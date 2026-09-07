#!/usr/bin/env python3
"""
baseline.py — Single-agent baseline for CareerLens evaluation.

This script evaluates a candidate's resume against a job posting using a single
Strands Agent (no multi-agent pipeline). It is used as a comparison baseline
for the CareerLens evaluation suite.

Usage:
  python baseline.py --job-url https://example.com/jobs/123 --resume-file path/to/resume.txt
  python baseline.py --job-url https://example.com/jobs/123 --resume-text "5 years Python experience..."

Output (stdout):
  {
    "fit_assessment": "The candidate is a strong match for this role...",
    "estimated_fit_score": 72,
    "key_gaps": ["Kubernetes", "Terraform"]
  }
"""

import argparse
import json
import os
import sys

# Load .env from the directory containing this script before any AWS calls
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_PATH = _SCRIPT_DIR / ".env"

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=_ENV_PATH)
except ImportError:
    pass  # python-dotenv not installed; rely on environment variables being set externally

BASELINE_SYSTEM_PROMPT = """You are a career advisor AI. Given a job posting URL and a candidate's resume text,
you will evaluate how well the candidate fits the job.

You MUST respond with a JSON object (and nothing else) in exactly this format:
{
  "fit_assessment": "<2-3 sentence narrative assessment of the candidate's fit>",
  "estimated_fit_score": <integer 0-100>,
  "key_gaps": ["<skill or qualification gap 1>", "<skill or qualification gap 2>", ...]
}

Rules:
- estimated_fit_score must be an integer between 0 and 100 inclusive.
- key_gaps is a list of strings; use an empty list [] if there are no significant gaps.
- fit_assessment must be a plain string (no nested JSON).
- Do not include any text outside the JSON object.
"""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="CareerLens single-agent baseline — evaluates resume vs job posting.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--job-url",
        required=True,
        help="URL of the job posting to evaluate against.",
    )

    resume_group = parser.add_mutually_exclusive_group(required=True)
    resume_group.add_argument(
        "--resume-text",
        default=None,
        help="Resume text passed directly as a command-line argument.",
    )
    resume_group.add_argument(
        "--resume-file",
        default=None,
        help="Path to a plain-text file containing the resume.",
    )
    return parser.parse_args()


def load_resume(args: argparse.Namespace) -> str:
    """Return the resume text from either --resume-text or --resume-file."""
    if args.resume_text:
        return args.resume_text.strip()

    resume_path = Path(args.resume_file)
    if not resume_path.exists():
        print(f"Error: resume file not found: {resume_path}", file=sys.stderr)
        sys.exit(1)

    try:
        return resume_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"Error reading resume file: {exc}", file=sys.stderr)
        sys.exit(1)


def run_baseline(job_url: str, resume_text: str) -> dict:
    """
    Invoke a single Strands Agent to assess fit between the resume and job posting.

    Returns a dict with keys: fit_assessment, estimated_fit_score, key_gaps.
    """
    try:
        from strands import Agent
    except ImportError as exc:
        print(
            f"Error: strands-agents not installed. Run: pip install strands-agents\n{exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Add project backend to path so model_factory is importable
    import sys as _sys
    _sys.path.insert(0, str(_SCRIPT_DIR / "backend"))

    try:
        from agents.model_factory import get_model
        model = get_model()
    except Exception as exc:
        print(
            f"Error initialising LLM model. "
            f"Check your LLM_PROVIDER and corresponding API key in .env.\n{exc}",
            file=sys.stderr,
        )
        _sys.exit(1)

    agent = Agent(model=model, system_prompt=BASELINE_SYSTEM_PROMPT, callback_handler=None)

    prompt = (
        f"Job Posting URL: {job_url}\n\n"
        f"Candidate Resume:\n{resume_text}"
    )

    try:
        response = agent(prompt)
        raw_text: str = str(response)
    except Exception as exc:
        print(f"Error calling Strands Agent: {exc}", file=sys.stderr)
        sys.exit(1)

    # The model is instructed to return pure JSON; parse it directly.
    # Fall back gracefully if the model adds surrounding text.
    try:
        # Try to find a JSON object in the response
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON object found in model response.")
        result = json.loads(raw_text[start:end])
    except (json.JSONDecodeError, ValueError) as exc:
        # If parsing fails, wrap the raw text in the expected structure
        result = {
            "fit_assessment": raw_text.strip(),
            "estimated_fit_score": -1,
            "key_gaps": [],
        }

    # Ensure expected keys are present
    result.setdefault("fit_assessment", "")
    result.setdefault("estimated_fit_score", -1)
    result.setdefault("key_gaps", [])

    # Clamp fit score to valid range
    score = result.get("estimated_fit_score")
    if isinstance(score, (int, float)):
        result["estimated_fit_score"] = max(0, min(100, int(score)))

    return result


def main() -> None:
    """Entry point."""
    args = parse_args()
    resume_text = load_resume(args)
    result = run_baseline(job_url=args.job_url, resume_text=resume_text)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
