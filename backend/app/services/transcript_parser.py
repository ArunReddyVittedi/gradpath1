"""Helpers for transcript uploads and lightweight transcript extraction."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.catalog_tools import load_catalog_data


GRADE_PATTERN = r"(A\+|A-|A|B\+|B-|B|C\+|C-|C|D|F|P|S)"


@dataclass
class ParsedTranscript:
    filename: str
    raw_text: str
    profile: Optional[Dict[str, Any]]
    warnings: List[str]


def parse_upload(filename: str, content: bytes) -> ParsedTranscript:
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        return _parse_json_upload(filename, content)
    if suffix in {".txt", ".md"}:
        text = content.decode("utf-8", errors="ignore")
        return ParsedTranscript(
            filename=filename,
            raw_text=text,
            profile=_profile_from_text(text),
            warnings=[],
        )
    if suffix == ".pdf":
        return _parse_pdf_upload(filename, content)
    raise ValueError("Unsupported transcript file type. Upload JSON, TXT, MD, or PDF.")


def _parse_json_upload(filename: str, content: bytes) -> ParsedTranscript:
    payload = json.loads(content.decode("utf-8"))
    raw_text = json.dumps(payload, indent=2)
    profile = _normalize_profile(payload)
    return ParsedTranscript(filename=filename, raw_text=raw_text, profile=profile, warnings=[])


def _parse_pdf_upload(filename: str, content: bytes) -> ParsedTranscript:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ValueError(
            "PDF transcript parsing requires the `pypdf` package. Install backend dependencies first."
        ) from exc

    import io

    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError(
            "The PDF did not contain extractable text. If it is a scan, convert it to text or JSON first."
        )
    profile = _profile_from_text(text)
    warnings: List[str] = []
    if profile is None:
        warnings.append("Transcript text was loaded, but the parser could only extract limited structure.")
    return ParsedTranscript(filename=filename, raw_text=text, profile=profile, warnings=warnings)


def _profile_from_text(text: str) -> Optional[Dict[str, Any]]:
    course_ids = _extract_course_ids(text)
    if not course_ids:
        return None

    name_match = re.search(r"(student name|name)\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    id_match = re.search(r"(student id|student_id|id)\s*[:\-]\s*([A-Za-z0-9]+)", text, re.IGNORECASE)
    major_match = re.search(r"(major|program)\s*[:\-]\s*(.+)", text, re.IGNORECASE)
    semester_match = re.search(
        r"(current semester|semester|term)\s*[:\-]\s*(Fall|Spring|Summer)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )

    completed_courses: List[Dict[str, Any]] = []
    seen = set()
    for course_id in course_ids:
        if course_id in seen:
            continue
        seen.add(course_id)
        grade_match = re.search(rf"{course_id}.*?{GRADE_PATTERN}", text, re.IGNORECASE)
        completed_courses.append(
            {
                "course_id": course_id,
                "term": None,
                "grade": grade_match.group(1).upper() if grade_match else None,
                "credits": _credits_for_course(course_id),
            }
        )

    return {
        "student_id": id_match.group(2).strip().lower() if id_match else "uploaded-transcript",
        "student_name": name_match.group(2).strip() if name_match else "Uploaded Student",
        "major": major_match.group(2).strip().upper() if major_match else "CS",
        "current_semester": f"{semester_match.group(2).title()} {semester_match.group(3)}"
        if semester_match
        else "Unknown",
        "completed_courses": completed_courses,
        "status": "ready",
        "source": "uploaded_transcript",
    }


def _normalize_profile(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    completed_courses = payload.get("completed_courses", [])
    if completed_courses and isinstance(completed_courses[0], str):
        completed_courses = [
            {
                "course_id": course_id,
                "term": None,
                "grade": None,
                "credits": _credits_for_course(course_id),
            }
            for course_id in completed_courses
        ]

    if not completed_courses:
        return None

    return {
        "student_id": payload.get("student_id", "uploaded-transcript"),
        "student_name": payload.get("student_name", "Uploaded Student"),
        "major": payload.get("major", "CS"),
        "current_semester": payload.get("current_semester", "Unknown"),
        "completed_courses": completed_courses,
        "status": "ready",
        "source": "uploaded_transcript",
    }


def _extract_course_ids(text: str) -> List[str]:
    course_ids = {course["course_id"] for course in load_catalog_data().get("courses", [])}
    found = re.findall(r"\b[A-Z]{2,4}\d{3}\b", text.upper())
    return [course_id for course_id in found if course_id in course_ids]


def _credits_for_course(course_id: str) -> int:
    for course in load_catalog_data().get("courses", []):
        if course.get("course_id") == course_id:
            return int(course.get("credits", 0))
    return 0
