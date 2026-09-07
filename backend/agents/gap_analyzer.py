"""
gap_analyzer.py — Gap Analyzer Agent for CareerLens.

Identifies the skill gaps between a job posting's requirements and a
candidate's profile, then annotates each gap with a criticality level and
ranks them so the most important gaps appear first.

Public API
----------
create_gap_analyzer_agent() -> Agent
    Factory that constructs and returns a configured Strands Agent.

analyze_gaps(parsed_job, profile) -> list[SkillGap]
    Convenience function that builds the agent and runs the full gap analysis
    pipeline, returning a list of SkillGap objects sorted by rank (ascending).

Pipeline
--------
1. Normalize skill names from both sources (case-insensitive, synonym-aware).
2. Compute the set difference: required_skills − profile_skills.
3. Use LLM reasoning to assess about each gap's criticality
   for the specific job title and industry.
4. Annotate every gap with "critical" | "important" | "nice-to-have".
5. Sort by criticality order (critical → important → nice-to-have) and assign
   integer ranks starting at 1.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from strands import Agent

from agents.model_factory import get_model


# Import from the models package.  When this module is executed from the
# backend/ working directory the package is on the path; when run from the
# project root, sys.path adjustments in main.py ensure the same.
try:
    from models.schemas import ExtractedProfile, ParsedJob, SkillGap
except ModuleNotFoundError:
    # Support running from the project root during tests
    from backend.models.schemas import ExtractedProfile, ParsedJob, SkillGap

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Criticality ordering — lower index = higher priority
# ---------------------------------------------------------------------------

_CRITICALITY_ORDER: dict[str, int] = {
    "critical": 0,
    "important": 1,
    "nice-to-have": 2,
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

GAP_ANALYZER_SYSTEM_PROMPT = """You are an expert career coach and technical recruiter specializing in skill gap analysis.

Your task is to:
1. Analyze a job posting's required skills against a candidate's existing skills.
2. Identify skills the candidate is missing (the "gaps").
3. Assess the criticality of each gap for the specific role and industry.

## Normalization Rules
- Treat skills as case-insensitive (e.g., "python" == "Python" == "PYTHON").
- Merge recognized synonyms into a single canonical name:
  - "ML" / "Machine Learning" / "machine-learning" → "Machine Learning"
  - "JS" / "JavaScript" → "JavaScript"
  - "k8s" / "Kubernetes" → "Kubernetes"
  - "tf" / "TensorFlow" → "TensorFlow"
  - "NLP" / "Natural Language Processing" → "Natural Language Processing"
  Apply the same principle for any other common abbreviations you recognize.

## Criticality Definitions
- **critical**: The job title or core responsibilities CANNOT be performed without this skill.
  The candidate would very likely be screened out in the first round.
- **important**: The skill is explicitly listed as required and would significantly help in the role,
  but the gap might be bridgeable with a short ramp-up period.
- **nice-to-have**: The skill is listed as a plus, preferred, or bonus. Its absence is unlikely
  to disqualify an otherwise strong candidate.

## Output Format
Always respond with ONLY a valid JSON array — no markdown, no explanation, no extra text.
Each element must be an object with exactly these keys:
  - "skill"       : string — the canonical (normalized) skill name
  - "criticality" : string — one of "critical", "important", "nice-to-have"

Example:
[
  {"skill": "Kubernetes", "criticality": "critical"},
  {"skill": "Terraform",  "criticality": "important"},
  {"skill": "Helm",       "criticality": "nice-to-have"}
]

If there are no skill gaps, return an empty JSON array: []

CRITICAL: Your entire response must be ONLY the JSON array. Start with [ and end with ]. No other text.
"""

# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_gap_analyzer_agent() -> Agent:
    """Construct and return a configured Gap Analyzer Strands Agent.

    The agent uses:
    - Model from model_factory.get_model() based on LLM_PROVIDER env var.
    - LLM native reasoning about
      criticality.


    Returns:
        A ready-to-invoke Strands ``Agent`` instance.
    """
    return Agent(
        model=get_model(),
        tools=[],
        system_prompt=GAP_ANALYZER_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Core analysis logic — kept outside the agent so it can be unit-tested
# without a live Bedrock connection
# ---------------------------------------------------------------------------


def _normalize_skills(skills: list[str]) -> set[str]:
    """Lowercase and strip all skills for deterministic set comparison."""
    return {s.strip().lower() for s in skills if s.strip()}


def _compute_raw_gaps(
    required: list[str],
    profile: list[str],
) -> list[str]:
    """Return required skills that are not present in the profile.

    Comparison is case-insensitive.  The original casing from *required* is
    preserved in the returned list so the LLM receives human-readable names.
    """
    profile_lower = _normalize_skills(profile)
    gaps: list[str] = []
    seen_lower: set[str] = set()
    for skill in required:
        key = skill.strip().lower()
        if key and key not in profile_lower and key not in seen_lower:
            gaps.append(skill.strip())
            seen_lower.add(key)
    return gaps


def _parse_gap_json(raw: str) -> list[dict[str, str]]:
    """Extract and parse the JSON array from an LLM response string.

    The model is instructed to return only a JSON array, but may occasionally
    wrap it in markdown code fences.  This function strips fences before
    parsing.

    Args:
        raw: Raw string returned by the LLM.

    Returns:
        A list of dicts, each containing "skill" and "criticality" keys.

    Raises:
        ValueError: If the string does not contain a parseable JSON array.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()

    # Find the first '[' and last ']' to isolate the JSON array
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass

    # Sometimes the LLM wraps the array in an object like {"gaps": [...]}
    obj_start = cleaned.find("{")
    obj_end = cleaned.rfind("}")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        try:
            obj = json.loads(cleaned[obj_start : obj_end + 1])
            # Find the first list value in the object
            for v in obj.values():
                if isinstance(v, list):
                    return v
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No JSON array found in LLM response: {raw!r}")


def _build_skill_gaps(annotated: list[dict[str, str]]) -> list[SkillGap]:
    """Convert annotated gap dicts to sorted, ranked SkillGap objects.

    Sorts by criticality order (critical → important → nice-to-have) and
    assigns integer ranks starting at 1.

    Args:
        annotated: List of dicts with "skill" and "criticality" keys.

    Returns:
        A list of :class:`SkillGap` objects sorted by rank ascending.
    """
    # Validate and normalise criticality values; default unknown ones to
    # "important" so we don't crash on unexpected LLM output.
    validated: list[dict[str, str]] = []
    for item in annotated:
        skill = str(item.get("skill", "")).strip()
        criticality = str(item.get("criticality", "")).strip().lower()
        if not skill:
            continue
        if criticality not in _CRITICALITY_ORDER:
            logger.warning(
                "Unexpected criticality %r for skill %r; defaulting to 'important'.",
                criticality,
                skill,
            )
            criticality = "important"
        validated.append({"skill": skill, "criticality": criticality})

    # Sort by criticality tier, then alphabetically within each tier for
    # deterministic output.
    validated.sort(key=lambda x: (_CRITICALITY_ORDER[x["criticality"]], x["skill"].lower()))

    return [
        SkillGap(skill=item["skill"], rank=idx + 1, criticality=item["criticality"])  # type: ignore[arg-type]
        for idx, item in enumerate(validated)
    ]


# ---------------------------------------------------------------------------
# Public convenience function
# ---------------------------------------------------------------------------


def analyze_gaps(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
) -> list[SkillGap]:
    """Analyze the skill gaps between a job posting and a candidate profile.

    This is the primary entry point for task 4.4.  It:
    1. Computes the raw set difference (required − profile) locally for speed.
    2. Calls the Gap Analyzer Agent with the full context so the LLM can
       normalize synonyms and assign criticality labels.
    3. Returns a ``list[SkillGap]`` sorted by rank ascending (rank 1 = most
       critical).

    If the LLM returns an empty gap list (i.e., the profile fully covers all
    requirements), an empty list is returned without error.

    Args:
        parsed_job:  The structured job posting produced by the Job Parser Agent.
        profile:     The candidate's extracted resume profile.

    Returns:
        A list of :class:`SkillGap` objects, sorted by ``rank`` ascending.

    Raises:
        RuntimeError: If the LLM response cannot be parsed after two attempts.
    """
    # ------------------------------------------------------------------
    # Step 1: Fast local set-difference to build the candidate gap list.
    # This gives the LLM a focused, pre-filtered set rather than all skills.
    # ------------------------------------------------------------------
    raw_gaps = _compute_raw_gaps(parsed_job.required_skills, profile.skills)
    logger.info(
        "Raw skill gaps for session %s / job %s: %s",
        profile.session_id,
        parsed_job.job_id,
        raw_gaps,
    )

    if not raw_gaps:
        logger.info("No skill gaps detected — profile fully covers job requirements.")
        return []

    # ------------------------------------------------------------------
    # Step 2: Build prompt context and invoke the agent.
    # ------------------------------------------------------------------
    prompt = _build_analysis_prompt(parsed_job, profile, raw_gaps)
    agent = create_gap_analyzer_agent()

    try:
        response = agent(prompt)
        # Strands Agent returns an AgentResult; extract the string content.
        raw_text = _extract_agent_text(response)
        annotated = _parse_gap_json(raw_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "First gap analysis attempt failed (%s); retrying with simplified prompt.",
            exc,
        )
        # Retry with a simpler, more direct prompt
        retry_prompt = _build_retry_prompt(raw_gaps, parsed_job.title)
        try:
            response = agent(retry_prompt)
            raw_text = _extract_agent_text(response)
            annotated = _parse_gap_json(raw_text)
        except Exception as retry_exc:
            logger.warning(
                "Both LLM attempts failed (%s); falling back to raw gap list.", retry_exc
            )
            # Hard fallback: return raw gaps with default criticality = "important"
            return _build_skill_gaps(
                [{"skill": g, "criticality": "important"} for g in raw_gaps]
            )

    # ------------------------------------------------------------------
    # Step 3: Convert to SkillGap objects, sort, and assign ranks.
    # ------------------------------------------------------------------
    gaps = _build_skill_gaps(annotated)
    logger.info(
        "Gap analysis complete: %d gaps identified for job %s.",
        len(gaps),
        parsed_job.job_id,
    )
    return gaps


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_analysis_prompt(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
    raw_gaps: list[str],
) -> str:
    """Build the full analysis prompt for the agent."""
    profile_skills_str = ", ".join(profile.skills) if profile.skills else "(none listed)"
    required_skills_str = (
        ", ".join(parsed_job.required_skills) if parsed_job.required_skills else "(none listed)"
    )
    gaps_str = ", ".join(raw_gaps)

    experience_summary = _summarize_experience(profile)

    return f"""Analyze skill gaps for this job application.

## Job Details
- Title: {parsed_job.title}
- Employer: {parsed_job.employer}
- Required Skills: {required_skills_str}
- Qualifications: {"; ".join(parsed_job.qualifications) if parsed_job.qualifications else "(none listed)"}

## Candidate Profile
- Current Skills: {profile_skills_str}
- Experience Summary: {experience_summary}

## Identified Raw Gaps (required but not in profile)
{gaps_str}

## Instructions
For each skill in the "Identified Raw Gaps" list above:
1. Normalize its name (fix abbreviations, capitalize properly).
2. Assess its criticality for the role of "{parsed_job.title}" at {parsed_job.employer}.
3. Return ONLY a valid JSON array — no markdown, no prose.

Reason carefully about each gap's importance for the role before producing your final JSON output.
"""


def _build_retry_prompt(raw_gaps: list[str], job_title: str) -> str:
    """Simpler fallback prompt used on the second attempt."""
    gaps_json = json.dumps(raw_gaps)
    return f"""For the role of "{job_title}", classify each of the following skills as
"critical", "important", or "nice-to-have".

Skills to classify: {gaps_json}

Respond with ONLY a JSON array. Example format:
[
  {{"skill": "Kubernetes", "criticality": "critical"}},
  {{"skill": "Terraform",  "criticality": "important"}}
]
"""


def _summarize_experience(profile: ExtractedProfile) -> str:
    """Produce a compact one-line experience summary for prompt brevity."""
    if not profile.experience_entries:
        return "(no work experience listed)"
    parts: list[str] = []
    for entry in profile.experience_entries[:3]:  # cap at 3 for prompt size
        duration = (
            f"{entry.duration_months}mo" if entry.duration_months is not None else "?"
        )
        parts.append(f"{entry.title} @ {entry.company} ({duration})")
    return "; ".join(parts)


def _extract_agent_text(response: Any) -> str:
    """Extract plain text from a Strands AgentResult.

    Handles several formats the SDK may return:
    - AgentResult with .message attribute (string)
    - Raw dict: {"role": "assistant", "content": [{"text": "..."}]}
    - Plain string
    In all cases, tries to surface just the JSON array if present.
    """
    import json as _json

    # 1. Try .message attribute (clean string)
    if hasattr(response, "message") and isinstance(response.message, str):
        text = response.message
    else:
        text = str(response)

    # 2. If the string looks like a Strands raw response dict, parse it
    if text.strip().startswith("{") and '"content"' in text:
        try:
            parsed = _json.loads(text)
            content = parsed.get("content", [])
            if content and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        text = block["text"]
                        break
        except (_json.JSONDecodeError, AttributeError):
            pass

    # 3. Strip markdown code fences (```json ... ```)
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip().rstrip("`").strip()

    return text
