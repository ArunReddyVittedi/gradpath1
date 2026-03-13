# GradPath (Step 10: Run Locally)

This guide shows the minimum commands to run GradPath with Google ADK and test one student scenario.

## 1. Create and activate a virtual environment

```bash
cd "/Users/arunr3ddy/Documents/New project"
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install ADK

```bash
pip install google-adk
```

## 3. Configure environment variables

GradPath agents use `gemini-2.0-flash`, so set your Google API key:

```bash
export GOOGLE_API_KEY="YOUR_API_KEY_HERE"
```

Optional: put this in a `.env` file at `/Users/arunr3ddy/Documents/New project/gradpath/.env`.

## 4. Run GradPath with ADK Web UI

From project root:

```bash
cd "/Users/arunr3ddy/Documents/New project"
adk web
```

Then select the `gradpath` agent package in the ADK UI.

## 5. Test one student scenario

Use this single prompt in ADK chat:

```text
I am Alex Kim. My student_id is s1001.
My major is CS.
Current semester is Spring 2026.
Target semester is Fall 2026.
Max credits is 9.
Please plan my next semester.
```

## 6. CLI alternative (no web UI)

```bash
cd "/Users/arunr3ddy/Documents/New project"
adk run gradpath
```

When prompted, paste the same scenario text above.


## 7. Run simple evaluation (expected vs actual)

From project root:

```bash
cd "/Users/arunr3ddy/Documents/New project"
python3 -m gradpath.evaluate
```

This reads `data/eval/eval_cases.json` and prints PASS/FAIL for each case.
