"""
backend/agents/orchestrator.py — CareerLens pipeline orchestrator.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from models.schemas import (
    AnalysisResult, ExtractedProfile, LearningStep, ParsedJob, SkillGap,
)
from storage.local_store import (
    jobs_dir, load_json, profiles_dir, results_dir, save_json,
)
from agents.job_parser import parse_job
from agents.gap_analyzer import analyze_gaps
from agents.learning_path import build_learning_path

logger = logging.getLogger(__name__)

# Callback type: (event_type, stage, message)
# event_type: "progress" (stage started) | "log" (sub-activity within a stage)
ProgressCallback = Callable[[str, str, str], None]


class PipelineError(Exception):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"[{stage}] {message}")
        self.stage = stage
        self.message = message


def _emit(cb: ProgressCallback | None, event_type: str, stage: str, message: str) -> None:
    if cb is None:
        return
    try:
        cb(event_type, stage, message)
    except Exception:
        pass


def compute_fit_score(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
    skill_gaps: list[SkillGap],
    learning_path: list[LearningStep],
) -> int:
    total_required = len(parsed_job.required_skills)
    if total_required > 0:
        covered = max(0, min(total_required - len(skill_gaps), total_required))
        skills_score = (covered / total_required) * 100.0
    else:
        skills_score = 100.0

    total_months = sum((e.duration_months or 0) for e in profile.experience_entries)
    experience_score = min(total_months / 120, 1.0) * 100.0
    qualification_score = 100.0 if profile.education_details else 50.0

    return max(0, min(100, round(
        0.50 * skills_score + 0.30 * experience_score + 0.20 * qualification_score
    )))


def _load_profile(session_id: str) -> ExtractedProfile:
    raw = load_json(profiles_dir(), session_id)
    if raw is None:
        raise PipelineError("profile_loading",
            f"No profile found for session_id={session_id!r}. Please upload your resume first.")
    try:
        return ExtractedProfile.model_validate(raw)
    except Exception as exc:
        raise PipelineError("profile_loading", f"Stored profile is corrupted: {exc}") from exc


def _load_parsed_job(job_id: str) -> ParsedJob:
    raw = load_json(jobs_dir(), job_id)
    if raw is None:
        raise PipelineError("job_parsing", f"No saved job found for job_id={job_id!r}.")
    try:
        return ParsedJob.model_validate(raw)
    except Exception as exc:
        raise PipelineError("job_parsing", f"Saved job is corrupted: {exc}") from exc


def _run_from_gap_analysis(
    parsed_job: ParsedJob,
    profile: ExtractedProfile,
    cb: ProgressCallback | None,
    analyzed_at: datetime,
    rescored_at: datetime | None,
) -> AnalysisResult:

    # --- Stage 3: Gap analysis ---
    _emit(cb, "progress", "gap_analysis", "Analyzing skill gaps...")
    _emit(cb, "log", "gap_analysis", f"🔍 Comparing {len(parsed_job.required_skills)} required skills vs {len(profile.skills)} profile skills")
    try:
        skill_gaps = analyze_gaps(parsed_job, profile)
        _emit(cb, "log", "gap_analysis", f"🤖 Gap Analyzer Agent reasoning about criticality...")
        if skill_gaps:
            critical = sum(1 for g in skill_gaps if g.criticality == "critical")
            important = sum(1 for g in skill_gaps if g.criticality == "important")
            _emit(cb, "log", "gap_analysis", f"✅ Found {len(skill_gaps)} gaps — {critical} critical, {important} important")
        else:
            _emit(cb, "log", "gap_analysis", "✅ No skill gaps — your profile fully covers this role!")
    except Exception as exc:
        raise PipelineError("gap_analysis", f"Gap analysis failed: {exc}") from exc

    # --- Stage 4: Learning path ---
    _emit(cb, "progress", "learning_path", "Building learning path...")
    _emit(cb, "log", "learning_path", f"📚 Learning Path Agent curating resources for {len(skill_gaps)} skill gaps")
    _emit(cb, "log", "learning_path", "🎬 Searching YouTube for tutorial videos...")
    _emit(cb, "log", "learning_path", "🎓 Building Coursera course links...")
    try:
        learning_path = build_learning_path(skill_gaps)
        _emit(cb, "log", "learning_path", f"✅ Built learning path with {len(learning_path)} steps")
    except Exception as exc:
        raise PipelineError("learning_path", f"Learning path construction failed: {exc}") from exc

    # --- Stage 5: Scoring ---
    _emit(cb, "progress", "scoring", "Computing fit score...")
    _emit(cb, "log", "scoring", "⚖️  Assessor Agent calculating weighted fit score...")
    _emit(cb, "log", "scoring", f"   → Skills coverage: {len(parsed_job.required_skills) - len(skill_gaps)}/{len(parsed_job.required_skills)} required skills matched")
    _emit(cb, "log", "scoring", f"   → Experience: {len(profile.experience_entries)} entries found")
    _emit(cb, "log", "scoring", f"   → Education: {'found' if profile.education_details else 'not found'}")
    try:
        fit_score = compute_fit_score(parsed_job, profile, skill_gaps, learning_path)
        _emit(cb, "log", "scoring", f"✅ Final fit score: {fit_score}%")
    except Exception as exc:
        raise PipelineError("scoring", f"Fit score computation failed: {exc}") from exc

    result = AnalysisResult(
        result_id=parsed_job.job_id,
        job_id=parsed_job.job_id,
        session_id=profile.session_id,
        fit_score=fit_score,
        skill_gaps=skill_gaps,
        learning_path=learning_path,
        analyzed_at=analyzed_at,
        rescored_at=rescored_at,
    )
    save_json(results_dir(), parsed_job.job_id, result)
    return result


def run_pipeline(
    job_url: str,
    session_id: str,
    progress_callback: ProgressCallback | None = None,
) -> AnalysisResult:
    cb = progress_callback
    logger.info("Starting pipeline — job_url=%s session_id=%s", job_url, session_id)

    # --- Stage 1: Job parsing ---
    _emit(cb, "progress", "job_parsing", "Fetching job posting...")
    _emit(cb, "log", "job_parsing", f"🌐 Job Parser Agent fetching: {job_url[:60]}...")

    # Detect platform for informative log
    if "greenhouse.io" in job_url:
        _emit(cb, "log", "job_parsing", "🔑 Detected Greenhouse — using JSON API")
    elif "lever.co" in job_url:
        _emit(cb, "log", "job_parsing", "🔑 Detected Lever — using JSON API")
    elif "workday" in job_url:
        _emit(cb, "log", "job_parsing", "🔑 Detected Workday — fetching with browser headers")
    elif "linkedin.com" in job_url:
        _emit(cb, "log", "job_parsing", "🔑 Detected LinkedIn — fetching job description")
    else:
        _emit(cb, "log", "job_parsing", "🔑 Fetching job page content...")

    job_result = parse_job(job_url)

    if isinstance(job_result, dict):
        error_type = job_result.get("error_type", "fetch_failed")
        error_msg = job_result.get("error", "Unknown error")
        raise PipelineError("job_parsing", f"Job parsing failed ({error_type}): {error_msg}")

    parsed_job: ParsedJob = job_result
    _emit(cb, "log", "job_parsing", f"✅ Parsed: \"{parsed_job.title}\" at {parsed_job.employer}")
    _emit(cb, "log", "job_parsing", f"   → Found {len(parsed_job.required_skills)} required skills")
    save_json(jobs_dir(), parsed_job.job_id, parsed_job)

    # --- Stage 2: Profile loading ---
    _emit(cb, "progress", "profile_loading", "Loading profile...")
    profile = _load_profile(session_id)
    _emit(cb, "log", "profile_loading", f"✅ Loaded profile with {len(profile.skills)} skills, {len(profile.experience_entries)} experience entries")

    analyzed_at = datetime.now(tz=timezone.utc)
    return _run_from_gap_analysis(
        parsed_job=parsed_job,
        profile=profile,
        cb=cb,
        analyzed_at=analyzed_at,
        rescored_at=None,
    )


def rescore_job(
    job_id: str,
    session_id: str,
    progress_callback: ProgressCallback | None = None,
) -> AnalysisResult:
    cb = progress_callback
    logger.info("Rescoring — job_id=%s session_id=%s", job_id, session_id)
    parsed_job = _load_parsed_job(job_id)
    _emit(cb, "progress", "profile_loading", "Loading profile...")
    profile = _load_profile(session_id)
    _emit(cb, "log", "profile_loading", f"✅ Loaded updated profile with {len(profile.skills)} skills")

    existing_raw = load_json(results_dir(), job_id)
    if existing_raw and "analyzed_at" in existing_raw:
        try:
            analyzed_at = datetime.fromisoformat(existing_raw["analyzed_at"])
        except (ValueError, TypeError):
            analyzed_at = datetime.now(tz=timezone.utc)
    else:
        analyzed_at = datetime.now(tz=timezone.utc)

    return _run_from_gap_analysis(
        parsed_job=parsed_job,
        profile=profile,
        cb=cb,
        analyzed_at=analyzed_at,
        rescored_at=datetime.now(tz=timezone.utc),
    )
