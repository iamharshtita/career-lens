#!/usr/bin/env python3
"""
eval_runner.py — Compares the CareerLens multi-agent pipeline against the single-agent baseline.

Loads all 20 evaluation fixtures, runs both pipelines on each fixture, computes aggregate
and per-pair metrics, and writes a structured JSON report.

Usage:
  python eval/eval_runner.py --fixtures eval/fixtures/ --output eval/report.json

The report structure:
  {
    "aggregate": {
      "careerlens": {"mae": N, "precision": N, "recall": N, "ndcg": N, "relevance": N},
      "baseline":   {"mae": N, "precision": N, "recall": N, "ndcg": N}
    },
    "per_pair": [
      {
        "pair_id": "pair_01",
        "careerlens": { ... },
        "baseline":   { ... },
        "ground_truth_fit_score": N
      },
      ...
    ]
  }
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — allow importing from backend/ and eval/ regardless of cwd
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent          # career-lens/eval/
_PROJECT_ROOT = _SCRIPT_DIR.parent                     # career-lens/
_BACKEND_DIR = _PROJECT_ROOT / "backend"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Load .env from project root before any imports that might trigger AWS calls
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
except ImportError:
    pass

from eval.metrics import (   # noqa: E402
    fit_score_mae,
    ndcg_at_k,
    resource_relevance,
    skill_extraction_pr,
)


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def load_fixtures(fixtures_dir: Path) -> list[dict]:
    """
    Load all ``pair_NN.json`` fixture files from *fixtures_dir* sorted by pair_id.

    Args:
        fixtures_dir: Directory containing fixture JSON files.

    Returns:
        List of fixture dicts in ascending pair_id order.

    Raises:
        FileNotFoundError: If *fixtures_dir* does not exist.
        ValueError: If no fixture files are found.
    """
    if not fixtures_dir.exists():
        raise FileNotFoundError(f"Fixtures directory not found: {fixtures_dir}")

    fixture_files = sorted(fixtures_dir.glob("pair_*.json"))
    if not fixture_files:
        raise ValueError(f"No pair_*.json fixtures found in {fixtures_dir}")

    fixtures: list[dict] = []
    for path in fixture_files:
        with open(path, encoding="utf-8") as fh:
            fixtures.append(json.load(fh))

    return fixtures


# ---------------------------------------------------------------------------
# CareerLens pipeline runner
# ---------------------------------------------------------------------------

def run_careerlens(fixture: dict) -> dict:
    """
    Run the CareerLens multi-agent pipeline on a single fixture.

    Attempts to import and invoke the orchestrator directly. Catches all exceptions
    so a failure on one fixture does not abort the entire evaluation.

    Args:
        fixture: A fixture dict following the ``EvalFixture`` schema.

    Returns:
        A result dict containing at minimum:
          - ``fit_score``  (int | None)
          - ``skill_gaps`` (list[dict] | None)
          - ``learning_path`` (list[dict] | None)
          - ``error`` (str | None) — populated on failure
    """
    try:
        import uuid
        from agents.orchestrator import run_pipeline  # type: ignore[import]
        from agents.profile_agent import parse_resume  # type: ignore[import]

        # The pipeline needs a pre-uploaded profile identified by session_id.
        # For eval, we create a profile from resume_text by encoding it as fake PDF bytes
        # or by directly calling the profile agent with the text.
        # We use a temporary session_id for each fixture.
        session_id = str(uuid.uuid4())

        # Build a minimal ExtractedProfile directly from the fixture's resume_text
        # without going through PDF extraction (eval fixtures use plain text).
        from models.schemas import ExtractedProfile  # type: ignore[import]
        from storage.local_store import save_json, profiles_dir  # type: ignore[import]
        from strands import Agent  # type: ignore[import]
        from strands.models.bedrock import BedrockModel  # type: ignore[import]
        import json as _json
        from datetime import datetime, timezone

        model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")
        profile_agent = Agent(
            model=model,
            system_prompt="""Parse this resume text and return ONLY a JSON object with keys:
"skills" (list of strings), "experience_entries" (list of {title,company,duration_months,description}),
"education_details" (list of {degree,institution,year,field}).
Return ONLY valid JSON, no markdown.""",
            callback_handler=None,
        )
        response = profile_agent("RESUME TEXT:\n" + fixture["resume_text"])
        raw = str(response)
        # Unwrap Strands dict format if needed
        if raw.strip().startswith("{") and '"content"' in raw:
            try:
                parsed = _json.loads(raw)
                for block in parsed.get("content", []):
                    if isinstance(block, dict) and "text" in block:
                        raw = block["text"]
                        break
            except Exception:
                pass
        import re as _re
        raw = _re.sub(r"```(?:json)?\s*", "", raw, flags=_re.IGNORECASE).strip().rstrip("`")
        try:
            data = _json.loads(raw)
        except Exception:
            m = _re.search(r"\{.*\}", raw, _re.DOTALL)
            data = _json.loads(m.group()) if m else {"skills": [], "experience_entries": [], "education_details": []}

        profile = ExtractedProfile(
            session_id=session_id,
            skills=data.get("skills", []),
            experience_entries=[],
            education_details=[],
            raw_text=fixture["resume_text"],
            extracted_at=datetime.now(timezone.utc),
        )
        save_json(profiles_dir(), session_id, profile)

        # For eval fixtures, job_url is fake (example-jobs.com).
        # Skip the job fetch entirely — build ParsedJob directly from job_description.
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz
        from models.schemas import ParsedJob as _ParsedJob  # type: ignore[import]
        from agents.gap_analyzer import analyze_gaps  # type: ignore[import]
        from agents.learning_path import build_learning_path  # type: ignore[import]
        from agents.orchestrator import compute_fit_score  # type: ignore[import]
        from models.schemas import AnalysisResult as _AR  # type: ignore[import]

        # Extract skills from job description using the LLM
        jd_agent = Agent(
            model=model,
            system_prompt="""Extract required skills from a job description.
Return ONLY a JSON object: {"required_skills": ["skill1", ...], "qualifications": ["q1", ...]}
No markdown, no explanation.""",
            callback_handler=None,
        )
        jd_response = jd_agent("Job Description:\n" + fixture["job_description"])
        jd_raw = str(jd_response)
        if jd_raw.strip().startswith("{") and '"content"' in jd_raw:
            try:
                _p = _json.loads(jd_raw)
                for _b in _p.get("content", []):
                    if isinstance(_b, dict) and "text" in _b:
                        jd_raw = _b["text"]
                        break
            except Exception:
                pass
        jd_raw = _re.sub(r"```(?:json)?\s*", "", jd_raw, flags=_re.IGNORECASE).strip().rstrip("`")
        try:
            jd_data = _json.loads(jd_raw)
        except Exception:
            m2 = _re.search(r"\{.*\}", jd_raw, _re.DOTALL)
            jd_data = _json.loads(m2.group()) if m2 else {"required_skills": [], "qualifications": []}

        parsed_job = _ParsedJob(
            job_id=str(_uuid.uuid4()),
            url=fixture["job_url"],
            title="Eval Fixture Job",
            employer="Eval Fixture Employer",
            required_skills=jd_data.get("required_skills", []),
            qualifications=jd_data.get("qualifications", []),
            raw_html=fixture["job_description"][:500],
            parsed_at=_dt.now(_tz.utc),
        )

        skill_gaps = analyze_gaps(parsed_job, profile)
        learning_path = build_learning_path(skill_gaps)
        fit_score = compute_fit_score(parsed_job, profile, skill_gaps, learning_path)

        result = _AR(
            result_id=parsed_job.job_id,
            job_id=parsed_job.job_id,
            session_id=session_id,
            fit_score=fit_score,
            skill_gaps=skill_gaps,
            learning_path=learning_path,
            analyzed_at=_dt.now(_tz.utc),
            rescored_at=None,
        ).model_dump()
        return result
    except ImportError:
        # Orchestrator not importable in eval context — return a structured error
        return {
            "fit_score": None,
            "skill_gaps": [],
            "learning_path": [],
            "error": (
                "CareerLens pipeline could not be imported. "
                "Ensure the backend server is configured and all dependencies are installed."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "fit_score": None,
            "skill_gaps": [],
            "learning_path": [],
            "error": f"CareerLens pipeline error: {type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Baseline runner
# ---------------------------------------------------------------------------

def run_baseline(fixture: dict, baseline_script: Path) -> dict:
    """
    Run the single-agent ``baseline.py`` script as a subprocess on a single fixture.

    Passes the job URL and resume text via CLI arguments and parses the JSON
    written to stdout.

    Args:
        fixture:         A fixture dict following the ``EvalFixture`` schema.
        baseline_script: Path to ``baseline.py``.

    Returns:
        A dict containing at minimum:
          - ``estimated_fit_score`` (int | None)
          - ``fit_assessment``      (str | None)
          - ``key_gaps``            (list[str])
          - ``error``               (str | None) — populated on failure
    """
    if not baseline_script.exists():
        return {
            "estimated_fit_score": None,
            "fit_assessment": None,
            "key_gaps": [],
            "error": f"baseline.py not found at {baseline_script}",
        }

    try:
        # For eval fixtures, pass job_description as --resume-text context
        # alongside the job_url so the baseline has the actual job content.
        # We embed the job description in the resume-text prompt since the
        # baseline cannot fetch fake URLs.
        combined_input = (
            f"JOB DESCRIPTION:\n{fixture['job_description']}\n\n"
            f"CANDIDATE RESUME:\n{fixture['resume_text']}"
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(baseline_script),
                "--job-url", fixture["job_url"],
                "--resume-text", combined_input,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_PROJECT_ROOT),
        )
        if proc.returncode != 0:
            return {
                "estimated_fit_score": None,
                "fit_assessment": None,
                "key_gaps": [],
                "error": f"baseline.py exited with code {proc.returncode}: {proc.stderr.strip()}",
            }

        output = proc.stdout.strip()
        result = json.loads(output)
        result.setdefault("estimated_fit_score", None)
        result.setdefault("fit_assessment", None)
        result.setdefault("key_gaps", [])
        result.pop("error", None)  # no error
        return result

    except subprocess.TimeoutExpired:
        return {
            "estimated_fit_score": None,
            "fit_assessment": None,
            "key_gaps": [],
            "error": "baseline.py timed out after 120 seconds",
        }
    except json.JSONDecodeError as exc:
        return {
            "estimated_fit_score": None,
            "fit_assessment": None,
            "key_gaps": [],
            "error": f"Could not parse baseline.py JSON output: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "estimated_fit_score": None,
            "fit_assessment": None,
            "key_gaps": [],
            "error": f"Baseline runner error: {type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Per-fixture metric computation
# ---------------------------------------------------------------------------

def compute_careerlens_metrics(cl_result: dict, fixture: dict) -> dict:
    """
    Compute all CareerLens metrics for a single fixture result.

    Args:
        cl_result: Dict returned by :func:`run_careerlens`.
        fixture:   The fixture dict (provides ground truth).

    Returns:
        Dict with keys: fit_score, mae, precision, recall, ndcg, relevance, error.
    """
    gt_fit = fixture["ground_truth_fit_score"]
    gt_skills = fixture["ground_truth_skills"]
    gt_gaps = fixture["ground_truth_gaps"]

    fit_score = cl_result.get("fit_score")
    skill_gaps: list[dict] = cl_result.get("skill_gaps") or []
    learning_path: list[dict] = cl_result.get("learning_path") or []
    error = cl_result.get("error")

    if fit_score is None or error:
        return {
            "fit_score": fit_score,
            "mae": None,
            "precision": None,
            "recall": None,
            "ndcg": None,
            "relevance": None,
            "error": error,
        }

    # Skill extraction: compare required_skills from the parsed job (if available)
    # against ground_truth_skills. Fall back to skills from skill_gaps as proxy.
    extracted_skills: list[str] = cl_result.get("extracted_skills") or [
        g.get("skill", "") for g in skill_gaps
    ]
    precision, recall = skill_extraction_pr(extracted_skills, gt_skills)

    # Gap ranking NDCG — ranked gap names from skill_gaps (ordered by rank)
    ranked_gaps = [g.get("skill", "") for g in sorted(skill_gaps, key=lambda x: x.get("rank", 99))]
    ndcg = ndcg_at_k(ranked_gaps, gt_gaps, k=5)

    # Resource relevance — average across all learning steps
    relevance_scores: list[float] = []
    for step in learning_path:
        skill_name: str = step.get("skill_gap", "")
        resources = (step.get("youtube_resources") or []) + (step.get("coursera_resources") or [])
        if resources and skill_name:
            relevance_scores.append(resource_relevance(resources, skill_name))
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else None

    return {
        "fit_score": fit_score,
        "mae": fit_score_mae(fit_score, gt_fit),
        "precision": precision,
        "recall": recall,
        "ndcg": ndcg,
        "relevance": avg_relevance,
        "error": None,
    }


def compute_baseline_metrics(bl_result: dict, fixture: dict) -> dict:
    """
    Compute baseline metrics for a single fixture result.

    Note: the baseline does not return structured skill or gap data, so only
    fit_score MAE, and key_gaps-derived precision/recall are computed.

    Args:
        bl_result: Dict returned by :func:`run_baseline`.
        fixture:   The fixture dict (provides ground truth).

    Returns:
        Dict with keys: fit_score, mae, precision, recall, ndcg, error.
    """
    gt_fit = fixture["ground_truth_fit_score"]
    gt_skills = fixture["ground_truth_skills"]
    gt_gaps = fixture["ground_truth_gaps"]

    fit_score = bl_result.get("estimated_fit_score")
    key_gaps: list[str] = bl_result.get("key_gaps") or []
    error = bl_result.get("error")

    if fit_score is None or error:
        return {
            "fit_score": fit_score,
            "mae": None,
            "precision": None,
            "recall": None,
            "ndcg": None,
            "error": error,
        }

    # Baseline key_gaps used as a proxy for both skill extraction and gap ranking
    precision, recall = skill_extraction_pr(key_gaps, gt_skills)
    ndcg = ndcg_at_k(key_gaps, gt_gaps, k=5)

    return {
        "fit_score": fit_score,
        "mae": fit_score_mae(fit_score, gt_fit),
        "precision": precision,
        "recall": recall,
        "ndcg": ndcg,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _safe_mean(values: list[Any]) -> float | None:
    """Return the mean of a list, ignoring None values. Returns None if all are None."""
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def aggregate_metrics(per_pair: list[dict]) -> dict:
    """
    Compute aggregate (mean) metrics across all fixtures for both pipelines.

    Args:
        per_pair: List of per-pair result dicts.

    Returns:
        Dict with ``careerlens`` and ``baseline`` sub-dicts of aggregate metrics.
    """
    cl_mae       = _safe_mean([p["careerlens"].get("mae")       for p in per_pair])
    cl_precision = _safe_mean([p["careerlens"].get("precision") for p in per_pair])
    cl_recall    = _safe_mean([p["careerlens"].get("recall")    for p in per_pair])
    cl_ndcg      = _safe_mean([p["careerlens"].get("ndcg")      for p in per_pair])
    cl_relevance = _safe_mean([p["careerlens"].get("relevance") for p in per_pair])

    bl_mae       = _safe_mean([p["baseline"].get("mae")       for p in per_pair])
    bl_precision = _safe_mean([p["baseline"].get("precision") for p in per_pair])
    bl_recall    = _safe_mean([p["baseline"].get("recall")    for p in per_pair])
    bl_ndcg      = _safe_mean([p["baseline"].get("ndcg")      for p in per_pair])

    return {
        "careerlens": {
            "mae":       cl_mae,
            "precision": cl_precision,
            "recall":    cl_recall,
            "ndcg":      cl_ndcg,
            "relevance": cl_relevance,
        },
        "baseline": {
            "mae":       bl_mae,
            "precision": bl_precision,
            "recall":    bl_recall,
            "ndcg":      bl_ndcg,
        },
    }


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_evaluation(fixtures_dir: Path, output_path: Path, baseline_script: Path) -> None:
    """
    Run the full evaluation loop over all fixtures and write the JSON report.

    Args:
        fixtures_dir:    Path to directory containing fixture JSON files.
        output_path:     Destination path for the JSON report.
        baseline_script: Path to ``baseline.py``.
    """
    print(f"Loading fixtures from: {fixtures_dir}")
    fixtures = load_fixtures(fixtures_dir)
    print(f"Loaded {len(fixtures)} fixtures.")

    per_pair: list[dict] = []

    for i, fixture in enumerate(fixtures, start=1):
        pair_id: str = fixture.get("pair_id", f"pair_{i:02d}")
        print(f"[{i:02d}/{len(fixtures)}] Running {pair_id} ...", end=" ", flush=True)

        # --- CareerLens pipeline ---
        cl_raw = run_careerlens(fixture)
        cl_metrics = compute_careerlens_metrics(cl_raw, fixture)

        # --- Baseline pipeline ---
        bl_raw = run_baseline(fixture, baseline_script)
        bl_metrics = compute_baseline_metrics(bl_raw, fixture)

        cl_status = "OK" if cl_metrics.get("error") is None else f"ERROR: {cl_metrics['error'][:60]}"
        bl_status = "OK" if bl_metrics.get("error") is None else f"ERROR: {bl_metrics['error'][:60]}"
        print(f"CareerLens={cl_status} | Baseline={bl_status}")

        per_pair.append({
            "pair_id": pair_id,
            "ground_truth_fit_score": fixture["ground_truth_fit_score"],
            "careerlens": cl_metrics,
            "baseline": bl_metrics,
        })

    print("\nAggregating metrics ...")
    aggregate = aggregate_metrics(per_pair)

    report = {
        "aggregate": aggregate,
        "per_pair": per_pair,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"\nReport written to: {output_path}")

    # Print a brief summary table
    print("\n--- Aggregate Results ---")
    for system in ("careerlens", "baseline"):
        agg = aggregate[system]
        mae_str       = f"{agg['mae']:.2f}"       if agg["mae"]       is not None else "N/A"
        precision_str = f"{agg['precision']:.3f}" if agg["precision"] is not None else "N/A"
        recall_str    = f"{agg['recall']:.3f}"    if agg["recall"]    is not None else "N/A"
        ndcg_str      = f"{agg['ndcg']:.3f}"      if agg["ndcg"]      is not None else "N/A"
        relevance_str = f"{agg.get('relevance', None):.3f}" if agg.get("relevance") is not None else "N/A"
        print(
            f"  {system:<12} | MAE={mae_str:>6} | P={precision_str} | "
            f"R={recall_str} | NDCG={ndcg_str} | Relevance={relevance_str}"
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="CareerLens evaluation runner — compares multi-agent pipeline vs baseline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("eval/fixtures"),
        help="Directory containing fixture JSON files (default: eval/fixtures).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/report.json"),
        help="Output path for the JSON report (default: eval/report.json).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_PROJECT_ROOT / "baseline.py",
        help="Path to baseline.py (default: <project_root>/baseline.py).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    run_evaluation(
        fixtures_dir=args.fixtures,
        output_path=args.output,
        baseline_script=args.baseline,
    )


if __name__ == "__main__":
    main()
