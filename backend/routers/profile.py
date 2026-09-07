"""
backend/routers/profile.py

Profile router for CareerLens.

Endpoints
---------
POST /profile/upload
    Validate and upload a PDF resume.  Invokes the Profile Agent to extract
    structured data and returns the session_id plus the extracted profile.

GET /profile/{session_id}
    Retrieve a previously stored profile by session_id.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from agents.profile_agent import parse_resume
from models.schemas import ExtractedProfile
from storage.local_store import load_json, profiles_dir

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPE = "application/pdf"


# ---------------------------------------------------------------------------
# POST /profile/upload
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_profile(file: UploadFile) -> JSONResponse:
    """Upload a PDF resume and extract structured profile data.

    Validation rules (both enforced before any processing):
    - MIME type must be ``application/pdf``.
    - File size must not exceed 10 MB (10,485,760 bytes).

    On success, the extracted profile is persisted to local storage and
    returned alongside the newly created ``session_id``.

    Args:
        file: The uploaded file from a multipart/form-data request.

    Returns:
        JSON object ``{"session_id": str, "profile": ExtractedProfile}``.

    Raises:
        HTTPException 400: If MIME type or file size validation fails.
        HTTPException 422: If the PDF text cannot be extracted or parsed.
    """
    # --- MIME type validation ---
    content_type = file.content_type or ""
    if content_type != ALLOWED_MIME_TYPE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid file type '{content_type}'. "
                "Only PDF files (application/pdf) are accepted."
            ),
        )

    # --- Read file bytes ---
    pdf_bytes = await file.read()

    # --- File size validation ---
    if len(pdf_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(pdf_bytes) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=(
                f"File is too large ({size_mb:.1f} MB). "
                "The maximum allowed size is 10 MB."
            ),
        )

    # --- Invoke Profile Agent ---
    session_id = str(uuid.uuid4())
    try:
        profile: ExtractedProfile = parse_resume(pdf_bytes, session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse resume: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred during profile extraction: {exc}",
        ) from exc

    return JSONResponse(
        content={
            "session_id": session_id,
            "profile": profile.model_dump(mode="json"),
        }
    )


# ---------------------------------------------------------------------------
# GET /profile/{session_id}
# ---------------------------------------------------------------------------


@router.get("/{session_id}")
async def get_profile(session_id: str) -> JSONResponse:
    """Retrieve a stored profile by session_id.

    Args:
        session_id: UUID of the session whose profile should be returned.

    Returns:
        The stored ``ExtractedProfile`` as JSON.

    Raises:
        HTTPException 404: If no profile exists for the given session_id.
        HTTPException 422: If the stored data is corrupted and cannot be
            deserialized into an ``ExtractedProfile``.
    """
    raw = load_json(profiles_dir(), session_id)
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail=f"No profile found for session_id '{session_id}'. "
                   "Please upload your resume first.",
        )

    try:
        profile = ExtractedProfile.model_validate(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Stored profile for session_id '{session_id}' is corrupted: {exc}",
        ) from exc

    return JSONResponse(content=profile.model_dump(mode="json"))
