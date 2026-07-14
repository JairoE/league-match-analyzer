"""Retrieval eval: leave-one-out precision@k / recall@k / MRR over the corpus.

Gated behind RUN_EVALS=1 so plain pytest runs stay hermetic. Requires the
database to be up and the corpus seeded (make seed-rag-corpus); skips
gracefully otherwise. Results land in evals/results/ as timestamped JSON
keyed by a hash of the eval config.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from evals.dataset import EvalCase, is_relevant, load_eval_cases
from evals.metrics import mean, percentile, precision_at_k, reciprocal_rank, recall_at_k

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_EVALS") != "1",
    reason="Set RUN_EVALS=1 to run the eval harness (needs DB + seeded corpus)",
)

MIN_CORPUS_ROWS = 10
RESULTS_DIR = Path(__file__).parent / "results"
# text-embedding-3-small pricing (USD per 1M tokens) for cost-per-query estimates
EMBEDDING_PRICE_PER_MTOK = 0.02
CHARS_PER_TOKEN_ESTIMATE = 4


def _config() -> dict[str, Any]:
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "eval": "retrieval_loo_v1",
        "k": settings.rag_few_shot_limit,
        "embedding_model": settings.rag_embedding_model,
        "min_corpus_rows": MIN_CORPUS_ROWS,
        "relevance": "champion + rank_tier + dominant_gap_category",
    }


def write_results(config: dict[str, Any], payload: dict[str, Any]) -> Path:
    """Write a timestamped results JSON keyed by the config hash."""
    RESULTS_DIR.mkdir(exist_ok=True)
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()[:8]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{timestamp}_{config_hash}.json"
    path.write_text(json.dumps({"config": config, **payload}, indent=2))
    return path


async def _evaluate() -> tuple[dict[str, Any], dict[str, Any]]:
    from app.db.session import async_session_factory
    from app.services.rag_retrieval import build_embedding_text, retrieve_few_shot_examples

    config = _config()
    k = config["k"]

    async with async_session_factory() as session:
        cases = await load_eval_cases(session)
        if len(cases) < MIN_CORPUS_ROWS:
            pytest.skip(
                f"Corpus too small for a meaningful eval: {len(cases)} rows "
                f"(< {MIN_CORPUS_ROWS}). Seed with: make seed-rag-corpus"
            )

        by_id: dict[str, EvalCase] = {case.analysis_id: case for case in cases}
        precisions: list[float] = []
        recalls: list[float] = []
        rr_values: list[float] = []
        latencies_ms: list[float] = []
        text_chars: list[int] = []

        for query in cases:
            start = time.perf_counter()
            # Fetch k+1 — the query row matches itself at distance 0.
            retrieved = await retrieve_few_shot_examples(
                session,
                query.champion_name,
                query.embedding,
                limit=k + 1,
            )
            latencies_ms.append((time.perf_counter() - start) * 1000)

            hits = [r for r in retrieved if str(r.id) != query.analysis_id][:k]
            relevance = [
                candidate is not None and is_relevant(query, candidate)
                for candidate in (by_id.get(str(hit.id)) for hit in hits)
            ]
            total_relevant = sum(is_relevant(query, c) for c in cases)

            precisions.append(precision_at_k(relevance, k))
            recall = recall_at_k(relevance, total_relevant, k)
            if recall is not None:
                recalls.append(recall)
            rr_values.append(reciprocal_rank(relevance))
            text_chars.append(
                len(
                    build_embedding_text(
                        query.champion_name, query.rank_tier, query.input_payload
                    )
                )
            )

    mean_tokens = mean([chars / CHARS_PER_TOKEN_ESTIMATE for chars in text_chars])
    metrics = {
        "cases": len(cases),
        "cases_with_relevant": len(recalls),
        f"precision_at_{k}": round(mean(precisions), 4),
        f"recall_at_{k}": round(mean(recalls), 4) if recalls else None,
        "mrr": round(mean(rr_values), 4),
        "latency_ms_p50": round(percentile(latencies_ms, 50), 2),
        "latency_ms_p95": round(percentile(latencies_ms, 95), 2),
        "est_embedding_tokens_per_query": round(mean_tokens, 1),
        "est_cost_usd_per_query": round(
            mean_tokens / 1_000_000 * EMBEDDING_PRICE_PER_MTOK, 10
        ),
    }
    return config, metrics


def test_retrieval_eval_produces_results() -> None:
    try:
        config, metrics = asyncio.run(_evaluate())
    except Exception as exc:
        # Environmental failure (DB down, bad credentials), not an eval failure.
        # pytest.skip() inside _evaluate is a BaseException and passes through.
        pytest.skip(f"Database unavailable for eval: {type(exc).__name__}: {exc}")

    path = write_results(config, {"metrics": metrics})
    print(f"\nretrieval eval → {path}\n{json.dumps(metrics, indent=2)}")

    k = config["k"]
    assert 0.0 <= metrics[f"precision_at_{k}"] <= 1.0
    assert 0.0 <= metrics["mrr"] <= 1.0
    if metrics[f"recall_at_{k}"] is not None:
        assert 0.0 <= metrics[f"recall_at_{k}"] <= 1.0
    assert path.exists()
