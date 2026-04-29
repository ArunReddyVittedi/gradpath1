"""Adapter that turns ADK agent and tool outputs into UI-ready data."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

LOGGER = logging.getLogger(__name__)

from tools.catalog_tools import load_catalog_data, load_major_planning_context
from tools.student_tools import load_student_index, load_student_profile
from tools.planning_tools import build_full_graduation_plan

from ..config import DEFAULT_MAX_CREDITS, DEFAULT_MIN_CREDITS, GRADUATION_CREDIT_REQUIREMENTS
from ..models import (
    AdvisingNote,
    ChatMessage,
    CompletedCourse,
    DashboardData,
    PlannedCourse,
    PlannedSemester,
    ProgressSummary,
    RecommendedCourse,
    ResponseSchemaExample,
    StudentSnapshot,
    StructuredAgentResponse,
)
from .adk_service import get_adk_runner_service
from .transcript_parser import ParsedTranscript


def build_placeholder_dashboard() -> DashboardData:
    return DashboardData(
        student=StudentSnapshot(
            student_name="Awaiting student input",
            student_id="Not identified",
            major="Unknown",
            current_semester="Not provided",
            source="chat_session",
        ),
        completed_courses=[],
        progress_summary=ProgressSummary(
            major="Unknown",
            target_semester="Not specified",
            credits_earned=0,
            required_courses_total=0,
            required_courses_completed=0,
            required_courses_remaining=0,
            percent_complete=0.0,
            total_recommended_credits=0,
        ),
        recommended_courses=[],
        advising_notes=[
            AdvisingNote(
                level="info",
                title="No transcript uploaded yet",
                message="Share a student ID, transcript file, or past coursework in chat to generate a plan.",
            ),
            AdvisingNote(
                level="info",
                title="Recommendations will appear here",
                message="The GradPath agent will update this dashboard automatically after analysis.",
            ),
        ],
    )


def build_welcome_history() -> List[ChatMessage]:
    return [
        ChatMessage(
            id=uuid4().hex,
            role="assistant",
            content=(
                "Share your student ID, goals, and target semester, or upload a transcript. "
                "I’ll analyze your history and update the planning dashboard for you."
            ),
            timestamp=_timestamp(),
        )
    ]


def build_schema_example() -> ResponseSchemaExample:
    dashboard = _build_dashboard_from_profile(
        {
            "student_id": "s1001",
            "student_name": "Alex Kim",
            "major": "CS",
            "current_semester": "Spring 2026",
            "completed_courses": [
                {"course_id": "CS101", "term": "Fall 2025", "grade": "A", "credits": 3},
                {"course_id": "CS102", "term": "Spring 2026", "grade": "B+", "credits": 3},
            ],
            "source": "example",
            "status": "ready",
        },
        target_semester="Not specified",
        extra_notes=[],
        adk_plan={"recommended_courses": ["CS201", "MATH201"], "total_recommended_credits": 6, "skipped_courses": []},
    )
    return ResponseSchemaExample(
        completed_courses=dashboard.completed_courses,
        progress_summary=dashboard.progress_summary,
        recommended_courses=dashboard.recommended_courses,
        advising_notes=dashboard.advising_notes,
    )


_FACTUAL_QUESTION_PATTERNS = [
    "how many", "how much", "what is my", "what's my", "whats my",
    "courses left", "courses remaining", "courses do i have",
    "credits left", "credits remaining", "credits do i have", "credits earned",
    "requirements left", "requirements remaining", "core requirements",
    "am i on track", "when will i graduate", "how close", "my progress",
    "my gpa", "completed courses", "what have i",
]


def _is_factual_question(message: str) -> bool:
    lower = message.lower()
    return any(pattern in lower for pattern in _FACTUAL_QUESTION_PATTERNS)


async def _answer_factual_question(
    message: str,
    profile: Dict[str, Any],
    session_dashboard: "DashboardData",
) -> StructuredAgentResponse:
    """Answer a factual question from existing profile data without touching the dashboard."""
    from tools.catalog_tools import load_major_planning_context
    from tools.planning_tools import _normalize

    major = profile.get("major", "CS")
    planning_context = load_major_planning_context(major, "Fall 2026")
    # Normalize both sides so 'CSC1058' and 'CSC-1058' compare equal
    required_courses = [_normalize(c) for c in planning_context.get("required_courses", [])]
    completed_ids = {_normalize(c["course_id"]) for c in profile.get("completed_courses", [])}
    required_completed = sum(1 for cid in required_courses if cid in completed_ids)
    required_remaining = len(required_courses) - required_completed
    credits_earned = sum(int(c.get("credits", 0)) for c in profile.get("completed_courses", []))

    # Graduation requirement varies by student type
    student_type = profile.get("student_type", "undergraduate")
    graduation_req = GRADUATION_CREDIT_REQUIREMENTS.get(student_type, 120)
    credits_to_graduate = max(graduation_req - credits_earned, 0)

    # Pull totals from the live dashboard when available and it has real data.
    # If the stored dashboard is still the placeholder (credits_to_graduate == 0 but
    # we know the student has not yet graduated), fall back to the computed value.
    dashboard_credits_to_graduate = (
        session_dashboard.progress_summary.credits_to_graduate
        if session_dashboard
           and session_dashboard.progress_summary
           and session_dashboard.progress_summary.credits_to_graduate > 0
        else credits_to_graduate
    )
    total_planned_credits = sum(
        sem.total_credits for sem in (session_dashboard.planned_semesters if session_dashboard else [])
    )
    elective_gap = max(dashboard_credits_to_graduate - total_planned_credits, 0)
    elective_note = (
        f"The required-course plan covers {total_planned_credits} of those {dashboard_credits_to_graduate} credits; "
        f"the remaining {elective_gap} must come from electives or gen-ed courses."
        if elective_gap > 0 and total_planned_credits > 0
        else ""
    )

    context = f"""You are GradPath, a friendly AI academic advisor.

The student asked: "{message}"

Here is their current academic data (treat these numbers as exact — do not invent different ones):
- Name: {profile.get("student_name", "Student")}
- Major: {major}
- Student type: {student_type}
- Credits earned: {credits_earned}
- Graduation requirement: {graduation_req} credits total
- Credits still needed to graduate: {dashboard_credits_to_graduate}
{("- " + elective_note) if elective_note else ""}
- Required courses completed: {required_completed} out of {len(required_courses)}
- Required courses remaining: {required_remaining}
- GPA: {profile.get("gpa", "not available")}
- Current semester: {profile.get("current_semester", "unknown")}

Answer their question directly and conversationally in 1–3 sentences using ONLY the numbers above. Be specific. Do not hallucinate — if something is listed as "not available", say so. Do not suggest uploading a transcript. Do not offer to generate a new plan unless asked.
"""
    api_key = os.getenv("GOOGLE_API_KEY", "")
    reply = ""
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(model="gemini-2.5-flash", contents=context),
            )
            reply = (getattr(response, "text", "") or "").strip()
        except Exception as exc:
            LOGGER.warning("Factual question reply failed: %s", exc)

    if not reply:
        reply = (
            f"You've completed {required_completed} of {len(required_courses)} required courses "
            f"with {required_remaining} remaining. You have {credits_earned} credits earned and need "
            f"{dashboard_credits_to_graduate} more to reach the {graduation_req}-credit graduation requirement."
            + (f" Your required-course plan covers {total_planned_credits} of those; "
               f"the remaining {elective_gap} credit(s) must come from electives."
               if elective_gap > 0 and total_planned_credits > 0 else "")
        )

    return StructuredAgentResponse(
        reply_text=reply,
        dashboard=session_dashboard,
        profile=profile,
    )


async def analyze_request(
    message: str,
    transcript: Optional[ParsedTranscript],
    web_session_id: str,
    session_profile: Optional[Dict[str, Any]] = None,
    session_dashboard: Optional["DashboardData"] = None,
) -> StructuredAgentResponse:
    student_ref = _extract_student_ref(message)

    extra_notes: List[AdvisingNote] = []
    profile: Optional[Dict[str, Any]] = None

    if transcript is not None:
        if transcript.status == "ocr_required":
            dashboard = build_placeholder_dashboard()
            dashboard.advising_notes = [
                AdvisingNote(
                    level="warning",
                    title="OCR support needed",
                    message=transcript.message,
                )
            ]
            return StructuredAgentResponse(reply_text=transcript.message, dashboard=dashboard)
        if transcript.profile is None:
            raise ValueError(transcript.message)
        profile = transcript.profile
        extra_notes.append(
            AdvisingNote(
                level="success",
                title="Transcript attached",
                message=f"Analyzed uploaded file: {transcript.filename}",
            )
        )
        extra_notes.extend(
            AdvisingNote(level="warning", title="Transcript parsing note", message=warning)
            for warning in transcript.warnings
        )
    elif student_ref:
        profile = load_student_profile(student_ref)

    # Use the profile saved from a previous turn in this session (e.g. transcript uploaded earlier)
    if profile is None and session_profile is not None:
        profile = session_profile

    # If the student declared their major in this message, update the session profile
    if profile is not None and profile.get("major", "Unknown") in {"Unknown", "Undergraduate", "Undeclared", ""}:
        inferred_major = _extract_major_from_message(message)
        if inferred_major:
            profile = {**profile, "major": inferred_major}

    if profile is None:
        inferred_profile = _infer_profile_from_message(message)
        if inferred_profile is not None:
            profile = inferred_profile
            extra_notes.append(
                AdvisingNote(
                    level="info",
                    title="Course history inferred from chat",
                    message="GradPath used the course references in the conversation to build a draft dashboard.",
                )
            )

    if profile is None:
        dashboard = build_placeholder_dashboard()
        dashboard.advising_notes.insert(
            0,
            AdvisingNote(
                level="warning",
                title="More academic history needed",
                message="Provide a student ID, upload a transcript, or list completed courses so GradPath can plan accurately.",
            ),
        )
        return StructuredAgentResponse(
            reply_text=(
                "I need more academic history before I can update your plan. "
                "Please share a student ID, transcript file, or completed courses."
            ),
            dashboard=dashboard,
            profile=None,
        )

    if profile.get("status") != "ready":
        dashboard = build_placeholder_dashboard()
        dashboard.student = StudentSnapshot(
            student_name=profile.get("student_name", "Unavailable"),
            student_id=profile.get("student_ref", profile.get("student_id", "Unavailable")),
            major=profile.get("major", "Unknown"),
            current_semester=profile.get("current_semester", "Unknown"),
            source="student_registry",
        )
        dashboard.advising_notes = [
            AdvisingNote(
                level="warning",
                title="Transcript not ready",
                message=profile.get("message", "Transcript data is not available yet."),
            )
        ]
        return StructuredAgentResponse(
            reply_text=dashboard.advising_notes[0].message,
            dashboard=dashboard,
            profile=profile,
        )

    if profile.get("major", "Unknown") in {"Unknown", "Undergraduate", "Undeclared", ""}:
        _VALID_MAJOR_NAMES = (
            "Computer Science, Biology, Chemistry, Biochemistry, Physics, Mathematics, "
            "History, Philosophy, Music, English, Communication, Sociology, Psychology, "
            "Criminal Justice, Health Science, Human Services, Environmental Science, "
            "Political Science, Pan-Africana Studies, Visual Arts, Accounting, Finance, "
            "Management, Information Systems Management, Forensic Science"
        )
        # Detect if the user tried to declare a major that isn't in our catalog
        tried_declaration = _looks_like_major_declaration(message)
        if tried_declaration:
            reply_text = (
                f"I didn't recognize \"{tried_declaration}\" as a Lincoln University major. "
                f"Please try one of the available majors: {_VALID_MAJOR_NAMES}."
            )
            note_message = (
                f"'{tried_declaration}' is not a recognized Lincoln University major. "
                f"Available majors: {_VALID_MAJOR_NAMES}."
            )
        else:
            reply_text = (
                f"Hi {profile.get('student_name', 'there')}! Your transcript was parsed successfully, "
                "but it does not list a declared major. "
                f"Please tell me your major (e.g. 'My major is Computer Science') so I can build your plan. "
                f"Available majors: {_VALID_MAJOR_NAMES}."
            )
            note_message = (
                "Your transcript does not list a declared major. "
                "Please reply with your major (e.g. 'My major is Computer Science') "
                f"so GradPath can build your degree plan. Available majors: {_VALID_MAJOR_NAMES}."
            )
        dashboard = build_placeholder_dashboard()
        dashboard.student = StudentSnapshot(
            student_name=profile.get("student_name", "Student"),
            student_id=profile.get("student_id", "uploaded-transcript"),
            major="Not declared",
            current_semester=profile.get("current_semester", "Unknown"),
            source=profile.get("source", "uploaded_transcript"),
        )
        dashboard.advising_notes = [
            *extra_notes,
            AdvisingNote(
                level="warning",
                title="Major not declared on transcript",
                message=note_message,
            ),
        ]
        return StructuredAgentResponse(
            reply_text=reply_text,
            dashboard=dashboard,
            profile=profile,
        )

    # Follow-up message — profile already exists from a previous turn.
    # Skip transcript_agent, history_agent, catalog_agent and go straight to planner.
    if session_profile is not None and transcript is None:
        # When the student just declared a major for the first time, skip the factual-question
        # shortcut and run the planner so they get a real plan, not stale placeholder stats.
        _unknown_majors = {"Unknown", "Undergraduate", "Undeclared", ""}
        major_just_declared = (
            session_profile.get("major", "Unknown") in _unknown_majors
            and profile.get("major", "Unknown") not in _unknown_majors
        )
        # Factual questions (e.g. "how many courses left") — answer from profile,
        # don't re-run the planner, and don't touch the dashboard.
        if _is_factual_question(message) and session_dashboard is not None and not major_just_declared:
            return await _answer_factual_question(message, profile, session_dashboard)

        return await _try_invoke_followup_agent(
            web_session_id=web_session_id,
            message=message,
            profile=profile,
            extra_notes=extra_notes,
        )

    return await _try_invoke_google_adk_agent(
        web_session_id=web_session_id,
        message=message,
        profile=profile,
        transcript=transcript,
        extra_notes=extra_notes,
    )


async def _try_invoke_google_adk_agent(
    web_session_id: str,
    message: str,
    profile: Dict[str, Any],
    transcript: Optional[ParsedTranscript],
    extra_notes: List[AdvisingNote],
) -> StructuredAgentResponse:
    adk_service = get_adk_runner_service()
    adk_result = await adk_service.run_planner(
        web_session_id=web_session_id,
        message=message,
        student_id=str(profile.get("student_id", profile.get("student_ref", ""))),
        student_name=str(profile.get("student_name", "Student")),
        major=str(profile.get("major", "CS")),
        current_semester=str(profile.get("current_semester", "Unknown")),
        transcript=transcript,
    )

    target_semester = adk_result.target_semester or "Not specified"

    if adk_result.planner_json is None:
        return StructuredAgentResponse(
            reply_text=adk_result.final_text or "GradPath needs a little more information before it can plan.",
            dashboard=build_placeholder_dashboard(),
            profile=profile,
        )

    notes = [
        AdvisingNote(
            level="success",
            title="Google ADK workflow active",
            message="The dashboard recommendations were generated by the live GradPath multi-agent flow.",
        ),
        *extra_notes,
    ]
    dashboard = _build_dashboard_from_profile(
        profile=profile,
        target_semester=target_semester,
        extra_notes=notes,
        adk_plan=adk_result.planner_json,
    )
    reply_text = await _generate_conversational_reply(dashboard, target_semester, message)
    return StructuredAgentResponse(reply_text=reply_text, dashboard=dashboard, profile=profile)


def _is_early_graduation_request(message: str) -> bool:
    keywords = ["early graduation", "graduate early", "finish early", "graduate faster", "fastest path", "accelerate"]
    lower = message.lower()
    return any(kw in lower for kw in keywords) or _extract_requested_semesters(message) is not None


def _extract_requested_semesters(message: str) -> Optional[int]:
    """Extract a specific semester count from messages like 'graduate in 2 semesters'."""
    patterns = [
        r'(?:in|next|within|only)\s+(\d+)\s+semester',
        r'(\d+)\s+semester[s]?\s+(?:left|remaining|to graduate|plan)',
        r'complete\s+(?:in|within)\s+(\d+)',
        r'finish\s+(?:in|within)\s+(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, message.lower())
        if match:
            val = int(match.group(1))
            if 1 <= val <= 8:
                return val
    return None


async def _try_invoke_followup_agent(
    web_session_id: str,
    message: str,
    profile: Dict[str, Any],
    extra_notes: List[AdvisingNote],
) -> StructuredAgentResponse:
    """Slim pipeline for follow-up messages — greeting + planner only."""
    if _is_early_graduation_request(message):
        requested_sems = _extract_requested_semesters(message)
        credits_earned = sum(int(c.get("credits", 0)) for c in profile.get("completed_courses", []))
        graduation_req = GRADUATION_CREDIT_REQUIREMENTS.get(profile.get("student_type", "undergraduate"), 120)
        credits_left = max(graduation_req - credits_earned, 0)
        if requested_sems and requested_sems > 0:
            import math
            credits_per_sem = math.ceil(credits_left / requested_sems)
            max_credits_override = min(max(credits_per_sem, 15), 21)
        else:
            max_credits_override = 15
        profile = {**profile, "preferences": "fastest", "max_credits": max_credits_override}

    adk_service = get_adk_runner_service()
    adk_result = await adk_service.run_followup(
        web_session_id=web_session_id,
        message=message,
        profile=profile,
    )

    # Merge any fields the student explicitly changed (non-null) into the saved profile.
    # This ensures changes like career_goal or target_semester persist across messages.
    updated_profile = profile
    if adk_result.greeting_json:
        changed = {k: v for k, v in adk_result.greeting_json.items() if v is not None}
        if changed:
            updated_profile = {**profile, **changed}

    target_semester = adk_result.target_semester or updated_profile.get("target_semester") or "Not specified"

    if adk_result.planner_json is None:
        return StructuredAgentResponse(
            reply_text=adk_result.final_text or "GradPath needs a little more information before it can plan.",
            dashboard=build_placeholder_dashboard(),
            profile=updated_profile,
        )

    notes = [
        AdvisingNote(
            level="success",
            title="Google ADK workflow active",
            message="The dashboard recommendations were generated by the live GradPath multi-agent flow.",
        ),
        *extra_notes,
    ]
    dashboard = _build_dashboard_from_profile(
        profile=updated_profile,
        target_semester=target_semester,
        extra_notes=notes,
        adk_plan=adk_result.planner_json,
    )
    reply_text = await _generate_conversational_reply(dashboard, target_semester, message)
    return StructuredAgentResponse(reply_text=reply_text, dashboard=dashboard, profile=updated_profile)


def _build_dashboard_from_profile(
    profile: Dict[str, Any],
    target_semester: str,
    extra_notes: List[AdvisingNote],
    adk_plan: Dict[str, Any],
) -> DashboardData:
    catalog = load_catalog_data()
    major = str(profile.get("major") or "CS")
    planning_context = load_major_planning_context(major, target_semester)
    required_courses = planning_context.get("required_courses", [])
    course_lookup = {course["course_id"]: course for course in (catalog if isinstance(catalog, list) else catalog.get("courses", []))}

    completed_courses_raw = profile.get("completed_courses", [])
    completed_ids = {course["course_id"] for course in completed_courses_raw}
    completed_courses = [
        CompletedCourse(
            course_id=course["course_id"],
            title=course_lookup.get(course["course_id"], {}).get("title", "Unknown Course"),
            term=course.get("term"),
            grade=course.get("grade"),
            credits=int(course.get("credits", course_lookup.get(course["course_id"], {}).get("credits", 0))),
        )
        for course in completed_courses_raw
    ]

    recommended_courses, skipped_notes, total_recommended_credits = _apply_adk_plan(
        adk_plan=adk_plan,
        course_lookup=course_lookup,
    )

    credits_earned = sum(course.credits for course in completed_courses)
    required_completed = sum(1 for course_id in required_courses if course_id in completed_ids)
    required_remaining = max(len(required_courses) - required_completed, 0)
    required_credits_total = sum(
        int(course_lookup.get(cid, {}).get("credits", 0))
        for cid in required_courses
        if cid not in completed_ids
    )
    percent_complete = round((required_completed / len(required_courses)) * 100, 1) if required_courses else 0.0

    notes = list(extra_notes)
    if not recommended_courses:
        notes.append(
            AdvisingNote(
                level="warning",
                title="No eligible courses found",
                message="GradPath could not find a valid recommendation set under the current constraints.",
            )
        )
    else:
        notes.append(
            AdvisingNote(
                level="success",
                title="Plan generated",
                message=f"Prepared {len(recommended_courses)} recommendation(s) for {target_semester}.",
            )
        )
    notes.extend(skipped_notes)

    # Build multi-semester graduation plan
    current_semester = profile.get("current_semester", "Spring 2026")
    student_type = profile.get("student_type", "undergraduate")

    # Count distinct semesters already completed from transcript
    completed_courses_raw = profile.get("completed_courses", [])
    semesters_used = len({c.get("term") for c in completed_courses_raw if c.get("term")})

    preferences = profile.get("preferences", "balanced")
    max_credits_for_plan = int(profile.get("max_credits", DEFAULT_MAX_CREDITS))
    if preferences == "fastest":
        max_credits_for_plan = max(max_credits_for_plan, 15)

    graduation_result = build_full_graduation_plan(
        major=major,
        completed_course_ids=list(completed_ids),
        current_semester=current_semester,
        max_credits_per_semester=max_credits_for_plan,
        min_credits_per_semester=DEFAULT_MIN_CREDITS,
        student_type=student_type,
        semesters_used=semesters_used,
    )
    raw_planned = graduation_result["planned"]
    unplanned = graduation_result["unplanned"]
    remaining_semesters = graduation_result["remaining_semesters"]
    total_semesters = graduation_result["total_semesters"]

    # Warn if student cannot finish all required courses in remaining semesters
    if unplanned:
        notes.append(AdvisingNote(
            level="warning",
            title="Cannot finish on time",
            message=(
                f"You have used {semesters_used} of {total_semesters} semesters. "
                f"With {remaining_semesters} semester(s) remaining, "
                f"{len(unplanned)} required course(s) could not be scheduled: "
                f"{', '.join(unplanned[:5])}{'...' if len(unplanned) > 5 else ''}. "
                "Consider speaking with your advisor about overloading or extending your program."
            ),
        ))

    planned_semesters = [
        PlannedSemester(
            term=sem["term"],
            total_credits=sem["total_credits"],
            courses=[
                PlannedCourse(
                    course_id=cid,
                    title=course_lookup.get(cid, {}).get("title", "Unknown Course"),
                    credits=int(course_lookup.get(cid, {}).get("credits", 0)),
                )
                for cid in sem["course_ids"]
            ],
        )
        for sem in raw_planned
    ]

    graduation_requirement = GRADUATION_CREDIT_REQUIREMENTS.get(student_type, 120)
    credits_to_graduate = max(graduation_requirement - credits_earned, 0)
    total_planned_credits = sum(sem.total_credits for sem in planned_semesters)

    if total_planned_credits > credits_to_graduate:
        overage = total_planned_credits - credits_to_graduate
        notes.append(AdvisingNote(
            level="warning",
            title="Plan exceeds graduation requirement",
            message=(
                f"Your planned semesters total {total_planned_credits} credits, but you only need "
                f"{credits_to_graduate} more credits to reach the {graduation_requirement}-credit "
                f"graduation requirement. You are over-scheduled by {overage} credit(s). "
                "Consider dropping an elective or speaking with your advisor to trim the plan."
            ),
        ))
    elif total_planned_credits < credits_to_graduate:
        elective_gap = credits_to_graduate - total_planned_credits
        notes.append(AdvisingNote(
            level="info",
            title="Additional elective credits needed",
            message=(
                f"Your required-course plan covers {total_planned_credits} of the {credits_to_graduate} credits "
                f"you still need to graduate. The remaining {elective_gap} credit(s) must come from electives, "
                "free electives, or general education courses not listed in this plan. "
                "Speak with your advisor to choose courses that fulfill those requirements."
            ),
        ))

    return DashboardData(
        student=StudentSnapshot(
            student_name=profile.get("student_name", "Unknown Student"),
            student_id=profile.get("student_id", profile.get("student_ref", "Unknown")),
            major=major,
            current_semester=current_semester,
            source=profile.get("source", "student_registry"),
            student_type=student_type,
            gpa=profile.get("gpa"),
            expected_graduation=profile.get("expected_graduation"),
            career_goal=profile.get("career_goal"),
            preferences=profile.get("preferences"),
            email=profile.get("email"),
        ),
        completed_courses=completed_courses,
        progress_summary=ProgressSummary(
            major=major,
            target_semester=target_semester,
            credits_earned=credits_earned,
            required_courses_total=len(required_courses),
            required_courses_completed=required_completed,
            required_courses_remaining=required_remaining,
            required_credits_total=required_credits_total,
            credits_to_graduate=credits_to_graduate,
            percent_complete=percent_complete,
            total_recommended_credits=total_recommended_credits,
        ),
        recommended_courses=recommended_courses,
        advising_notes=notes,
        planned_semesters=planned_semesters,
    )



def _apply_adk_plan(
    adk_plan: Dict[str, Any],
    course_lookup: Dict[str, Dict[str, Any]],
) -> Tuple[List[RecommendedCourse], List[AdvisingNote], int]:
    recommended: List[RecommendedCourse] = []
    notes: List[AdvisingNote] = []

    for course_id in adk_plan.get("recommended_courses", []):
        course = course_lookup.get(course_id, {})
        recommended.append(
            RecommendedCourse(
                course_id=course_id,
                title=course.get("title", "Unknown Course"),
                credits=int(course.get("credits", 0)),
                reason="Selected by the GradPath ADK planner after evaluating history, prerequisites, and offerings.",
            )
        )

    # Group skipped courses by reason and generate summary notes
    skipped_by_reason: Dict[str, List[str]] = {}
    for skipped in adk_plan.get("skipped_courses", []):
        course_id = skipped.get("course_id", "UNKNOWN")
        reason = skipped.get("reason", "deferred")
        if course_id == "TRANSCRIPT":
            continue
        skipped_by_reason.setdefault(reason, []).append(course_id)

    completed_list = skipped_by_reason.get("completed", [])
    prereq_list = skipped_by_reason.get("unmet_prerequisites", [])
    not_offered_list = skipped_by_reason.get("not_offered", [])
    credit_list = skipped_by_reason.get("credit_limit", [])

    # Build one paragraph summary note
    summary_parts = []

    if completed_list:
        summary_parts.append(
            f"{len(completed_list)} required course{'s are' if len(completed_list) != 1 else ' is'} already completed and counted toward your degree."
        )

    if prereq_list:
        prereq_str = ", ".join(prereq_list[:3]) + ("..." if len(prereq_list) > 3 else "")
        summary_parts.append(
            f"{len(prereq_list)} course{'s' if len(prereq_list) != 1 else ''} ({prereq_str}) {'are' if len(prereq_list) != 1 else 'is'} waiting on prerequisites — complete earlier courses first to unlock {'them' if len(prereq_list) != 1 else 'it'}."
        )

    if not_offered_list:
        summary_parts.append(
            f"{len(not_offered_list)} course{'s are' if len(not_offered_list) != 1 else ' is'} not offered this semester and will be available in a future term."
        )

    if credit_list:
        summary_parts.append(
            f"{len(credit_list)} course{'s were' if len(credit_list) != 1 else ' was'} deferred to the next semester to stay within the credit cap."
        )

    if summary_parts:
        notes.append(AdvisingNote(
            level="info",
            title="Degree Progress Summary",
            message=" ".join(summary_parts),
        ))

    total_credits = int(adk_plan.get("total_recommended_credits", 0))
    return recommended, notes, total_credits


async def _generate_conversational_reply(
    dashboard: DashboardData,
    target_semester: str,
    message: str = "",
) -> str:
    """Call Gemini to generate a natural, conversational advisor reply."""
    student = dashboard.student
    progress = dashboard.progress_summary

    # Guard: no plan at all — neither recommended courses nor planned semesters
    if not dashboard.recommended_courses and not dashboard.planned_semesters:
        return (
            f"I reviewed {student.student_name}'s record for {target_semester}, but couldn't put together a valid plan right now. "
            "Check the advising notes on the left — there may be prerequisite gaps or availability issues."
        )

    planned_count = len(dashboard.planned_semesters)
    total_planned_credits = sum(sem.total_credits for sem in dashboard.planned_semesters)
    elective_gap = max(progress.credits_to_graduate - total_planned_credits, 0)

    # Use the first planned semester as the "next semester" for the chat reply.
    # This is more accurate than recommended_courses, which can land in later semesters
    # once prerequisite ordering is applied by the graduation planner.
    if dashboard.planned_semesters:
        next_sem = dashboard.planned_semesters[0]
        next_sem_label = next_sem.term
        course_list = ", ".join(f"{c.course_id} ({c.title})" for c in next_sem.courses)
        total_credits = next_sem.total_credits
    else:
        next_sem_label = target_semester
        course_list = ", ".join(f"{c.course_id} ({c.title})" for c in dashboard.recommended_courses)
        total_credits = sum(c.credits for c in dashboard.recommended_courses)

    elective_note = (
        f"\n- IMPORTANT: The required-course plan covers only {total_planned_credits} of the {progress.credits_to_graduate} credits needed to graduate. "
        f"The remaining {elective_gap} credit(s) must come from electives or gen-ed courses not listed in this plan."
        if elective_gap > 0 else
        f"\n- The required-course plan covers all {total_planned_credits} credits needed to graduate."
    )

    # Include any warning/error advising notes so Gemini knows about unscheduled courses,
    # credit overages, or other constraints that the plan could not satisfy.
    warning_notes = [
        note for note in dashboard.advising_notes
        if note.level in ("warning", "error")
    ]
    warnings_block = ""
    if warning_notes:
        warnings_block = "\nACTIVE WARNINGS (must be reflected in your reply if relevant):\n" + "\n".join(
            f"- [{note.title}] {note.message}" for note in warning_notes
        )

    # If the student requested a specific semester count, include that so Gemini
    # can honestly compare it against what the plan actually produced.
    requested_sems = _extract_requested_semesters(message)
    requested_sems_note = (
        f"\n- Student requested graduation in {requested_sems} semester(s), but the plan produced {planned_count} semester(s) due to prerequisite or schedule constraints."
        if requested_sems is not None and requested_sems != planned_count
        else ""
    )

    context = f"""You are GradPath, an AI academic advisor. The analysis of this student's academic record has ALREADY been completed by the GradPath system — you are reporting the results. Do not say you "can't analyze transcripts" or "can't update plans" — that work is done. Your job is only to communicate the results clearly.

The student said: "{message}"

ACTUAL RESULTS from the completed analysis (treat this as ground truth):
- Student: {student.student_name}, Major: {student.major}
- Immediate next semester: {next_sem_label}
- Courses planned for next semester: {course_list} ({total_credits} credits)
- Required courses completed: {progress.required_courses_completed}/{progress.required_courses_total}
- Degree progress: {progress.percent_complete}% complete
- Credits needed to graduate: {progress.credits_to_graduate}
- Credits covered by the required-course plan: {total_planned_credits}{elective_note}
- Total planned semesters remaining: {planned_count}{requested_sems_note}{warnings_block}

CRITICAL RULES:
1. The analysis is complete — never say you cannot analyze transcripts, access data, or update plans.
2. Only say something "changed" or "updated" if it is reflected in the results above.
3. If the student requested something not reflected in the results (e.g. asked for 2 semesters but plan shows {planned_count}), be honest — report what the plan shows and briefly explain why (prerequisites, credit limits, schedule availability).
4. Do not invent course removals, additions, or changes not shown in the data.
5. If something truly cannot be done, say so and suggest an alternative.
6. NEVER claim the plan covers all {progress.credits_to_graduate} credits needed to graduate if total_planned_credits ({total_planned_credits}) is less than that. Always be honest about the elective gap.
7. If there are ACTIVE WARNINGS above, mention the most important one to the student.
8. Be warm, conversational, and specific — 2–4 sentences, no bullet points, no headers.
"""

    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        LOGGER.warning("GOOGLE_API_KEY not set — falling back to template reply")
        elective_suffix = (
            f" Your required-course plan covers {total_planned_credits} of those; "
            f"the remaining {elective_gap} credit(s) must come from electives."
            if elective_gap > 0 else ""
        )
        return (
            f"Here's your updated plan for {target_semester}: {course_list} ({total_credits} credits). "
            f"You're {progress.percent_complete}% through required courses with {progress.credits_to_graduate} credits left to graduate.{elective_suffix}"
        )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents=context,
            ),
        )
        reply = (getattr(response, "text", "") or "").strip()
        if reply:
            return reply
    except Exception as exc:
        LOGGER.warning("Conversational reply generation failed: %s", exc)

    return (
        f"Here's your updated plan for {target_semester}: {course_list} ({total_credits} credits). "
        f"You're {progress.percent_complete}% through required courses with {progress.credits_to_graduate} credits left to graduate."
    )



_MESSAGE_MAJOR_PATTERNS = {
    # longest phrases first so they match before shorter substrings
    "biochemistry and molecular biology": "BIOCHEM",
    "information systems management": "ISM",
    "chemistry forensic science": "FORENSIC",
    "forensic science": "FORENSIC",
    "environmental science": "ENV",
    "environmental studies": "ENV",
    "pan-africana studies": "PAS",
    "pan africana studies": "PAS",
    "political science": "POL",
    "criminal justice": "CRJ",
    "health science": "HSC",
    "computer science": "CS",
    "human services": "HUS",
    "visual arts": "ART",
    "black studies": "PAS",
    "information systems": "ISM",
    "biochemistry": "BIOCHEM",
    "mathematical sciences": "MAT",
    "mathematics": "MAT",
    "communication": "COM",
    "anthropology": "ANT",
    "accounting": "ACC",
    "sociology": "SOC",
    "psychology": "PSY",
    "philosophy": "PHL",
    "management": "MGT",
    "chemistry": "CHE",
    "biology": "BIO",
    "physics": "PHY",
    "history": "HIS",
    "finance": "FIN",
    "english": "ENG",
    "music": "MUS",
    "data science": "CS",
    "math": "MAT",
    "art": "ART",
    "religion": "REL",
    "religious studies": "REL",
    "french": "FRE",
    "spanish": "SPN",
}


def _extract_major_from_message(message: str) -> Optional[str]:
    """Extract a major declaration from a follow-up message like 'I am a CS student'."""
    lower = message.lower()
    for phrase, major_key in sorted(_MESSAGE_MAJOR_PATTERNS.items(), key=lambda x: -len(x[0])):
        if phrase in lower:
            return major_key
    return None


def _looks_like_major_declaration(message: str) -> Optional[str]:
    """Return the declared major string if the message looks like 'my major is X', else None."""
    match = re.search(
        r"(?:my major is|i(?:'m| am) (?:a |an )?|major(?:ing)? in)\s+([A-Za-z][A-Za-z\s\-]{1,40})",
        message,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".")
    return None


def _extract_student_ref(message: str) -> Optional[str]:
    index = load_student_index()
    aliases = []
    for record in index.get("students", []):
        aliases.extend(record.get("aliases", []))

    alias_pattern = "|".join(sorted({re.escape(alias) for alias in aliases}, key=len, reverse=True))
    if not alias_pattern:
        return None

    match = re.search(rf"\b({alias_pattern})\b", message, re.IGNORECASE)
    return match.group(1) if match else None



def _infer_profile_from_message(message: str) -> Optional[Dict[str, Any]]:
    catalog = load_catalog_data()
    catalog_list = catalog if isinstance(catalog, list) else catalog.get("courses", [])
    course_lookup = {course["course_id"] for course in catalog_list}
    found_courses = [
        course_id
        for course_id in re.findall(r"\b[A-Z]{2,4}-\d{3,4}\b", message.upper())
        if course_id in course_lookup
    ]
    if not found_courses:
        return None

    completed_courses = []
    seen = set()
    for course_id in found_courses:
        if course_id in seen:
            continue
        seen.add(course_id)
        completed_courses.append(
            {
                "course_id": course_id,
                "term": None,
                "grade": None,
                "credits": next(
                    (
                        int(course.get("credits", 0))
                        for course in catalog_list
                        if course.get("course_id") == course_id
                    ),
                    0,
                ),
            }
        )

    return {
        "student_id": "chat-history",
        "student_name": "Student from chat",
        "major": "CS",
        "current_semester": "Unknown",
        "completed_courses": completed_courses,
        "status": "ready",
        "source": "chat_message",
    }


def build_user_message(content: str, attachment_name: Optional[str] = None) -> ChatMessage:
    return ChatMessage(
        id=uuid4().hex,
        role="user",
        content=content,
        timestamp=_timestamp(),
        attachment_name=attachment_name,
    )


def build_assistant_message(content: str, attachment_name: Optional[str] = None) -> ChatMessage:
    return ChatMessage(
        id=uuid4().hex,
        role="assistant",
        content=content,
        timestamp=_timestamp(),
        attachment_name=attachment_name,
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
