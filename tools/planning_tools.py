"""Planning helpers used for deterministic schedule generation."""

from typing import Any, Dict, List

from .catalog_tools import (
    get_course_prerequisites,
    get_required_courses,
    load_catalog_data,
)
from .schedule_tools import get_offered_course_ids
from .transcript_tools import get_completed_courses
from .student_tools import load_student_profile


def recommend_courses(
    student_id: str, major: str, target_semester: str, max_credits: int
) -> Dict[str, Any]:
    """Return guarded course recommendations for one student scenario.

    Guardrails:
    - no completed courses
    - prerequisites must be met
    - must be offered in target semester
    - total credits must stay <= max_credits
    """
    completed = set(get_completed_courses(student_id))
    required_courses = get_required_courses(major)
    offered = set(get_offered_course_ids(target_semester))

    catalog = load_catalog_data()
    credits_by_course = {
        c["course_id"]: c.get("credits", 0) for c in catalog.get("courses", [])
    }

    recommended_courses: List[str] = []
    skipped_courses: List[Dict[str, str]] = []
    total_credits = 0

    for course_id in required_courses:
        if course_id in completed:
            skipped_courses.append({"course_id": course_id, "reason": "completed"})
            continue

        prerequisites = get_course_prerequisites(course_id)
        unmet = [pre for pre in prerequisites if pre not in completed]
        if unmet:
            skipped_courses.append(
                {"course_id": course_id, "reason": "unmet_prerequisites"}
            )
            continue

        if course_id not in offered:
            skipped_courses.append({"course_id": course_id, "reason": "not_offered"})
            continue

        course_credits = credits_by_course.get(course_id, 0)
        if total_credits + course_credits > max_credits:
            skipped_courses.append({"course_id": course_id, "reason": "credit_limit"})
            continue

        recommended_courses.append(course_id)
        total_credits += course_credits

    return {
        "student_id": student_id,
        "target_semester": target_semester,
        "max_credits": max_credits,
        "recommended_courses": recommended_courses,
        "total_recommended_credits": total_credits,
        "skipped_courses": skipped_courses,
    }


def build_next_semester_schedule(
    student_id: str, target_semester: str, max_credits: int
) -> Dict[str, Any]:
    """Build the next-term plan from normalized data using Python guardrails.

    student_id can be an alias like `s1`, `T1`, or a canonical JSON-backed id
    like `s1001`.
    """
    profile = load_student_profile(student_id)
    if profile.get("status") != "ready":
        return {
            "status": profile.get("status", "unavailable"),
            "student_ref": student_id,
            "target_semester": target_semester,
            "max_credits": max_credits,
            "message": profile.get(
                "message",
                "Student transcript is not ready for schedule generation.",
            ),
            "source_pdf": profile.get("source_pdf"),
            "recommended_courses": [],
            "total_recommended_credits": 0,
            "skipped_courses": [],
        }

    resolved_student_id = profile["student_id"]
    major = profile["major"]
    result = recommend_courses(
        student_id=resolved_student_id,
        major=major,
        target_semester=target_semester,
        max_credits=max_credits,
    )

    return {
        "status": "ready",
        "student_ref": student_id,
        "student_id": resolved_student_id,
        "student_name": profile.get("student_name"),
        "major": major,
        "current_semester": profile.get("current_semester"),
        "target_semester": target_semester,
        "max_credits": max_credits,
        "completed_courses": get_completed_courses(resolved_student_id),
        "recommended_courses": result["recommended_courses"],
        "total_recommended_credits": result["total_recommended_credits"],
        "skipped_courses": result["skipped_courses"],
    }
