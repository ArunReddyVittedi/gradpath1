# GradPath — AI-Powered Academic Planning Assistant

GradPath is an AI-powered academic advising tool I built for Lincoln University students. It helps students figure out which courses to take next semester based on their transcript, declared major, and Lincoln University's real course catalog and schedule data.

A student uploads their transcript PDF, and GradPath automatically:
- Parses their academic history (completed courses, GPA, credits earned)
- Checks which required courses for their major they still need
- Verifies prerequisites and semester availability
- Recommends a personalized next-semester course plan
- Displays everything in a live dashboard

---

## What I Built

This project combines a multi-agent AI backend with a full web UI:

- **5-agent AI pipeline** using Google ADK (Agent Development Kit) with Gemini 2.5 Flash
- **FastAPI backend** that handles transcript uploads, session memory, and API routing
- **React + Vite frontend** with a two-panel layout (dashboard on left, chat on right)
- **Real Lincoln University data** — 597 courses from the 2026 catalog, Spring 2026 schedule with 468 sections, and degree requirements for 11 majors

---

## Project Structure

```
gradpath/
├── agent.py                          # Root ADK SequentialAgent (5 sub-agents)
├── agents/
│   ├── greeting_agent.py             # Collects target semester and credit limit
│   ├── transcript_agent.py           # Parses uploaded transcript PDF
│   ├── history_agent.py              # Summarizes completed courses
│   ├── catalog_agent.py              # Loads major requirements and schedule
│   └── planner_agent.py              # Recommends next-semester courses
├── tools/
│   ├── catalog_tools.py              # Reads catalog and major requirements JSON
│   ├── schedule_tools.py             # Reads semester schedule JSON
│   ├── transcript_tools.py           # ADK tool for transcript extraction
│   ├── transcript_parser.py          # pdfplumber-based PDF parsing
│   └── transcript_schema.py          # Pydantic schemas + course ID normalization
├── backend/
│   └── app/
│       ├── main.py                   # FastAPI app entry point
│       ├── models.py                 # API response schemas
│       ├── routers/chat.py           # /api/session and /api/chat endpoints
│       └── services/
│           ├── agent_adapter.py      # Converts ADK output to dashboard data
│           ├── adk_service.py        # Runs the ADK pipeline for web sessions
│           ├── session_store.py      # In-memory session + profile persistence
│           └── transcript_parser.py  # Upload parsing for the web API
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── styles.css
│       └── components/
│           ├── ChatPanel.tsx
│           └── DashboardPanel.tsx
├── data/
│   ├── catalogs/
│   │   ├── catalog_2026.json         # 597 real LU courses
│   │   └── major_requirements.json   # Required courses for 11 majors
│   └── schedules/
│       ├── spring_2026.json          # 468 sections
│       ├── summer_2026_gc.json       # 17 sections (Graduate Center)
│       └── summer_2026_ol.json       # 64 sections (Online)
├── scripts/
│   └── parse_all.py                  # pdfplumber parser for LU PDFs
├── run_gradpath_ui.py                # One-command project launcher
└── requirements.txt
```

---

## How It Works

### Full Request Flow

1. Student opens the app — a new session is created with a blank dashboard
2. Student uploads their transcript PDF (or types their student ID)
3. FastAPI receives the upload and runs `pdfplumber` to extract text
4. Gemini parses the raw text into structured JSON (courses, GPA, student info)
5. Course codes are normalized to canonical LU format (e.g. `CSC1058` → `CSC-1058`)
6. Failed grades (F, NP, NC, U) are excluded from completed courses
7. The student profile is passed to the Google ADK pipeline:

```
greeting_agent   → determines target semester and max credits
transcript_agent → reads transcript from session state
history_agent    → extracts list of completed course IDs
catalog_agent    → loads required courses, prerequisites, schedule offerings
planner_agent    → applies constraints and outputs recommended courses
```

8. The planner checks three constraints for each required course:
   - Are prerequisites satisfied?
   - Is the course offered this semester?
   - Would adding it exceed the credit limit?
9. The dashboard updates with recommendations, progress %, and advising notes
10. The student profile is saved in session memory — follow-up messages don't require re-uploading the transcript

### Session Memory

After the first message, GradPath remembers the student's profile (major, completed courses, semester) for the rest of the browser session. This works by saving the profile dict in `SessionStore` after every request and loading it at the start of the next one. If a student's major was not declared on the transcript, GradPath asks them to type it and automatically detects phrases like "I am a CS student" to update the plan.

---

## Data

All data was parsed directly from real Lincoln University PDF files using `scripts/parse_all.py`:

| File | Source | Size |
|---|---|---|
| `catalog_2026.json` | LU Academic Catalog 2026 PDF | 597 courses, 44 departments |
| `major_requirements.json` | LU degree requirements | 11 majors, 11–22 courses each |
| `spring_2026.json` | LU Spring 2026 Course Schedule PDF | 468 sections |
| `summer_2026_gc.json` | LU Summer 2026 GC Schedule PDF | 17 sections |
| `summer_2026_ol.json` | LU Summer 2026 Online Schedule PDF | 64 sections |

---

## Tech Stack

| Component | Technology |
|---|---|
| AI Agents | Google ADK (SequentialAgent + LlmAgent) |
| LLM | Gemini 2.5 Flash |
| Backend | FastAPI + Uvicorn |
| Frontend | React + Vite + TypeScript |
| PDF Parsing | pdfplumber |
| Data Validation | Pydantic |
| Session Memory | Python in-memory dict (InMemoryRunner) |

---

## Running the Project

### 1. Clone and set up the environment

```bash
git clone https://github.com/ArunReddyVittedi/gradpath1.git
cd gradpath1
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Set up your API key

Copy `.env.example` to `.env` and add your Google API key:

```env
GOOGLE_API_KEY=your_google_api_key_here
GRADPATH_TRANSCRIPT_LLM_MODEL=gemini-2.5-flash
GRADPATH_FRONTEND_ORIGIN=http://localhost:5173
```

Get a free key at [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials).

### 3. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. Run

```bash
python run_gradpath_ui.py
```

Opens at **http://127.0.0.1:8000**

---

## API Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/api/session` | Start a new session, returns blank dashboard |
| POST | `/api/chat` | Send message + optional transcript, returns updated dashboard |
| GET | `/api/schema` | Example response shape for reference |

`POST /api/chat` accepts `multipart/form-data`:
- `session_id` — from `/api/session`
- `message` — student's chat message
- `transcript` — optional PDF file upload

---

## Supported Transcript Uploads

- `.pdf` — text-based PDFs (most LU transcripts)
- `.json`, `.txt`, `.md` — structured or plain text

Scanned/image-only PDFs return an "OCR required" message with a clear explanation.

---

## Majors Supported

CS, Biology (BIO), Chemistry (CHE), Biochemistry (BIOCHEM), Health Science (HSC), Accounting (ACC), Finance (FIN), Management (MGT), Information Systems (ISM), Criminal Justice (CRJ), Anthropology (ANT)

---

## Known Limitations

- Fall 2026 schedule data is not yet available — fall planning uses catalog-inferred availability
- Session memory is in-memory only — cleared when the server restarts
- Currently plans one semester at a time — multi-semester roadmap not yet implemented
