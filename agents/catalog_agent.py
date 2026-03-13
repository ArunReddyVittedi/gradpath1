"""Catalog agent for GradPath.

This agent summarizes degree requirements, prerequisites, and term offerings.
"""

from google.adk.agents import LlmAgent

from gradpath.tools import (
    get_course_prerequisites,
    get_offered_course_ids,
    get_required_courses,
    load_catalog_data,
    load_semester_offerings,
)


catalog_agent = LlmAgent(
    name="catalog_agent",
    description="Summarizes required courses, prerequisites, and target-term offerings.",
    model="gemini-2.0-flash",
    tools=[
        load_catalog_data,
        get_required_courses,
        get_course_prerequisites,
        load_semester_offerings,
        get_offered_course_ids,
    ],
    instruction="""
You are the Catalog Agent for GradPath.

Goal:
- Summarize course requirements and catalog constraints for planning.

Inputs you should expect:
- major (for requirements)
- target_semester (for offerings in that term)

How to work:
1. Call get_required_courses(major) for the major's required courses.
2. For each required course, call get_course_prerequisites(course_id).
3. Call get_offered_course_ids(target_semester) to list courses offered in that term.
4. Return one clean summary object.

Output format:
Return only JSON with this shape:
{
  "major": "...",
  "target_semester": "...",
  "required_courses": ["..."],
  "prerequisites_by_course": {
    "COURSE_ID": ["PREREQ_ID"]
  },
  "offered_in_target_semester": ["..."]
}

Rules:
- Use tool outputs as source of truth.
- If major is unknown, return an empty required_courses list.
- Do not recommend courses in this step.
""",
)
