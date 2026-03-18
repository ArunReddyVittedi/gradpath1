"""Tools for reading catalog, requirements, and prerequisites."""

import json
from pathlib import Path
from typing import Any, Dict, List

from .schedule_tools import get_offered_course_ids


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOGS_DIR = DATA_DIR / "catalogs"


# We keep one default demo catalog file for the beginner project.
DEFAULT_CATALOG_FILE = CATALOGS_DIR / "catalog_2026.json"


def load_catalog_data() -> Dict[str, Any]:
    """Load the demo catalog JSON."""
    with DEFAULT_CATALOG_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_required_courses(major: str) -> List[str]:
    """Return required course IDs for a given major (example: 'CS')."""
    catalog = load_catalog_data()
    return catalog.get("majors", {}).get(major, {}).get("required_courses", [])


def get_course_prerequisites(course_id: str) -> List[str]:
    """Return prerequisite course IDs for one course."""
    catalog = load_catalog_data()
    for course in catalog.get("courses", []):
        if course.get("course_id") == course_id:
            return course.get("prerequisites", [])
    return []


def load_major_planning_context(major: str, target_semester: str) -> Dict[str, Any]:
    """Return only the catalog data needed for one major and one term."""
    catalog = load_catalog_data()
    required_courses = get_required_courses(major)

    course_details: Dict[str, Dict[str, Any]] = {}
    for course in catalog.get("courses", []):
        course_id = course.get("course_id")
        if course_id in required_courses:
            course_details[course_id] = {
                "credits": course.get("credits", 0),
                "prerequisites": course.get("prerequisites", []),
            }

    return {
        "major": major,
        "target_semester": target_semester,
        "required_courses": required_courses,
        "course_details": course_details,
        "offered_in_target_semester": get_offered_course_ids(target_semester),
    }
