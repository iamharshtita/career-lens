"""
backend/agents/job_parser.py

Job Parser Agent for CareerLens.

The Job Parser is a real Strands agentic loop — the LLM decides which URLs
to fetch, calls http_request as a tool, reads the response, and iterates
until it has enough content to extract a structured job posting.

The agent's system prompt teaches it platform-specific strategies:
  - Greenhouse: prefer the JSON API over the board HTML
  - Lever: prefer the public API
  - Other platforms: fetch directly, retry with alternate URLs if needed

This makes the fetch logic genuinely agentic — the model reasons about
what it received and decides the next action, rather than hardcoded Python
branching.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from strands import Agent
from strands_tools import http_request

from agents.model_factory import get_model

from models.schemas import ParsedJob

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — teaches the agent how to handle different job boards
# ---------------------------------------------------------------------------

JOB_PARSER_SYSTEM_PROMPT = """You are a Job Parser Agent. Your job is to fetch a job posting URL and extract structured information from it.

You have access to the http_request tool. Use it to fetch web pages.

## Strategy by platform

### Greenhouse (job-boards.greenhouse.io or boards.greenhouse.io)
For embed URLs like:
  https://job-boards.greenhouse.io/embed/job_app?for=COMPANY&jr_id=JOB_ID
Or board URLs like:
  https://boards.greenhouse.io/COMPANY/jobs/JOB_ID

FIRST try the Greenhouse JSON API — it returns clean structured data:
  https://boards-api.greenhouse.io/v1/boards/COMPANY/jobs/JOB_ID

If the JSON API returns 404, try listing all jobs:
  https://boards-api.greenhouse.io/v1/boards/COMPANY/jobs
Then find the matching job by id.

### Lever (jobs.lever.co)
For URLs like: https://jobs.lever.co/COMPANY/UUID
Try the public API first:
  https://api.lever.co/v0/postings/COMPANY/UUID

### LinkedIn, Workday, and other platforms
Fetch the URL directly using http_request with convert_to_markdown=true.
If the content looks empty or like a login wall, try fetching the URL without parameters.

## What to extract
Once you have the job content, extract:
- title: exact job title
- employer: company name
- required_skills: list of technical skills, tools, languages explicitly required
- qualifications: degrees, certifications, years of experience mentioned

## Output format
After fetching and extracting, return ONLY this JSON (no markdown, no explanation):
{
  "title": "...",
  "employer": "...",
  "required_skills": ["skill1", "skill2"],
  "qualifications": ["qualification1"],
  "raw_html": "first 500 chars of fetched content"
}

If after all attempts the page has no job content (login wall, CAPTCHA, empty):
{"error": "No job content identified on the page", "error_type": "insufficient_content"}

If the URL is unreachable:
{"error": "Could not fetch the URL", "error_type": "fetch_failed"}

## Important
- Be persistent — if the first fetch doesn't have job content, reason about why and try an alternative URL
- For Greenhouse embed URLs, always extract the company name (for=COMPANY) and job id (jr_id=ID) from the URL parameters and use the API
- Always return valid JSON as your final response
"""

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_job(url: str) -> ParsedJob | dict[str, Any]:
    """Use a Strands Agent with http_request tool to fetch and parse a job posting.
    
    The agent drives the fetch strategy itself — it decides which URLs to call,
    reads the responses, and iterates until it has enough content.
    This is the primary agentic approach.
    """
    logger.info("Job Parser Agent starting for URL: %s", url)

    agent = Agent(
        model=get_model(),
        tools=[http_request],
        system_prompt=JOB_PARSER_SYSTEM_PROMPT,
        callback_handler=None,
    )

    prompt = f"""Parse this job posting URL and return the structured JSON:

URL: {url}

Remember:
- If this is a Greenhouse URL, extract the company name and job id from the URL and use the Greenhouse JSON API
- Be persistent — fetch, read the response, decide if you have enough information, and retry if needed
- Return ONLY the final JSON object"""

    try:
        response = agent(prompt)
        raw = _extract_text(response)
    except Exception as exc:
        logger.exception("Job Parser Agent failed for URL %s", url)
        return {"error": f"Agent execution failed: {exc}", "error_type": "fetch_failed"}

    # Parse JSON from agent response
    payload = _parse_json(raw)
    if payload is None:
        return {"error": "Agent returned non-JSON output", "error_type": "insufficient_content"}

    # Check for explicit error response
    if "error" in payload and "error_type" in payload:
        return payload

    # Build and return ParsedJob
    try:
        return ParsedJob(
            job_id=str(uuid.uuid4()),
            url=url,
            title=payload.get("title", ""),
            employer=payload.get("employer", ""),
            required_skills=payload.get("required_skills", []),
            qualifications=payload.get("qualifications", []),
            raw_html=payload.get("raw_html", "")[:2000],
            parsed_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.warning("ParsedJob construction failed: %s", exc)
        return {"error": f"Schema validation failed: {exc}", "error_type": "insufficient_content"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(response: Any) -> str:
    """Extract plain text from a Strands AgentResult."""
    import json as _j
    if hasattr(response, "message") and isinstance(response.message, str):
        text = response.message.strip()
    else:
        text = str(response).strip()
    # Handle raw Strands dict: {"role": "assistant", "content": [{"text": "..."}]}
    if text.startswith("{") and '"content"' in text:
        try:
            parsed = _j.loads(text)
            for block in parsed.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    text = block["text"].strip()
                    break
        except Exception:
            pass
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip().rstrip("`").strip()
    return text


def _parse_json(text: str) -> dict[str, Any] | None:
    """Extract and parse the first JSON object from text."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first { ... } block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None
