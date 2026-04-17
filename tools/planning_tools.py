"""Planning helpers used for deterministic schedule generation."""

import re
from typing import Any, Dict, List

from .catalog_tools import (
    get_course_prerequisites,
    get_required_courses,
    load_catalog_data,
)
from .schedule_tools import get_offered_course_ids
from .transcript_tools import get_completed_courses
from .student_tools import load_student_profile


# ── Semester sequencing helpers ───────────────────────────────────────────────

_SEASON_TEMPLATE: Dict[str, str] = {
    "Fall": "Fall 2026",
    "Spring": "Spring 2026",
    "Summer": "Summer 2026 gc",
}

_MAX_SEMESTERS: Dict[str, int] = {
    "undergraduate": 8,
    "graduate": 4,
    "phd": 10,
}


def _next_semester(term: str) -> str:
    """Return the semester immediately following the given term.

    Spring → Fall (same year)
    Summer → Fall (same year)
    Fall   → Spring (next year)
    """
    parts = term.strip().split()
    season = parts[0]
    year = int(parts[-1])
    if season in ("Spring", "Summer"):
        return f"Fall {year}"
    return f"Spring {year + 1}"


def _template_term(season: str) -> str:
    """Map a season name to the stored schedule template term."""
    return _SEASON_TEMPLATE.get(season, "Fall 2026")


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
        c["course_id"]: c.get("credits", 0) for c in (catalog if isinstance(catalog, list) else catalog.get("courses", []))
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


def build_full_graduation_plan(
    major: str,
    completed_course_ids: List[str],
    current_semester: str,
    max_credits_per_semester: int = 12,
    min_credits_per_semester: int = 9,
    student_type: str = "undergraduate",
) -> List[Dict[str, Any]]:
    """Plan all remaining semesters until graduation.

    Uses the stored 2026 schedules as repeating templates for each season.
    Returns a list of planned semester dicts with course_ids and credits.
    """
    required_courses = get_required_courses(major)
    catalog = load_catalog_data()
    credits_by_course = {
        c["course_id"]: c.get("credits", 0)
        for c in (catalog if isinstance(catalog, list) else catalog.get("courses", []))
    }

    # Normalize all course IDs to use hyphens so prereq checks match catalog
    def _normalize(cid: str) -> str:
        return re.sub(r"\s+", "-", cid.strip().upper())

    placed = {_normalize(c) for c in completed_course_ids}
    required_courses = [_normalize(c) for c in required_courses]
    remaining = [c for c in required_courses if c not in placed]

    max_semesters = _MAX_SEMESTERS.get(student_type.lower(), 8)
    current_term = _next_semester(current_semester)
    planned: List[Dict[str, Any]] = []

    for _ in range(max_semesters):
        if not remaining:
            break

        season = current_term.split()[0]
        template = _template_term(season)
        offered = set(get_offered_course_ids(template))

        semester_courses: List[str] = []
        total_credits = 0
        deferred: List[str] = []

        for course_id in remaining:
            prereqs = [_normalize(p) for p in get_course_prerequisites(course_id)]
            unmet = [p for p in prereqs if p not in placed]
            if unmet or course_id not in offered:
                deferred.append(course_id)
                continue
            course_credits = credits_by_course.get(course_id, 0)
            if total_credits + course_credits > max_credits_per_semester:
                deferred.append(course_id)
                continue
            semester_courses.append(course_id)
            total_credits += course_credits
            placed.add(course_id)

        remaining = deferred

        if semester_courses:
            planned.append({
                "term": current_term,
                "course_ids": semester_courses,
                "total_credits": total_credits,
            })

        current_term = _next_semester(current_term)

    return planned
