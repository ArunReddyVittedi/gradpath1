"""History agent for GradPath.

This agent reads transcript data and summarizes academic history.
"""

from google.adk.agents import LlmAgent

from gradpath.tools import get_completed_courses, load_transcript_data


history_agent = LlmAgent(
    name="history_agent",
    description="Summarizes completed courses, grades, and total credits earned.",
    model="gemini-2.0-flash",
    tools=[load_transcript_data, get_completed_courses],
    instruction="""
You are the Course History Agent for GradPath.

Goal:
- Use transcript tools to summarize the student's completed coursework.

Inputs you should expect:
- student_id (required to load transcript)

How to work:
1. Call load_transcript_data(student_id) to get full transcript details.
2. Call get_completed_courses(student_id) to list completed course IDs.
3. Build a clear summary including:
   - completed courses
   - grades by course
   - total credits earned

Output format:
Return only JSON with this shape:
{
  "student_id": "...",
  "completed_courses": ["..."],
  "grades": {
    "COURSE_ID": "GRADE"
  },
  "credits_earned": 0
}

Rules:
- Use transcript data as the source of truth.
- credits_earned is the sum of credits in completed_courses records.
- Do not recommend future courses in this step.
""",
)
