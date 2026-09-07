"""
eval/metrics.py — Evaluation metrics for the CareerLens multi-agent pipeline.

Provides four metric functions used by eval_runner.py to compare the CareerLens
pipeline output against human-annotated ground truth:

  - fit_score_mae          : Mean Absolute Error for fit scores
  - skill_extraction_pr    : Precision/recall for skill extraction
  - ndcg_at_k              : Normalised Discounted Cumulative Gain for gap ranking
  - resource_relevance     : Word-overlap cosine similarity of resource titles vs skill gap
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Fit score accuracy — Mean Absolute Error
# ---------------------------------------------------------------------------


def fit_score_mae(predicted: int, ground_truth: int) -> float:
    """
    Compute the Mean Absolute Error between a predicted fit score and the ground truth.

    Args:
        predicted:     Integer fit score in [0, 100] produced by the pipeline.
        ground_truth:  Human-labelled integer fit score in [0, 100].

    Returns:
        Non-negative float representing |predicted - ground_truth|.

    Example:
        >>> fit_score_mae(72, 65)
        7.0
    """
    return float(abs(predicted - ground_truth))


# ---------------------------------------------------------------------------
# 2. Skill extraction — Precision and Recall
# ---------------------------------------------------------------------------


def skill_extraction_pr(
    extracted: list[str], ground_truth: list[str]
) -> tuple[float, float]:
    """
    Compute precision and recall for a skill extraction result.

    Comparison is case-insensitive. Duplicate entries in either list are
    collapsed to a set before comparison.

    Args:
        extracted:     Skills extracted by the pipeline (may be empty).
        ground_truth:  Human-annotated required skills (may be empty).

    Returns:
        A ``(precision, recall)`` tuple where both values are floats in [0.0, 1.0].
        - precision = |extracted ∩ ground_truth| / |extracted|  (0.0 if extracted is empty)
        - recall    = |extracted ∩ ground_truth| / |ground_truth| (0.0 if ground_truth is empty)

    Example:
        >>> skill_extraction_pr(["Python", "SQL", "React"], ["Python", "SQL", "Docker"])
        (0.6666666666666666, 0.6666666666666666)
    """
    extracted_set: set[str] = {s.lower().strip() for s in extracted if s.strip()}
    gt_set: set[str] = {s.lower().strip() for s in ground_truth if s.strip()}

    intersection = extracted_set & gt_set

    precision = len(intersection) / len(extracted_set) if extracted_set else 0.0
    recall = len(intersection) / len(gt_set) if gt_set else 0.0

    # Clamp to [0.0, 1.0] as a safety measure
    precision = max(0.0, min(1.0, precision))
    recall = max(0.0, min(1.0, recall))

    return precision, recall


# ---------------------------------------------------------------------------
# 3. Gap ranking quality — NDCG@k
# ---------------------------------------------------------------------------


def ndcg_at_k(
    ranked: list[str], ground_truth: list[str], k: int = 5
) -> float:
    """
    Compute Normalised Discounted Cumulative Gain at rank k (NDCG@k) for gap ranking.

    Items in ``ground_truth`` are treated as binary-relevant (relevance = 1);
    items not in ``ground_truth`` have relevance = 0.  Position in ``ranked``
    determines the discount.  The ideal ranking places all relevant items first.

    Comparison is case-insensitive.

    Args:
        ranked:        Gaps returned by the pipeline, ordered by priority (index 0 = rank 1).
        ground_truth:  Human-annotated gaps ordered by relevance (most relevant first).
                       Used as the relevant-item set; positional order is NOT used in
                       relevance labelling — all items in ground_truth are equally relevant.
        k:             Cutoff depth. Default is 5.

    Returns:
        Float in [0.0, 1.0]. Returns 0.0 if either list is empty or k == 0.

    Example:
        >>> ndcg_at_k(["Kubernetes", "Terraform", "Ansible"], ["Kubernetes", "Terraform"], k=3)
        1.0
    """
    if not ranked or not ground_truth or k == 0:
        return 0.0

    gt_set: set[str] = {g.lower().strip() for g in ground_truth if g.strip()}

    def _dcg(items: list[str], relevant: set[str], cutoff: int) -> float:
        """Compute DCG for a ranked list with binary relevance."""
        score = 0.0
        for i, item in enumerate(items[:cutoff]):
            rel = 1.0 if item.lower().strip() in relevant else 0.0
            # Standard NDCG formula: rel / log2(rank + 1), rank is 1-indexed
            score += rel / math.log2(i + 2)
        return score

    dcg = _dcg(ranked, gt_set, k)

    # Ideal DCG: place all relevant items first
    n_relevant_in_k = min(len(gt_set), k)
    ideal_items = list(gt_set)[:n_relevant_in_k]
    idcg = _dcg(ideal_items, gt_set, k)

    if idcg == 0.0:
        return 0.0

    ndcg = dcg / idcg
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, ndcg))


# ---------------------------------------------------------------------------
# 4. Resource relevance — word-overlap cosine similarity
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """
    Lowercase and tokenize a string into alphanumeric word tokens.

    Removes punctuation, splits on whitespace, and filters empty tokens.
    """
    return [tok for tok in re.sub(r"[^a-z0-9\s]", " ", text.lower()).split() if tok]


def _tf_vector(tokens: list[str]) -> dict[str, float]:
    """
    Compute a simple term-frequency vector from a token list.

    Returns a dict mapping token → (count / total_tokens).
    """
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """
    Compute cosine similarity between two TF vectors.

    Returns a float in [0.0, 1.0].  Returns 0.0 if either vector is empty.
    """
    if not vec_a or not vec_b:
        return 0.0

    common_terms = set(vec_a) & set(vec_b)
    dot_product = sum(vec_a[t] * vec_b[t] for t in common_terms)

    magnitude_a = math.sqrt(sum(v * v for v in vec_a.values()))
    magnitude_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def resource_relevance(resources: list[dict], skill_gap: str) -> float:
    """
    Compute the average word-overlap cosine similarity between resource titles
    and a given skill gap name.

    Each resource dict is expected to have a ``"title"`` key.  Resources without
    a ``"title"`` key (or with empty titles) are skipped.  Similarity is computed
    using simple TF vectors over word tokens — no external ML library required.

    Args:
        resources:  List of resource dicts (``VideoResource`` or ``CourseResource``
                    serialised as dicts).  Each should contain at least a ``"title"`` key.
        skill_gap:  The skill gap name to compare against (e.g. ``"Kubernetes"``).

    Returns:
        Float in [0.0, 1.0].  Returns 0.0 if ``resources`` is empty or ``skill_gap``
        is blank, or if no resource has a non-empty title.

    Example:
        >>> resources = [{"title": "Introduction to Kubernetes for beginners"}]
        >>> resource_relevance(resources, "Kubernetes")
        0.5...
    """
    if not resources or not skill_gap.strip():
        return 0.0

    gap_tokens = _tokenize(skill_gap)
    gap_vec = _tf_vector(gap_tokens)

    if not gap_vec:
        return 0.0

    scores: list[float] = []
    for resource in resources:
        title: Optional[str] = resource.get("title", "")
        if not title or not title.strip():
            continue
        title_tokens = _tokenize(title)
        title_vec = _tf_vector(title_tokens)
        sim = _cosine_similarity(gap_vec, title_vec)
        scores.append(sim)

    if not scores:
        return 0.0

    return sum(scores) / len(scores)
