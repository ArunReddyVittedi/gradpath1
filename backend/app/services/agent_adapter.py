"""Adapter that turns the existing GradPath agent/tool outputs into UI-ready data."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from tools.catalog_tools import load_catalog_data, load_major_planning_context
from tools.student_tools import load_student_profile, load_student_index

from ..config import DEFAULT_MAX_CREDITS, DEFAULT_TARGET_SEMESTER, USE_ADK_WRAPPER
from ..models import (
    AdvisingNote,
    ChatMessage,
    CompletedCourse,
    DashboardData,
    ProgressSummary,
    RecommendedCourse,
    ResponseSchemaExample,
    StudentSnapshot,
    StructuredAgentResponse,
)
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
            target_semester=DEFAULT_TARGET_SEMESTER,
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
        },
        target_semester=DEFAULT_TARGET_SEMESTER,
        max_credits=DEFAULT_MAX_CREDITS,
        extra_notes=[],
    )
    return ResponseSchemaExample(
        completed_courses=dashboard.completed_courses,
        progress_summary=dashboard.progress_summary,
        recommended_courses=dashboard.recommended_courses,
        advising_notes=dashboard.advising_notes,
    )


def analyze_request(message: str, transcript: Optional[ParsedTranscript]) -> StructuredAgentResponse:
    target_semester = _extract_target_semester(message) or DEFAULT_TARGET_SEMESTER
    max_credits = _extract_max_credits(message) or DEFAULT_MAX_CREDITS
    student_ref = _extract_student_ref(message)

    extra_notes: List[AdvisingNote] = []
    profile: Optional[Dict[str, Any]] = None

    if transcript is not None:
        if transcript.profile is None:
            raise ValueError(
                "Transcript uploaded successfully, but I could not extract enough course history to plan from it."
            )
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

    if USE_ADK_WRAPPER and profile is not None:
        # Plug your Google ADK orchestration call in here if you want the web UI to
        # invoke the existing multi-agent flow directly instead of using the local
        # adapter below. Keep the return value mapped into the dashboard schema.
        adk_result = _try_invoke_google_adk_agent(
            message=message,
            profile=profile,
            target_semester=target_semester,
            max_credits=max_credits,
        )
        if adk_result is not None:
            return adk_result

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
        dashboard.progress_summary.target_semester = target_semester
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
        )

    dashboard = _build_dashboard_from_profile(
        profile=profile,
        target_semester=target_semester,
        max_credits=max_credits,
        extra_notes=extra_notes,
    )
    reply_text = _build_reply_text(dashboard, target_semester)
    return StructuredAgentResponse(reply_text=reply_text, dashboard=dashboard)


def _try_invoke_google_adk_agent(
    message: str,
    profile: Dict[str, Any],
    target_semester: str,
    max_credits: int,
) -> Optional[StructuredAgentResponse]:
    # This is intentionally conservative because ADK session bootstrapping varies
    # by project setup. Replace this stub with your real ADK runner if needed.
    _ = (message, profile, target_semester, max_credits)
    return None


def _build_dashboard_from_profile(
    profile: Dict[str, Any],
    target_semester: str,
    max_credits: int,
    extra_notes: List[AdvisingNote],
) -> DashboardData:
    catalog = load_catalog_data()
    major = str(profile.get("major") or "CS")
    planning_context = load_major_planning_context(major, target_semester)
    required_courses = planning_context.get("required_courses", [])
    course_lookup = {course["course_id"]: course for course in catalog.get("courses", [])}

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

    recommended_courses, skipped_notes, total_recommended_credits = _recommend_courses(
        completed_ids=completed_ids,
        required_courses=required_courses,
        planning_context=planning_context,
        course_lookup=course_lookup,
        max_credits=max_credits,
    )

    credits_earned = sum(course.credits for course in completed_courses)
    required_completed = sum(1 for course_id in required_courses if course_id in completed_ids)
    required_remaining = max(len(required_courses) - required_completed, 0)
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

    return DashboardData(
        student=StudentSnapshot(
            student_name=profile.get("student_name", "Unknown Student"),
            student_id=profile.get("student_id", profile.get("student_ref", "Unknown")),
            major=major,
            current_semester=profile.get("current_semester", "Unknown"),
            source=profile.get("source", "student_registry"),
        ),
        completed_courses=completed_courses,
        progress_summary=ProgressSummary(
            major=major,
            target_semester=target_semester,
            credits_earned=credits_earned,
            required_courses_total=len(required_courses),
            required_courses_completed=required_completed,
            required_courses_remaining=required_remaining,
            percent_complete=percent_complete,
            total_recommended_credits=total_recommended_credits,
        ),
        recommended_courses=recommended_courses,
        advising_notes=notes,
    )


def _recommend_courses(
    completed_ids: set,
    required_courses: List[str],
    planning_context: Dict[str, Any],
    course_lookup: Dict[str, Dict[str, Any]],
    max_credits: int,
) -> Tuple[List[RecommendedCourse], List[AdvisingNote], int]:
    recommended: List[RecommendedCourse] = []
    notes: List[AdvisingNote] = []
    total_credits = 0
    offered = set(planning_context.get("offered_in_target_semester", []))
    details = planning_context.get("course_details", {})

    for course_id in required_courses:
        if course_id in completed_ids:
            continue

        prerequisites = details.get(course_id, {}).get("prerequisites", [])
        unmet = [pre for pre in prerequisites if pre not in completed_ids]
        if unmet:
            notes.append(
                AdvisingNote(
                    level="warning",
                    title=f"{course_id} deferred",
                    message=f"Missing prerequisites: {', '.join(unmet)}.",
                )
            )
            continue

        if course_id not in offered:
            notes.append(
                AdvisingNote(
                    level="info",
                    title=f"{course_id} not offered",
                    message="This required course is not available in the selected semester.",
                )
            )
            continue

        credits = int(details.get(course_id, {}).get("credits", course_lookup.get(course_id, {}).get("credits", 0)))
        if total_credits + credits > max_credits:
            notes.append(
                AdvisingNote(
                    level="info",
                    title=f"{course_id} held for later",
                    message="Adding this course would exceed the max credit limit.",
                )
            )
            continue

        recommended.append(
            RecommendedCourse(
                course_id=course_id,
                title=course_lookup.get(course_id, {}).get("title", "Unknown Course"),
                credits=credits,
                reason="Fits remaining degree requirements, prerequisites, and term availability.",
            )
        )
        total_credits += credits

    return recommended, notes, total_credits


def _build_reply_text(dashboard: DashboardData, target_semester: str) -> str:
    student = dashboard.student
    if not dashboard.recommended_courses:
        return (
            f"I reviewed {student.student_name}'s record for {target_semester}, but I couldn't assemble a valid next-term plan yet. "
            "Check the advising notes for prerequisite, availability, or transcript issues."
        )

    recommendations = ", ".join(
        f"{course.course_id} ({course.title})" for course in dashboard.recommended_courses
    )
    return (
        f"I analyzed {student.student_name}'s academic history and updated the dashboard for {target_semester}. "
        f"Recommended next courses: {recommendations}. "
        f"Degree progress is now shown on the left, along with advising notes and warnings."
    )


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


def _extract_target_semester(message: str) -> Optional[str]:
    match = re.search(r"\b(Fall|Spring|Summer)\s+(20\d{2})\b", message, re.IGNORECASE)
    if not match:
        return None
    return f"{match.group(1).title()} {match.group(2)}"


def _extract_max_credits(message: str) -> Optional[int]:
    patterns = [
        r"max credits?\s*(?:is|=|:)?\s*(\d+)",
        r"up to\s*(\d+)\s*credits?",
        r"(\d+)\s*credits?\s*max",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _infer_profile_from_message(message: str) -> Optional[Dict[str, Any]]:
    course_lookup = {course["course_id"] for course in load_catalog_data().get("courses", [])}
    found_courses = [
        course_id
        for course_id in re.findall(r"\b[A-Z]{2,4}\d{3}\b", message.upper())
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
                        for course in load_catalog_data().get("courses", [])
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
