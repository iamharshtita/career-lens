"""
backend/agents

Agent package for CareerLens.

Exports the public entry-point functions from each agent module so that
router and orchestrator code can use clean top-level imports:

    from agents.orchestrator import run_pipeline, rescore_job
    from agents.profile_agent import parse_resume
    from agents.job_parser import parse_job
    from agents.gap_analyzer import analyze_gaps
    from agents.learning_path import build_learning_path
    from agents.assessor import assess
"""

from agents.gap_analyzer import analyze_gaps
from agents.job_parser import parse_job
from agents.learning_path import build_learning_path
from agents.orchestrator import PipelineError, rescore_job, run_pipeline
from agents.profile_agent import parse_resume

__all__ = [
    "analyze_gaps",
    "build_learning_path",
    "parse_job",
    "parse_resume",
    "PipelineError",
    "rescore_job",
    "run_pipeline",
]
