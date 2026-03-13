"""Planning helpers used for simple local evaluation."""

from typing import Any, Dict, List

from .catalog_tools import (
    get_course_prerequisites,
    get_required_courses,
    load_catalog_data,
)
from .schedule_tools import get_offered_course_ids
from .transcript_tools import get_completed_courses


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
