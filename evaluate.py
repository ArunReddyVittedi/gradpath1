"""Simple evaluation runner for GradPath.

Compares expected recommendations from eval_cases.json
against actual recommendations from the guardrail planner logic.
"""

import json
from pathlib import Path

from gradpath.tools import recommend_courses


EVAL_FILE = Path(__file__).resolve().parent / "data" / "eval" / "eval_cases.json"


def run_evaluation() -> None:
    """Run all evaluation cases and print a readable report."""
    with EVAL_FILE.open("r", encoding="utf-8") as f:
        eval_data = json.load(f)

    cases = eval_data.get("cases", [])
    passed = 0

    print("GradPath Evaluation Report")
    print("=" * 28)

    for case in cases:
        case_id = case["case_id"]
        student_id = case["student_id"]
        major = case["major"]
        target_semester = case["target_semester"]
        max_credits = case["max_credits"]
        expected = case.get("expected_recommendations", [])

        actual_result = recommend_courses(
            student_id=student_id,
            major=major,
            target_semester=target_semester,
            max_credits=max_credits,
        )
        actual = actual_result["recommended_courses"]

        is_pass = actual == expected
        if is_pass:
            passed += 1

        print(f"\nCase: {case_id}")
        print(f"Expected: {expected}")
        print(f"Actual:   {actual}")
        print(f"Result:   {'PASS' if is_pass else 'FAIL'}")

        if not is_pass:
            print(f"Skipped detail: {actual_result['skipped_courses']}")

    total = len(cases)
    print("\n" + "-" * 28)
    print(f"Score: {passed}/{total} cases passed")


if __name__ == "__main__":
    run_evaluation()
