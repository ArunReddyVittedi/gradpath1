# GradPath

GradPath is an AI-powered academic planning assistant built with the [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/). It helps students plan their next semester by analyzing their transcript history, degree requirements, and available course offerings — using a four-agent sequential workflow so each agent only sees the data it needs.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Data Flow](#data-flow)
- [Setup](#setup)
- [Running the App](#running-the-app)
- [Example Prompt](#example-prompt)
- [Troubleshooting](#troubleshooting)
- [Evaluation](#evaluation)
- [Data Ingestion](#data-ingestion)

---

## Project Structure

```
gradpath/
├── agent.py                        # Root sequential workflow orchestrator
├── agents/
│   ├── greeting_agent.py           # Step 1: Collects student planning inputs
│   ├── history_agent.py            # Step 2: Loads & summarizes transcript history
│   ├── catalog_agent.py            # Step 3: Loads degree requirements & offerings
│   └── planner_agent.py            # Step 4: Recommends next-semester courses
├── tools/
│   ├── student_tools.py            # Resolve student IDs, load profiles
│   ├── transcript_tools.py         # Access transcript data
│   ├── catalog_tools.py            # Load catalogs, requirements, prerequisites
│   ├── schedule_tools.py           # Load semester offerings
│   └── planning_tools.py           # Course recommendation logic
├── scripts/
│   ├── build_source_manifest.py    # Rebuild the data registry
│   ├── ingest_schedule_pdfs.py     # Parse schedule PDFs into JSON
│   └── extract_catalog_pdf_text.py # Extract catalog PDF to text
├── data/
│   ├── transcripts/                # T1.pdf–T10.pdf + normalized student JSON
│   ├── catalogs/                   # Catalog PDFs + normalized JSON
│   ├── schedules/                  # Schedule PDFs + normalized JSON
│   ├── registry/                   # student_index.json, source_manifest.json
│   └── eval/                       # eval_cases.json (test cases)
├── evaluate.py                     # Local evaluation runner
└── .env                            # API key configuration
```

---

## Architecture

GradPath uses a **four-agent sequential ADK flow**. Each agent receives only the minimal data slice it needs — no agent ever sees the full repository, all transcripts, or entire catalog documents at once. This keeps LLM context small and responses focused.

```
User Input
    │
    ▼
┌─────────────────┐
│  greeting_agent │  Collects: student_id, student_name,
│                 │            target_semester, max_credits
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  history_agent  │  Loads: that student's transcript summary only
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  catalog_agent  │  Loads: that major's requirements +
│                 │          target semester's course offerings
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  planner_agent  │  Outputs: personalized course recommendations
└─────────────────┘
```

**LLM Model:** `gemini-2.5-flash` (configurable)

---

## Data Flow

The project treats **PDFs as source documents** and **JSON as normalized runtime data**. All planning happens against JSON only — this keeps token usage small.

| Path | Description |
|------|-------------|
| `data/transcripts/T1.pdf` … `T10.pdf` | Source transcript PDFs (image scans) |
| `data/transcripts/student_s1001.json` | Normalized transcript — ready ✅ |
| `data/transcripts/student_s1002.json` | Normalized transcript — ready ✅ |
| `data/transcripts/student_s1003.json` … | Not yet ready — OCR required ⚠️ |
| `data/catalogs/*.pdf` | Source course catalog PDFs |
| `data/catalogs/*.json` | Normalized catalog JSON |
| `data/schedules/*.pdf` | Source schedule PDFs |
| `data/schedules/*.json` | Normalized schedule JSON |
| `data/registry/student_index.json` | Alias map: `T1 → s1 → s1001` |
| `data/registry/source_manifest.json` | Registry of all current data files |

> **Note:** Transcript PDFs T3–T10 are image scans that require OCR before they can be converted to runtime JSON. Only students `s1001` and `s1002` are fully usable right now.

---

## Setup

### Prerequisites

- Python 3.10+
- A [Google AI Studio](https://aistudio.google.com) API key with access to Gemini models

### 1. Navigate to the project root

```bash
cd "C:\Users\Dell\Desktop\New folder"
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Install the ADK framework

```bash
.\.venv\Scripts\python.exe -m pip install google-adk
```

> **PowerShell note:** If `.\.venv\Scripts\Activate.ps1` gives an "execution policy" error, either fix it with a one-time policy change or skip activation entirely.

**Option A — Fix execution policy (one-time):**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

**Option B — Skip activation, call python directly:**
```powershell
.\.venv\Scripts\python.exe -m adk web
```

### 4. Configure your API key

Edit `gradpath/.env` and set your key:

```env
GOOGLE_API_KEY=your_google_api_key_here
```

---

## Running the App

### Web UI (recommended)

```bash
cd "C:\Users\Dell\Desktop\New folder"
.\.venv\Scripts\python.exe -m adk web
```

Opens a browser-based chat interface at `http://localhost:8000`.

### CLI mode

```bash
cd "C:\Users\Dell\Desktop\New folder"
.\.venv\Scripts\python.exe -m adk run gradpath
```

---

## Example Prompt

Once the app is running, try:

```
My student_id is s1.
My name is Alex Kim.
Target semester is Fall 2026.
Max credits is 9.
Please plan my next semester.
```

Student ID aliases are supported — `s1`, `T1`, and `s1001` all resolve to the same normalized record.

**Available test students:** `s1001` (alias: `s1`, `T1`) and `s1002` (alias: `s2`, `T2`)

---

## Troubleshooting

### PowerShell execution policy error

```
Activate.ps1 cannot be loaded because running scripts is disabled on this system.
```

**Fix:** Skip activation entirely and use the full path to python:
```bash
.\.venv\Scripts\python.exe -m adk web
```

Or allow scripts for your user account (one-time):
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### 429 RESOURCE_EXHAUSTED — quota exceeded

```
Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests
limit: 5, model: gemini-2.5-flash
```

This means you've hit the **free tier rate limit** of 5 requests per minute for `gemini-2.5-flash`.

**Options:**

| Fix | Details |
|-----|---------|
| Wait ~21 seconds | The quota resets per minute — works for occasional testing |
| Switch to `gemini-2.0-flash` | Free tier allows 15 RPM — change the model name in agent files |
| Enable billing | Upgrades to 1000+ RPM — set up at [ai.dev/rate-limit](https://ai.dev/rate-limit) |
| Use a new API key | Each Google project gets its own free quota — create one at [aistudio.google.com](https://aistudio.google.com) |

---

## Evaluation

Run the local evaluation suite to check course recommendation accuracy:

```bash
cd "C:\Users\Dell\Desktop\New folder"
python -m gradpath.evaluate
```

This runs test cases from `data/eval/eval_cases.json` and compares actual recommendations against expected outputs.

**Current test cases:**
- `s1001` — CS major, Fall 2026, 9 credits → expects `[CS201, CS210, MATH201]`
- `s1002` — CS major, Fall 2026, 6 credits → expects `[CS220, CS230]`

---

## Data Ingestion

Only needed when source PDFs change.

### Rebuild the registry

```bash
cd "C:\Users\Dell\Desktop\New folder"
python -m gradpath.scripts.build_source_manifest
```

Refreshes `data/registry/student_index.json` and `data/registry/source_manifest.json`.

### Extract schedule PDFs to JSON

```bash
.\.venv\Scripts\python.exe -m gradpath.scripts.ingest_schedule_pdfs
```

### Extract catalog PDF to text

```bash
.\.venv\Scripts\python.exe -m gradpath.scripts.extract_catalog_pdf_text
```

> **Transcript PDFs (T3–T10):** These are image scans and require an OCR step before they can be normalized into runtime JSON. This is not yet automated.
