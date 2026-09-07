"""
backend/routers/analysis.py — SSE streaming for the analysis pipeline.
"""
from __future__ import annotations

import json
import queue
import threading
from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from agents.orchestrator import PipelineError, run_pipeline

router = APIRouter()
_SENTINEL = object()


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.get("/analyze")
async def analyze(
    job_url: str = Query(...),
    session_id: str = Query(...),
) -> StreamingResponse:

    def event_generator() -> Generator[str, None, None]:
        q: queue.Queue = queue.Queue()

        def progress_callback(event_type: str, stage: str, message: str) -> None:
            # event_type is "progress" or "log"
            q.put(_sse(event_type, {"stage": stage, "message": message}))

        def worker() -> None:
            try:
                result = run_pipeline(
                    job_url=job_url.strip(),
                    session_id=session_id.strip(),
                    progress_callback=progress_callback,
                )
                q.put(_sse("result", {
                    "fit_score": result.fit_score,
                    "skill_gaps": [g.model_dump(mode="json") for g in result.skill_gaps],
                    "learning_path": [s.model_dump(mode="json") for s in result.learning_path],
                }))
            except PipelineError as exc:
                q.put(_sse("error", {"message": exc.message, "stage": exc.stage}))
            except Exception as exc:
                q.put(_sse("error", {"message": f"Unexpected error: {exc}"}))
            finally:
                q.put(_sse("done", {}))
                q.put(_SENTINEL)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        yield ": connected\n\n"

        while True:
            try:
                item = q.get(timeout=120)
            except queue.Empty:
                yield _sse("error", {"message": "Pipeline timed out."})
                break
            if item is _SENTINEL:
                break
            yield item

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
