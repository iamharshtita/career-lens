"""
backend/routers

FastAPI router package for CareerLens.

Routers
-------
profile   — PDF upload and profile retrieval  (/profile/...)
analysis  — SSE-streamed pipeline analysis    (/analysis/...)
dashboard — Saved results and re-scoring      (/dashboard/...)
"""

from routers.analysis import router as analysis
from routers.dashboard import router as dashboard
from routers.profile import router as profile

__all__ = ["analysis", "dashboard", "profile"]
