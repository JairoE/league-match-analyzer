"""Pure retrieval metrics — no dependencies beyond the standard library."""

from __future__ import annotations

from collections.abc import Sequence


def precision_at_k(relevance: Sequence[bool], k: int) -> float:
    """Fraction of the top-k retrieved items that are relevant.

    Uses the standard fixed-k denominator: retrieving fewer than k items
    is penalized.

    Args:
        relevance: Relevance flags in retrieval order.
        k: Cutoff.

    Returns:
        Precision in [0, 1].
    """
    if k <= 0:
        return 0.0
    return sum(bool(flag) for flag in relevance[:k]) / k


def recall_at_k(
    relevance: Sequence[bool],
    total_relevant: int,
    k: int,
) -> float | None:
    """Fraction of all relevant items found in the top k.

    Args:
        relevance: Relevance flags in retrieval order.
        total_relevant: Number of relevant items in the whole corpus.
        k: Cutoff.

    Returns:
        Recall in [0, 1], or None when the query has no relevant items
        (such cases should be excluded from the aggregate).
    """
    if total_relevant <= 0:
        return None
    return sum(bool(flag) for flag in relevance[:k]) / total_relevant


def reciprocal_rank(relevance: Sequence[bool]) -> float:
    """1 / rank of the first relevant item, or 0.0 when none is retrieved."""
    for index, flag in enumerate(relevance):
        if flag:
            return 1.0 / (index + 1)
    return 0.0


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (p in [0, 100]) of a value list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean, 0.0 for an empty list."""
    return sum(values) / len(values) if values else 0.0
