"""
backend/agents/profile_agent.py

Profile Agent for CareerLens.

Parses a raw PDF resume (supplied as bytes) into a structured
``ExtractedProfile`` using the Strands Agents SDK and Amazon Bedrock.

Public API
----------
create_profile_agent() -> Agent
    Factory that instantiates a fresh Strands Agent configured for
    resume parsing.

parse_resume(pdf_bytes: bytes, session_id: str) -> ExtractedProfile
    End-to-end entry point:
    1. Extracts raw text from the PDF bytes via ``pdf_extractor``.
    2. Sends the text to the LLM-backed agent with a structured-output
       prompt.
    3. Parses the LLM response into an ``ExtractedProfile`` Pydantic model.
    4. Persists the profile to local storage.
    5. Returns the ``ExtractedProfile``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from strands import Agent

from agents.model_factory import get_model

from models.schemas import (
    EducationDetail,
    ExperienceEntry,
    ExtractedProfile,
)
from storage.local_store import profiles_dir, save_json
from tools.pdf_extractor import PDFExtractionError, extract_pdf_text

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

PROFILE_SYSTEM_PROMPT = """You are a precise resume parser.

When given resume text, you extract structured information and return it as
valid JSON with the following top-level keys:

  "skills"              – list of strings; deduplicated, normalised skill names
                          (e.g. "Python", "Machine Learning", "Docker")
  "experience_entries"  – list of objects, each with:
                            "title"           (string, required)
                            "company"         (string, required)
                            "duration_months" (integer ≥ 0, or null if unknown)
                            "description"     (string, required)
  "education_details"   – list of objects, each with:
                            "degree"      (string, required)
                            "institution" (string, required)
                            "year"        (integer 1900-2100, or null if unknown)
                            "field"       (string or null)

Rules:
- Return ONLY the JSON object — no markdown fences, no commentary.
- Deduplicate and normalise skill names (title-case; expand common abbreviations
  where unambiguous, e.g. "ML" → "Machine Learning").
- List experience entries most-recent first.
- If a field cannot be determined from the text, use null for optional fields
  or an empty list where appropriate.
- Do not invent information that is not present in the resume text.
"""

# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_profile_agent() -> Agent:
    """Return a configured Strands Agent for resume parsing.

    The agent uses Amazon Bedrock (Claude 3.5 Haiku) and requires no
    additional tools — structured extraction is handled entirely via
    prompt engineering and JSON parsing of the model response.
    """
    return Agent(
        model=get_model(),
        system_prompt=PROFILE_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Return the first JSON object found in *text*.

    The LLM may occasionally wrap the JSON in markdown code fences despite
    the prompt instruction. This helper strips those fences and returns the
    bare JSON string.
    """
    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    # Otherwise look for the first top-level JSON object
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return text.strip()


def _parse_llm_response(raw: str, session_id: str, raw_text: str) -> ExtractedProfile:
    """Parse the LLM's JSON response into a validated ``ExtractedProfile``.

    Args:
        raw:        The raw string returned by the agent.
        session_id: Session UUID to embed in the profile.
        raw_text:   Original plain-text extracted from the PDF.

    Returns:
        A validated ``ExtractedProfile`` Pydantic model.

    Raises:
        ValueError: If the JSON cannot be decoded or fails Pydantic
            validation.
    """
    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Profile agent returned invalid JSON: {exc}\nRaw response: {raw[:500]}"
        ) from exc

    # Build sub-models with graceful handling of missing/null fields
    experience_entries: list[ExperienceEntry] = []
    for entry in data.get("experience_entries") or []:
        try:
            experience_entries.append(ExperienceEntry(**entry))
        except Exception:
            # Skip malformed entries rather than failing the whole parse
            continue

    education_details: list[EducationDetail] = []
    for edu in data.get("education_details") or []:
        try:
            education_details.append(EducationDetail(**edu))
        except Exception:
            continue

    skills: list[str] = [
        s for s in (data.get("skills") or []) if isinstance(s, str) and s.strip()
    ]

    try:
        profile = ExtractedProfile(
            session_id=session_id,
            skills=skills,
            experience_entries=experience_entries,
            education_details=education_details,
            raw_text=raw_text,
            extracted_at=datetime.now(tz=timezone.utc),
        )
    except Exception as exc:
        raise ValueError(f"Failed to construct ExtractedProfile: {exc}") from exc

    return profile


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_resume(pdf_bytes: bytes, session_id: str) -> ExtractedProfile:
    """Extract and parse a resume PDF into a stored ``ExtractedProfile``.

    Args:
        pdf_bytes:  Raw bytes of the uploaded PDF file.
        session_id: UUID identifying the current user session. Used as the
            storage key under ``profiles/{session_id}.json``.

    Returns:
        A validated and persisted ``ExtractedProfile``.

    Raises:
        ValueError: If the PDF contains no extractable text (wraps
            ``PDFExtractionError``) or if the LLM response cannot be
            parsed into a valid profile.
    """
    # Step 1 — extract raw text from the PDF
    try:
        raw_text = extract_pdf_text(pdf_bytes)
    except PDFExtractionError as exc:
        raise ValueError(
            f"Could not extract text from PDF: {exc.reason}"
        ) from exc

    # Step 2 — use the LLM agent to parse the text into structured fields
    agent = create_profile_agent()

    prompt = (
        "Parse the following resume and return a JSON object with the keys "
        "'skills', 'experience_entries', and 'education_details' as described "
        "in your instructions.\n\n"
        f"RESUME TEXT:\n{raw_text}"
    )

    agent_result = agent(prompt)

    # Step 3 — convert the agent response to an ExtractedProfile
    # Handle raw Strands dict format: {"role": "assistant", "content": [{"text": "..."}]}
    import json as _j, re as _re
    raw_response = str(agent_result)
    if raw_response.strip().startswith("{") and '"content"' in raw_response:
        try:
            _parsed = _j.loads(raw_response)
            for _block in _parsed.get("content", []):
                if isinstance(_block, dict) and "text" in _block:
                    raw_response = _block["text"].strip()
                    break
        except Exception:
            pass
    raw_response = _re.sub(r"```(?:json)?\s*", "", raw_response, flags=_re.IGNORECASE).strip().rstrip("`").strip()

    profile = _parse_llm_response(raw_response, session_id, raw_text)

    # Step 4 — persist to local storage
    save_json(profiles_dir(), session_id, profile)

    # Step 5 — return
    return profile
