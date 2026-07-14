"""Ungated unit tests for the pure metric functions (no DB needed)."""

from __future__ import annotations

from evals.metrics import mean, percentile, precision_at_k, reciprocal_rank, recall_at_k


def test_precision_at_k() -> None:
    assert precision_at_k([True, False, True], 3) == 2 / 3
    assert precision_at_k([True], 3) == 1 / 3  # fixed-k denominator
    assert precision_at_k([], 3) == 0.0
    assert precision_at_k([True, True], 0) == 0.0


def test_recall_at_k() -> None:
    assert recall_at_k([True, False, True], total_relevant=4, k=3) == 0.5
    assert recall_at_k([False, False], total_relevant=2, k=2) == 0.0
    assert recall_at_k([True], total_relevant=0, k=3) is None


def test_reciprocal_rank() -> None:
    assert reciprocal_rank([False, True, False]) == 0.5
    assert reciprocal_rank([True]) == 1.0
    assert reciprocal_rank([False, False]) == 0.0
    assert reciprocal_rank([]) == 0.0


def test_percentile() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([7.0], 95) == 7.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert percentile([1.0, 2.0, 3.0, 4.0], 100) == 4.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0) == 1.0


def test_mean() -> None:
    assert mean([]) == 0.0
    assert mean([1.0, 2.0, 3.0]) == 2.0
