"""Tools for reading and summarizing student transcript data."""

import json
from pathlib import Path
from typing import Any, Dict, List


# Base folder for all data files.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"


def load_transcript_data(student_id: str) -> Dict[str, Any]:
    """Load one student's transcript JSON by student_id.

    Example: student_id='s1001' -> data/transcripts/student_s1001.json
    """
    file_path = TRANSCRIPTS_DIR / f"student_{student_id}.json"
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_completed_courses(student_id: str) -> List[str]:
    """Return only the list of completed course IDs for a student."""
    transcript = load_transcript_data(student_id)
    completed = transcript.get("completed_courses", [])
    return [course["course_id"] for course in completed]
