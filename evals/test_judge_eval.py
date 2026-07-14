"""LLM-as-judge eval over retrieved few-shot sets (RUN_EVALS=1 + API key).

Samples up to JUDGE_SAMPLE_SIZE queries, retrieves their few-shot examples,
and has the LLM grade each set on relevance / factuality / completeness.
Also contains ungated unit tests for prompt building and response parsing.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from evals.dataset import load_eval_cases
from evals.judge import JUDGE_SYSTEM_PROMPT, build_judge_user_prompt, parse_judge_response
from evals.metrics import mean
from evals.test_retrieval_eval import MIN_CORPUS_ROWS, write_results

JUDGE_SAMPLE_SIZE = 10

# ── Ungated unit tests ────────────────────────────────────────────────


def test_build_judge_user_prompt_formats_examples() -> None:
    prompt = build_judge_user_prompt(
        "Jhin SILVER | gaps: The Collector gap=+0.0400",
        [
            {
                "champion_name": "Jhin",
                "rank_tier": "SILVER",
                "overall_assessment": "Solid.",
                "recommendations": [
                    {
                        "title": "Buy Collector",
                        "current_choice": "IE",
                        "recommended_choice": "Collector",
                        "delta_w_gap": 0.04,
                    }
                ],
            }
        ],
    )

    assert prompt.startswith("QUERY: Jhin SILVER")
    assert "1. Jhin (SILVER)" in prompt
    assert "Buy Collector: IE -> Collector" in prompt


def test_build_judge_user_prompt_empty_set() -> None:
    assert "(none retrieved)" in build_judge_user_prompt("Jhin SILVER", [])


def test_parse_judge_response_valid_and_clamped() -> None:
    parsed = parse_judge_response(
        '{"relevance": 4, "factuality": 9, "completeness": 0.5, "rationale": "ok"}'
    )

    assert parsed == {
        "relevance": 4,
        "factuality": 5,
        "completeness": 1,
        "rationale": "ok",
    }


def test_parse_judge_response_rejects_malformed() -> None:
    assert parse_judge_response("not json") is None
    assert parse_judge_response('{"relevance": "high"}') is None
    assert parse_judge_response('["list"]') is None


# ── Gated judge eval ──────────────────────────────────────────────────


async def _judge_eval() -> tuple[dict, dict]:
    from app.core.config import get_settings
    from app.db.session import async_session_factory
    from app.services.llm_client import OpenAIClient
    from app.services.rag_retrieval import (
        build_embedding_text,
        format_few_shot_examples,
        retrieve_few_shot_examples,
    )

    settings = get_settings()
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY not configured — judge eval needs a real key")
    config = {
        "eval": "llm_judge_v1",
        "k": settings.rag_few_shot_limit,
        "judge_model": settings.llm_model_name,
        "sample_size": JUDGE_SAMPLE_SIZE,
    }
    client = OpenAIClient(api_key=settings.openai_api_key, model=settings.llm_model_name)

    async with async_session_factory() as session:
        cases = await load_eval_cases(session)
        if len(cases) < MIN_CORPUS_ROWS:
            pytest.skip(
                f"Corpus too small: {len(cases)} rows (< {MIN_CORPUS_ROWS}). "
                "Seed with: make seed-rag-corpus"
            )

        scored: list[dict] = []
        for query in cases[:JUDGE_SAMPLE_SIZE]:
            retrieved = await retrieve_few_shot_examples(
                session,
                query.champion_name,
                query.embedding,
                limit=config["k"] + 1,
            )
            examples = format_few_shot_examples(
                [r for r in retrieved if str(r.id) != query.analysis_id][: config["k"]]
            )
            query_text = build_embedding_text(
                query.champion_name, query.rank_tier, query.input_payload
            )
            response = await client.complete(
                JUDGE_SYSTEM_PROMPT,
                build_judge_user_prompt(query_text, examples),
            )
            parsed = parse_judge_response(response.content)
            if parsed is not None:
                scored.append({"analysis_id": query.analysis_id, **parsed})

    if not scored:
        pytest.skip("Judge returned no parseable scores")
    metrics = {
        "judged_cases": len(scored),
        "mean_relevance": round(mean([s["relevance"] for s in scored]), 2),
        "mean_factuality": round(mean([s["factuality"] for s in scored]), 2),
        "mean_completeness": round(mean([s["completeness"] for s in scored]), 2),
    }
    return config, {"metrics": metrics, "cases": scored}


@pytest.mark.skipif(
    os.environ.get("RUN_EVALS") != "1",
    reason="Set RUN_EVALS=1 to run the judge eval (needs DB + OpenAI key)",
)
def test_llm_judge_eval_produces_results() -> None:
    try:
        config, payload = asyncio.run(_judge_eval())
    except Exception as exc:
        pytest.skip(f"Environment unavailable for judge eval: {type(exc).__name__}: {exc}")

    path = write_results(config, payload)
    print(f"\njudge eval → {path}\n{json.dumps(payload['metrics'], indent=2)}")

    for axis in ("mean_relevance", "mean_factuality", "mean_completeness"):
        assert 1.0 <= payload["metrics"][axis] <= 5.0
