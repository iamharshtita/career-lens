# CareerLens -- Multi-Agent Job Fit Analyzer

CareerLens analyzes the fit between your resume and any job posting using a pipeline of specialized AI agents. Paste a job URL, upload your resume, and get a fit score (0-100), ranked skill gaps, and a personalized learning path in under 90 seconds.

---

## How it works

Five agents run in sequence, each passing structured output to the next:

| Agent | What it does | LLM? | Tools |
|---|---|---|---|
| Profile Agent | Extracts skills, experience, education from your PDF resume | Yes (1 call) | None |
| Job Parser Agent | Fetches and parses the job posting from any public URL | Yes (1 call) | http_request |
| Gap Analyzer Agent | Identifies missing skills and ranks them by criticality | Yes (1 call) | None |
| Learning Path Agent | Finds YouTube tutorials and course links per gap | No | YouTube API |
| Assessor (Fit Score) | Computes weighted fit score | No | None |

The Job Parser Agent is the only genuine agentic tool-use loop -- it decides which API to call (Greenhouse JSON API, Lever API, or direct fetch), reads the response, and retries if needed.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Any supported LLM provider API key (see Configuration)
- YouTube Data API v3 key -- free at https://console.cloud.google.com

---

## Configuration

From the project root (`career-lens/`):

```bash
cp .env.example .env
```

Open `.env` and configure your LLM provider:

```
# Set to: bedrock, anthropic, or openai
LLM_PROVIDER=bedrock

# AWS Bedrock (default)
AWS_PROFILE=your_aws_profile_name
AWS_DEFAULT_REGION=us-east-1

# Anthropic (set LLM_PROVIDER=anthropic)
# ANTHROPIC_API_KEY=your_key

# OpenAI (set LLM_PROVIDER=openai)
# OPENAI_API_KEY=your_key

# Required for all providers
YOUTUBE_API_KEY=your_youtube_key
CAREERLENS_DATA_DIR=./backend/data
```

All agents read from a central `backend/agents/model_factory.py` -- setting `LLM_PROVIDER` in `.env` is the only change needed to switch providers. No code changes required.

---

## Installation

From the project root (`career-lens/`):

```bash
# Install backend dependencies
cd backend && pip3 install -r requirements.txt && cd ..

# Install frontend dependencies
cd frontend && npm install && cd ..
```

---

## Running the full system

From the project root (`career-lens/`), open two separate terminals:

```bash
# Terminal 1 -- backend API (port 8000)
cd backend
python3 main.py

# Terminal 2 -- frontend (port 3000)
cd frontend
npm run dev
```

Open http://localhost:3000 in your browser. Go to **Profile** to upload your resume PDF, then go to **Analyze** and paste any job posting URL.

---

## Running the baseline

From the project root (`career-lens/`):

```bash
python3 baseline.py \
  --job-url "https://job-boards.greenhouse.io/embed/job_app?for=chicagotradingcampus&jr_id=6a70e264cb96192a368463f9" \
  --resume-text "CS student at ASU graduating 2027. Skills: Python, JavaScript, React, SQL..."
```

The baseline is a single LLM call with no tools. It cannot fetch URLs -- it reasons from the URL string and resume text alone. Used as the comparison point for evaluation.

---

## Running the evaluation suite

From the project root (`career-lens/`):

```bash
python3 eval/eval_runner.py --fixtures eval/fixtures/ --output eval/report.json
```

Runs both CareerLens and the baseline on 20 annotated fixtures and writes a structured comparison report with fit score MAE, skill extraction precision/recall, gap ranking NDCG@5, and resource relevance scores.

---

## Project structure

```
career-lens/
├── .env.example                 # Environment variable template
├── baseline.py                  # Single-agent comparison baseline
├── backend/
│   ├── main.py                  # FastAPI server (port 8000)
│   ├── requirements.txt         # Python dependencies
│   ├── agents/
│   │   ├── job_parser.py        # Job Parser Agent -- http_request tool loop
│   │   ├── profile_agent.py     # Profile Agent
│   │   ├── gap_analyzer.py      # Gap Analyzer Agent
│   │   ├── learning_path.py     # Learning Path Agent
│   │   ├── assessor.py          # Assessor sub-agents (built, not yet wired in)
│   │   └── orchestrator.py      # Pipeline coordinator and SSE streaming
│   ├── routers/                 # FastAPI route handlers
│   ├── models/schemas.py        # Pydantic data models
│   └── tools/pdf_extractor.py   # pdfplumber wrapper
├── frontend/
│   ├── package.json
│   └── app/
│       ├── profile/page.tsx     # Resume upload page
│       ├── job/page.tsx         # Job analysis page with live SSE stream
│       └── dashboard/page.tsx   # Saved analyses and re-score
└── eval/
    ├── fixtures/                # 20 annotated job/resume pairs
    ├── eval_runner.py           # Evaluation script
    └── metrics.py               # MAE, precision/recall, NDCG, relevance
```

---

## Supported job boards

| Platform | Fetch method |
|---|---|
| Greenhouse | Greenhouse JSON API (no scraping needed) |
| Lever | Lever public API |
| Workday, LinkedIn, others | Direct HTTP fetch with browser headers |

---

## Known limitations

- Fit score uses a heuristic formula. `assessor.py` with three LLM sub-agents is implemented but not yet connected to the pipeline.
- YouTube API free tier allows 100 searches/day.
- E-learning recommendations are search links, not direct course results.
- Evaluation fixtures use placeholder URLs; real job board URLs are planned for the next phase.
