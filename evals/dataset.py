"""Leave-one-out eval dataset built from real LLMAnalysis rows.

Ground truth is programmatic (per docs/LLM_PIPELINE_STATUS.md): a retrieved
example is *relevant* to a query when it shares champion, rank tier, and
dominant improvement-gap category.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EvalCase:
    """One held-out analysis acting as a retrieval query."""

    analysis_id: str
    champion_name: str
    rank_tier: str | None
    dominant_category: str | None
    embedding: list[float]
    input_payload: dict[str, Any]


def dominant_gap_category(input_payload: dict[str, Any]) -> str | None:
    """Classify the top improvement gap of an analysis.

    Item action keys are numeric Data Dragon item ids; objective keys are
    monster-type strings (e.g. "DRAGON"). Returns None when the analysis
    has no improvement gaps.
    """
    opportunities = input_payload.get("top_improvement_opportunities") or []
    if not opportunities:
        return None
    better = opportunities[0].get("better_alternative") or {}
    key = str(better.get("action_key") or "")
    if not key:
        return None
    return "item_purchase" if key.isdigit() else "objective_kill"


def is_relevant(query: EvalCase, candidate: EvalCase) -> bool:
    """Programmatic relevance: same champion + rank tier + gap category."""
    return (
        candidate.analysis_id != query.analysis_id
        and candidate.champion_name == query.champion_name
        and candidate.rank_tier == query.rank_tier
        and candidate.dominant_category == query.dominant_category
    )


async def load_eval_cases(session: Any) -> list[EvalCase]:
    """Load every embedded LLMAnalysis row as an eval case.

    Args:
        session: Async database session.

    Returns:
        EvalCase list ordered by creation time.
    """
    from sqlmodel import select

    from app.models.llm_analysis import LLMAnalysis

    result = await session.execute(
        select(LLMAnalysis)
        .where(LLMAnalysis.embedding.is_not(None))
        .order_by(LLMAnalysis.created_at)  # type: ignore[attr-defined]
    )
    cases: list[EvalCase] = []
    for row in result.scalars().all():
        cases.append(
            EvalCase(
                analysis_id=str(row.id),
                champion_name=row.champion_name,
                rank_tier=row.rank_tier,
                dominant_category=dominant_gap_category(row.input_payload or {}),
                embedding=list(row.embedding),
                input_payload=row.input_payload or {},
            )
        )
    return cases
