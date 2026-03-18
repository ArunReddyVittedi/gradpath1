"""Root workflow for GradPath.

ADK looks for `root_agent` in this file.
We use SequentialAgent because planning steps must run in strict order.
"""

from google.adk.agents import SequentialAgent

from gradpath.agents import (
    catalog_agent,
    greeting_agent,
    history_agent,
    planner_agent,
)


root_agent = SequentialAgent(
    name="gradpath_root_agent",
    description="Runs the GradPath academic planning flow in sequence.",
    sub_agents=[
        greeting_agent,  # Step 1: collect student planning inputs
        history_agent,   # Step 2: summarize one student's transcript
        catalog_agent,   # Step 3: summarize one major/term catalog slice
        planner_agent,   # Step 4: recommend next-semester courses
    ],
)
