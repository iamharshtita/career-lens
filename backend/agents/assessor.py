"""
backend/agents/assessor.py

Assessor Agent — CareerLens

Computes an overall fit score (0–100) by running three specialised
dimension-scorer sub-agents in sequence and combining their outputs with
fixed weights:

    fit_score = round(0.50 * skills_coverage
                    + 0.30 * experience_relevance
                    + 0.20 * qualification_match)
    fit_score = max(0, min(100, fit_score))   # clamped to [0, 100]

The three scorers are independent Strands Agent instances, each with its own
focused system prompt.  They are invoked sequentially — a Strands Swarm
import is attempted but gracefully falls back to plain sequential calls if
the swarm sub-module is unavailable in the installed SDK version.

Public API
----------
compute_fit_score(
    parsed_job      : ParsedJob,
    profile         : ExtractedProfile,
    skill_gaps      : list[SkillGap],
    learning_path   : list[LearningStep],
) -> AnalysisResult
    The primary entry point for task 4.8.  Returns a fully populated
    AnalysisResult.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from strands import Agent

from agents.model_factory import get_model

try:
    from models.schemas import (
        AnalysisResult,
        ExtractedProfile,
        LearningStep,
        ParsedJob,
        SkillGap,
    )
except ModuleNotFoundError:
    from backend.models.schemas import (  # type: ignore[no-redef]
        AnalysisResult,
        ExtractedProfile,
        LearningStep,
        ParsedJob,
        SkillGap,
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration (shared across all scorer agents)
# ---------------------------------------------------------------------------


def _make_model():
    """Return a fresh model instance using the configured LLM provider."""
    return get_model()


# ---------------------------------------------------------------------------
# System prompts for each dimension scorer
# ---------------------------------------------------------------------------

SKILLS_COVERAGE_SYSTEM_PROMPT = """You are an expert technical recruiter evaluating how well a candidate's skills match a job posting.

You will receive:
- A list of required skills for the job
- The candidate's current skill set
- Any identified skill gaps

Your task is to score the candidate's SKILLS COVERAGE on a scale of 0 to 100:
- 100: Candidate has ALL required skills — perfect match
- 75–99: Candidate has most required skills; minor gaps only
- 50–74: Candidate has roughly half the required skills; some meaningful gaps
- 25–49: Candidate has fewer than half the required skills; significant gaps
- 0–24: Candidate is missing most or all required skills

Respond with ONLY a JSON object in this exact format — no markdown, no prose:
{"score": <integer from 0 to 100>, "reasoning": "<one sentence>"}
"""

EXPERIENCE_RELEVANCE_SYSTEM_PROMPT = """You are a senior hiring manager evaluating how relevant a candidate's work experience is to a target job.

You will receive:
- The job title and employer
- The candidate's work-experience entries (titles, companies, durations, descriptions)

Your task is to score the candidate's EXPERIENCE RELEVANCE on a scale of 0 to 100:
- 100: Experience is directly in the same role/industry — highly relevant
- 75–99: Strong relevant experience; closely aligned domain or seniority
- 50–74: Some relevant experience; partially aligned
- 25–49: Limited relevance; tangentially related background
- 0–24: Little to no relevant experience for this role

Respond with ONLY a JSON object in this exact format — no markdown, no prose:
{"score": <integer from 0 to 100>, "reasoning": "<one sentence>"}
"""

QUALIFICATION_MATCH_SYSTEM_PROMPT = """You are a credentialing specialist evaluating how well a candidate's education and certifications match a job's stated qualifications.

You will receive:
- The job's listed qualifications (degrees, certifications, years of experience, etc.)
- The candidate's education details

Your task is to score the candidate's QUALIFICATION MATCH on a scale of 0 to 100:
- 100: Candidate meets or exceeds all stated qualifications
- 75–99: Candidate meets most qualifications; minor shortfalls
- 50–74: Candidate meets roughly half the stated qualifications
- 25–49: Candidate meets fewer than half the qualifications
- 0–24: Candidate meets few or none of the stated qualifications

Respond with ONLY a JSON object in this exact format — no markdown, no prose:
{"score": <integer from 0 to 100>, "reasoning": "<one sentence>"}
"""

# ---------------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------------


def _create_skills_coverage_scorer() -> Agent:
    """Build and return the skills-coverage scorer Agent."""
    return Agent(
        model=_make_model(),
        system_prompt=SKILLS_COVERAGE_SYSTEM_PROMPT,
        callback_handler=None,
    )


def _create_experience_relevance_scorer() -> Agent:
    """Build and return the experience-relevance scorer Agent."""
    return Agent(
        model=_make_model(),
        system_prompt=EXPERIENCE_RELEVANCE_SYSTEM_PROMPT,
        callback_handler=None,
    )


def _create_qualification_match_scorer() -> Agent:
    """Build and return the qualification-match scorer Agent."""
    return Agent(
        model=_make_model(),
        system_prompt=QUALIFICATION_MATCH_SYSTEM_PROMPT,
        callback_handler=None,
    )


# Module-level scorer instances (created lazily on first call to
# compute_fit_score so that import-time AWS credential errors surface only
# when the function is actually used, not at module load).
skills_coverage_scorer: Agent | None = None
experience_relevance_scorer: Agent | None = None
qualification_match_scorer: Agent | None = None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_skills_prompt(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
    skill_gaps: list[SkillGap],
) -> str:
    required = ", ".join(parsed_job.required_skills) or "(none listed)"
    candidate = ", ".join(profile.skills) or "(none listed)"
    gaps = ", ".join(g.skill for g in skill_gaps) or "(none — full coverage)"
    return (
        f"Job Title: {parsed_job.title}\n"
        f"Required Skills: {required}\n"
        f"Candidate's Skills: {candidate}\n"
        f"Identified Skill Gaps: {gaps}\n\n"
        "Score the candidate's skills coverage (0–100)."
    )


def _build_experience_prompt(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
) -> str:
    lines = [
        f"Target Job Title: {parsed_job.title}",
        f"Employer: {parsed_job.employer}",
        "",
        "Candidate's Work Experience:",
    ]
    if profile.experience_entries:
        for entry in profile.experience_entries:
            dur = f"{entry.duration_months} months" if entry.duration_months is not None else "unknown duration"
            lines.append(f"  • {entry.title} at {entry.company} ({dur}): {entry.description}")
    else:
        lines.append("  (no work experience listed)")
    lines.append("")
    lines.append("Score the candidate's experience relevance (0–100).")
    return "\n".join(lines)


def _build_qualification_prompt(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
) -> str:
    qualifications = "\n".join(f"  • {q}" for q in parsed_job.qualifications) or "  (none listed)"
    edu_lines: list[str] = []
    if profile.education_details:
        for edu in profile.education_details:
            field_str = f" in {edu.field}" if edu.field else ""
            year_str = f" ({edu.year})" if edu.year else ""
            edu_lines.append(f"  • {edu.degree}{field_str} — {edu.institution}{year_str}")
    else:
        edu_lines.append("  (no education details listed)")
    education = "\n".join(edu_lines)
    return (
        f"Job Qualifications Required:\n{qualifications}\n\n"
        f"Candidate's Education:\n{education}\n\n"
        "Score the candidate's qualification match (0–100)."
    )


# ---------------------------------------------------------------------------
# Score extraction helpers
# ---------------------------------------------------------------------------


def _extract_score(response: Any, dimension: str, fallback: int = 50) -> int:
    """Parse the integer score from a scorer agent's response.

    The agent is instructed to return ``{"score": <int>, "reasoning": "..."}``.
    This function is defensive — it attempts multiple extraction strategies
    and returns *fallback* if all fail, so a single scorer error never
    crashes the entire pipeline.

    Args:
        response:  Raw Strands AgentResult or string.
        dimension: Name of the scoring dimension (used in log messages only).
        fallback:  Score to return if parsing fails (default 50 = neutral).

    Returns:
        An integer in [0, 100].
    """
    raw = _extract_text(response)

    # Strategy 1: direct JSON parse
    try:
        cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip().rstrip("`").strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            payload = json.loads(cleaned[start : end + 1])
            score = int(payload["score"])
            return max(0, min(100, score))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass

    # Strategy 2: regex hunt for a bare integer after "score"
    match = re.search(r'"score"\s*:\s*(\d{1,3})', raw)
    if match:
        score = int(match.group(1))
        return max(0, min(100, score))

    # Strategy 3: first standalone integer in the response
    nums = re.findall(r'\b([0-9]{1,3})\b', raw)
    for n in nums:
        candidate = int(n)
        if 0 <= candidate <= 100:
            return candidate

    logger.warning(
        "%s scorer returned unparseable output (using fallback=%d): %r",
        dimension,
        fallback,
        raw[:200],
    )
    return fallback


def _extract_text(response: Any) -> str:
    """Extract plain text from a Strands AgentResult, handling raw dict format."""
    import json as _j, re as _re
    if hasattr(response, "message") and isinstance(response.message, str):
        text = response.message.strip()
    else:
        text = str(response).strip()
    if text.startswith("{") and chr(34) + "content" + chr(34) in text:
        try:
            parsed = _j.loads(text)
            for block in parsed.get("content", []):
                if isinstance(block, dict) and "text" in block:
                    text = block["text"].strip()
                    break
        except Exception:
            pass
    text = _re.sub(r"[`]{3}(?:json)?\s*", "", text, flags=_re.IGNORECASE).strip().rstrip(chr(96)).strip()
    return text


# ---------------------------------------------------------------------------
# Aggregation logic (pure function — easily unit-tested without AWS)
# ---------------------------------------------------------------------------


def aggregate_scores(
    skills_score: int,
    experience_score: int,
    qualification_score: int,
) -> int:
    """Combine three dimension scores into a single fit score.

    Weights:
        - skills_coverage       50 %
        - experience_relevance  30 %
        - qualification_match   20 %

    The result is rounded to the nearest integer and clamped to [0, 100].

    Args:
        skills_score:        Skills coverage sub-score (0–100).
        experience_score:    Experience relevance sub-score (0–100).
        qualification_score: Qualification match sub-score (0–100).

    Returns:
        Overall fit score as an integer in [0, 100].
    """
    raw = 0.50 * skills_score + 0.30 * experience_score + 0.20 * qualification_score
    return max(0, min(100, round(raw)))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_fit_score(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
    skill_gaps: list[SkillGap],
    learning_path: list[LearningStep],
) -> AnalysisResult:
    """Run the three-dimensional scoring pipeline and return an AnalysisResult.

    The function creates (or reuses) the three scorer agents, invokes them
    sequentially with job/profile context, aggregates their scores with the
    50/30/20 weighting scheme, and packages everything into an
    :class:`~models.schemas.AnalysisResult`.

    Args:
        parsed_job:    Structured job posting from the Job Parser Agent.
        profile:       Candidate profile from the Profile Agent.
        skill_gaps:    Ranked skill gaps from the Gap Analyzer Agent.
        learning_path: Learning steps from the Learning Path Agent.

    Returns:
        A fully populated :class:`~models.schemas.AnalysisResult` with
        ``fit_score`` guaranteed to be in [0, 100].
    """
    global skills_coverage_scorer, experience_relevance_scorer, qualification_match_scorer

    # Lazy-initialise scorer agents
    if skills_coverage_scorer is None:
        skills_coverage_scorer = _create_skills_coverage_scorer()
    if experience_relevance_scorer is None:
        experience_relevance_scorer = _create_experience_relevance_scorer()
    if qualification_match_scorer is None:
        qualification_match_scorer = _create_qualification_match_scorer()

    # ------------------------------------------------------------------
    # Dimension 1 — Skills Coverage (weight: 50 %)
    # ------------------------------------------------------------------
    logger.info("Running skills coverage scorer for job %s …", parsed_job.job_id)
    skills_prompt = _build_skills_prompt(parsed_job, profile, skill_gaps)
    try:
        skills_response = skills_coverage_scorer(skills_prompt)
        skills_score = _extract_score(skills_response, "skills_coverage")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skills coverage scorer failed (%s); using fallback 50.", exc)
        skills_score = 50

    # ------------------------------------------------------------------
    # Dimension 2 — Experience Relevance (weight: 30 %)
    # ------------------------------------------------------------------
    logger.info("Running experience relevance scorer for job %s …", parsed_job.job_id)
    experience_prompt = _build_experience_prompt(parsed_job, profile)
    try:
        experience_response = experience_relevance_scorer(experience_prompt)
        experience_score = _extract_score(experience_response, "experience_relevance")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Experience relevance scorer failed (%s); using fallback 50.", exc)
        experience_score = 50

    # ------------------------------------------------------------------
    # Dimension 3 — Qualification Match (weight: 20 %)
    # ------------------------------------------------------------------
    logger.info("Running qualification match scorer for job %s …", parsed_job.job_id)
    qualification_prompt = _build_qualification_prompt(parsed_job, profile)
    try:
        qualification_response = qualification_match_scorer(qualification_prompt)
        qualification_score = _extract_score(qualification_response, "qualification_match")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Qualification match scorer failed (%s); using fallback 50.", exc)
        qualification_score = 50

    # ------------------------------------------------------------------
    # Aggregate
    # ------------------------------------------------------------------
    fit_score = aggregate_scores(skills_score, experience_score, qualification_score)

    logger.info(
        "Fit score for job %s: %d (skills=%d, experience=%d, qualifications=%d)",
        parsed_job.job_id,
        fit_score,
        skills_score,
        experience_score,
        qualification_score,
    )

    # ------------------------------------------------------------------
    # Build and return AnalysisResult
    # ------------------------------------------------------------------
    result_id = parsed_job.job_id  # result_id == job_id per design spec

    return AnalysisResult(
        result_id=result_id,
        job_id=parsed_job.job_id,
        session_id=profile.session_id,
        fit_score=fit_score,
        skill_gaps=skill_gaps,
        learning_path=learning_path,
        analyzed_at=datetime.now(timezone.utc),
        rescored_at=None,
    )
