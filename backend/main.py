"""
backend/main.py

FastAPI application entrypoint for CareerLens.

Startup sequence
----------------
1. Load ``.env`` via python-dotenv so environment variables are available
   before any module-level code in routers or agents runs.
2. Verify that ``AWS_PROFILE`` is set; print a clear error and exit if not,
   because all Bedrock calls will fail without valid credentials.
3. Mount CORS middleware allowing the Next.js dev server at
   ``http://localhost:3000``.
4. Register routers at their canonical path prefixes.

Running directly
----------------
::

    cd backend/
    python main.py          # starts uvicorn on http://0.0.0.0:8000
    uvicorn main:app --reload --port 8000  # hot-reload variant
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# 1. Load .env before any AWS / Strands imports
# ---------------------------------------------------------------------------
from dotenv import load_dotenv  # type: ignore[import-untyped]
from pathlib import Path as _Path

# Load .env from the project root (career-lens/), one level above backend/
_ROOT_ENV = _Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ROOT_ENV)

# ---------------------------------------------------------------------------
# 2. Validate required environment variables
# ---------------------------------------------------------------------------

if not os.getenv("AWS_PROFILE"):
    print(
        "\n[CareerLens] ERROR: AWS_PROFILE environment variable is not set.\n"
        "Please set it to a valid AWS credentials profile (e.g. 'sandbox2025').\n"
        "You can do this by:\n"
        "  - Adding AWS_PROFILE=sandbox2025 to your .env file, or\n"
        "  - Exporting it in your shell: export AWS_PROFILE=sandbox2025\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Build the FastAPI application
# ---------------------------------------------------------------------------

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import analysis, dashboard, profile  # noqa: E402

app = FastAPI(
    title="CareerLens API",
    description=(
        "Multi-agent job fit analyzer. Orchestrates PDF resume parsing, "
        "job-posting extraction, skill gap analysis, learning path curation, "
        "and weighted fit scoring."
    ),
    version="0.1.0",
)

# CORS — allow the Next.js dev server only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# 4. Register routers
# ---------------------------------------------------------------------------

app.include_router(profile, prefix="/profile", tags=["profile"])
app.include_router(analysis, prefix="/analysis", tags=["analysis"])
app.include_router(dashboard, prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# 5. Health-check endpoint
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 6. Direct execution entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["."],
    )
