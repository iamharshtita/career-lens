"""
Pydantic v2 data models for the CareerLens application.

All models are used across the backend agents, API routers, storage layer,
and evaluation suite. Field validation ensures data integrity at every
layer boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Resume / Profile models
# ---------------------------------------------------------------------------


class ExperienceEntry(BaseModel):
    """A single work-experience entry extracted from a resume."""

    title: str = Field(..., description="Job title held by the candidate.")
    company: str = Field(..., description="Name of the employing organisation.")
    duration_months: int | None = Field(
        default=None,
        ge=0,
        description="Duration of the role in whole months. None if unknown.",
    )
    description: str = Field(
        ..., description="Free-text description of responsibilities and achievements."
    )


class EducationDetail(BaseModel):
    """A single education record extracted from a resume."""

    degree: str = Field(..., description="Degree or certification name (e.g. 'B.S.').")
    institution: str = Field(..., description="Name of the awarding institution.")
    year: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Graduation year. None if unknown.",
    )
    field: str | None = Field(
        default=None,
        description="Field of study or major. None if not specified.",
    )


class ExtractedProfile(BaseModel):
    """Structured representation of a candidate's resume after extraction."""

    session_id: str = Field(
        ..., description="UUID that scopes this profile to a user session."
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Deduplicated list of skills identified in the resume "
        "(e.g. ['Python', 'SQL', 'Docker']).",
    )
    experience_entries: list[ExperienceEntry] = Field(
        default_factory=list,
        description="Ordered list of work-experience entries (most recent first).",
    )
    education_details: list[EducationDetail] = Field(
        default_factory=list,
        description="List of education records found in the resume.",
    )
    raw_text: str = Field(
        ..., description="Full text extracted verbatim from the uploaded PDF."
    )
    extracted_at: datetime = Field(
        ..., description="UTC timestamp at which extraction was completed."
    )


# ---------------------------------------------------------------------------
# Job posting model
# ---------------------------------------------------------------------------


class ParsedJob(BaseModel):
    """Structured representation of a job posting after parsing."""

    job_id: str = Field(..., description="UUID assigned to this job posting.")
    url: str = Field(..., description="Original URL from which the posting was fetched.")
    title: str = Field(..., description="Job title as stated in the posting.")
    employer: str = Field(..., description="Name of the hiring organisation.")
    required_skills: list[str] = Field(
        default_factory=list,
        description="Skills explicitly required by the posting.",
    )
    qualifications: list[str] = Field(
        default_factory=list,
        description="Qualification bullets (degrees, certifications, years of experience, etc.).",
    )
    raw_html: str = Field(
        ..., description="Raw HTML of the fetched job-posting page."
    )
    parsed_at: datetime = Field(
        ..., description="UTC timestamp at which parsing was completed."
    )


# ---------------------------------------------------------------------------
# Gap analysis models
# ---------------------------------------------------------------------------


CriticalityLevel = Literal["critical", "important", "nice-to-have"]


class SkillGap(BaseModel):
    """A single skill that is required by the job but absent from the profile."""

    skill: str = Field(..., description="Normalised skill name.")
    rank: int = Field(
        ...,
        ge=1,
        description="Priority rank (1 = highest priority). Must be unique within a result.",
    )
    criticality: CriticalityLevel = Field(
        ...,
        description="Importance of this skill gap: 'critical', 'important', or 'nice-to-have'.",
    )


# ---------------------------------------------------------------------------
# Learning path models
# ---------------------------------------------------------------------------


class VideoResource(BaseModel):
    """A YouTube video recommended for closing a skill gap."""

    title: str = Field(..., description="Title of the video.")
    url: str = Field(..., description="Full YouTube watch URL.")
    channel: str = Field(..., description="YouTube channel name.")
    duration_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Video duration in seconds. None if unknown.",
    )


class CourseResource(BaseModel):
    """A Coursera course recommended for closing a skill gap."""

    title: str = Field(..., description="Course title.")
    url: str = Field(..., description="Full Coursera course URL.")
    provider: str = Field(
        ..., description="Institution or organisation offering the course."
    )
    duration_weeks: int | None = Field(
        default=None,
        ge=0,
        description="Estimated course duration in weeks. None if unknown.",
    )


class LearningStep(BaseModel):
    """Curated learning resources for a single skill gap."""

    skill_gap: str = Field(
        ..., description="The skill name this learning step addresses."
    )
    priority: int = Field(
        ...,
        ge=1,
        description="Display priority; mirrors the corresponding SkillGap.rank.",
    )
    youtube_resources: list[VideoResource] = Field(
        default_factory=list,
        description="Relevant YouTube videos. Empty list when no results were found.",
    )
    coursera_resources: list[CourseResource] = Field(
        default_factory=list,
        description="Relevant Coursera courses. Empty list when no results were found.",
    )


# ---------------------------------------------------------------------------
# Analysis result model
# ---------------------------------------------------------------------------


class AnalysisResult(BaseModel):
    """The full output produced by the multi-agent pipeline for one job/profile pair."""

    result_id: str = Field(
        ..., description="UUID for this result; matches job_id for easy lookup."
    )
    job_id: str = Field(..., description="UUID of the analysed job posting.")
    session_id: str = Field(..., description="UUID of the candidate's profile session.")
    fit_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Overall fit score in the range [0, 100] inclusive.",
    )
    skill_gaps: list[SkillGap] = Field(
        default_factory=list,
        description="Ranked list of skill gaps ordered by rank ascending (rank 1 first).",
    )
    learning_path: list[LearningStep] = Field(
        default_factory=list,
        description="Ordered learning path aligned with skill_gaps (priority 1 first).",
    )
    analyzed_at: datetime = Field(
        ..., description="UTC timestamp at which the initial analysis was completed."
    )
    rescored_at: datetime | None = Field(
        default=None,
        description="UTC timestamp of the most recent re-score, or None if never re-scored.",
    )

    @field_validator("skill_gaps")
    @classmethod
    def skill_gaps_ordered_by_rank(cls, v: list[SkillGap]) -> list[SkillGap]:
        """Ensure skill_gaps are sorted in ascending rank order."""
        if len(v) > 1:
            ranks = [gap.rank for gap in v]
            if ranks != sorted(ranks):
                raise ValueError(
                    "skill_gaps must be ordered by rank ascending "
                    f"(got ranks {ranks})."
                )
        return v

    @field_validator("learning_path")
    @classmethod
    def learning_path_ordered_by_priority(cls, v: list[LearningStep]) -> list[LearningStep]:
        """Ensure learning_path is sorted in ascending priority order."""
        if len(v) > 1:
            priorities = [step.priority for step in v]
            if priorities != sorted(priorities):
                raise ValueError(
                    "learning_path must be ordered by priority ascending "
                    f"(got priorities {priorities})."
                )
        return v


# ---------------------------------------------------------------------------
# Evaluation fixture model
# ---------------------------------------------------------------------------


class EvalFixture(BaseModel):
    """One job/resume pair used in the offline evaluation suite."""

    pair_id: str = Field(
        ...,
        pattern=r"^pair_\d{2}$",
        description="Fixture identifier in the format 'pair_NN' (e.g. 'pair_01').",
    )
    resume_text: str = Field(
        ..., description="Full plain-text resume for this fixture."
    )
    job_url: str = Field(
        ..., description="URL of the target job posting."
    )
    job_description: str = Field(
        ..., description="Full plain-text job description for offline use."
    )
    ground_truth_skills: list[str] = Field(
        default_factory=list,
        description="Human-annotated list of skills required by the job.",
    )
    ground_truth_gaps: list[str] = Field(
        default_factory=list,
        description="Ordered list of skill gaps annotated by relevance (most relevant first).",
    )
    ground_truth_fit_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Human-labelled fit score in the range [0, 100].",
    )
