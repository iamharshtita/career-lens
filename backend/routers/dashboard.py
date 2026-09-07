"""
backend/routers/dashboard.py

Dashboard router for CareerLens.

Endpoints
---------
GET /dashboard/jobs
    List all saved analysis results, sorted by analyzed_at descending.

GET /dashboard/jobs/{job_id}
    Return a specific analysis result by job_id.

POST /dashboard/jobs/{job_id}/rescore
    Re-run the pipeline from gap analysis using the current profile,
    and return the updated result.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents.orchestrator import PipelineError, rescore_job
from models.schemas import AnalysisResult
from storage.local_store import load_json, results_dir

router = APIRouter()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RescoreRequest(BaseModel):
    """Body accepted by POST /dashboard/jobs/{job_id}/rescore."""

    session_id: str


# ---------------------------------------------------------------------------
# GET /dashboard/jobs
# ---------------------------------------------------------------------------


@router.get("/jobs")
async def list_jobs() -> JSONResponse:
    """Return all saved analysis results sorted by analyzed_at descending.

    Iterates every ``.json`` file in the ``results/`` directory, deserializes
    each into an ``AnalysisResult``, and returns them ordered newest-first.
    Files that cannot be deserialized are silently skipped.

    Returns:
        JSON array of ``AnalysisResult`` objects.
    """
    rdir = results_dir()
    results: list[AnalysisResult] = []

    for path in sorted(rdir.glob("*.json")):
        key = path.stem
        raw = load_json(rdir, key)
        if raw is None:
            continue
        try:
            results.append(AnalysisResult.model_validate(raw))
        except Exception:
            # Skip corrupted result files rather than failing the whole list
            continue

    # Sort by analyzed_at descending (most recent first)
    results.sort(key=lambda r: r.analyzed_at, reverse=True)

    return JSONResponse(content=[r.model_dump(mode="json") for r in results])


# ---------------------------------------------------------------------------
# GET /dashboard/jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    """Return a specific analysis result by job_id.

    Args:
        job_id: UUID of the analysis result to retrieve.

    Returns:
        The ``AnalysisResult`` as JSON.

    Raises:
        HTTPException 404: If no result exists for the given job_id.
        HTTPException 422: If the stored data is corrupted.
    """
    raw = load_json(results_dir(), job_id)
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis result found for job_id '{job_id}'.",
        )

    try:
        result = AnalysisResult.model_validate(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Stored result for job_id '{job_id}' is corrupted: {exc}",
        ) from exc

    return JSONResponse(content=result.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# POST /dashboard/jobs/{job_id}/rescore
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/rescore")
async def rescore(job_id: str, body: RescoreRequest) -> JSONResponse:
    """Re-score an existing job analysis using the current profile.

    Reloads the saved ``ParsedJob`` for *job_id*, reloads the current
    ``ExtractedProfile`` for *session_id*, and re-runs gap analysis,
    learning path construction, and fit score computation.  The updated
    result is persisted and returned.

    Args:
        job_id: UUID of the previously analysed job.
        body:   JSON body containing ``session_id``.

    Returns:
        The updated ``AnalysisResult`` as JSON.

    Raises:
        HTTPException 404: If the job or profile cannot be loaded.
        HTTPException 422: If any pipeline stage fails.
    """
    try:
        result = rescore_job(
            job_id=job_id,
            session_id=body.session_id,
        )
    except PipelineError as exc:
        # Map "not found" pipeline errors to 404; everything else to 422
        if "No saved job found" in exc.message or "No profile found" in exc.message:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during re-score: {exc}",
        ) from exc

    return JSONResponse(content=result.model_dump(mode="json"))
