"""RAG retrieval service for few-shot example injection (pipeline step 6.5).

Handles embedding text construction and similarity-based retrieval of past
LLMAnalysis records to use as few-shot examples in the LLM prompt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlmodel import select

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.llm_analysis import LLMAnalysis

logger = get_logger("league_api.services.rag_retrieval")


def build_embedding_text(
    champion_name: str,
    rank_tier: str | None,
    comparison_dict: dict[str, Any],
) -> str:
    """Build a compact text representation of an analysis context for embedding.

    Captures champion, rank, top improvement gaps, and selection bias signals —
    the dimensions most relevant for finding similar prior analyses.

    Args:
        champion_name: Human-readable champion name (e.g. "Yasuo").
        rank_tier: Rank tier string (e.g. "GOLD") or None.
        comparison_dict: Output of ComparisonResult.to_dict().

    Returns:
        Single-line text suitable for embedding generation.
    """
    rank = rank_tier or "UNKNOWN"
    parts: list[str] = [f"{champion_name} {rank}"]

    opportunities = comparison_dict.get("top_improvement_opportunities", [])
    if opportunities:
        gap_parts: list[str] = []
        for opp in opportunities[:3]:
            better = opp.get("better_alternative", {})
            action_name = better.get("action_name") or better.get("action_key", "?")
            gap = opp.get("delta_w_gap")
            if gap is not None:
                gap_parts.append(f"{action_name} gap={gap:+.4f}")
            else:
                gap_parts.append(action_name)
        parts.append("gaps: " + ", ".join(gap_parts))

    bias_flags = comparison_dict.get("top_selection_bias_flags", [])
    if bias_flags:
        bias_names = [
            (f.get("action_name") or f.get("action_key", "?")) for f in bias_flags[:3]
        ]
        parts.append("bias: " + ", ".join(bias_names))

    return " | ".join(parts)


async def retrieve_few_shot_examples(
    session: AsyncSession,
    champion_name: str,
    query_embedding: list[float],
    limit: int = 3,
) -> list[LLMAnalysis]:
    """Retrieve the most similar past LLMAnalysis records for a given champion.

    Performs cosine-distance nearest-neighbor search on the embedding column,
    filtered to the same champion. Only rows with non-null embeddings are
    considered. Returns an empty list if no records exist yet (cold start).

    Args:
        session: Async database session.
        champion_name: Champion to filter by (exact match).
        query_embedding: Dense vector for the current analysis context.
        limit: Maximum number of examples to return.

    Returns:
        List of LLMAnalysis records ordered by cosine similarity (most similar first).
    """
    from app.models.llm_analysis import LLMAnalysis

    try:
        result = await session.execute(
            select(LLMAnalysis)
            .where(LLMAnalysis.champion_name == champion_name)
            .where(LLMAnalysis.embedding.is_not(None))
            .order_by(LLMAnalysis.embedding.cosine_distance(query_embedding))
            .limit(limit)
        )
        examples = list(result.scalars().all())
        logger.info(
            "rag_retrieval_done",
            extra={"champion": champion_name, "found": len(examples)},
        )
        return examples
    except Exception:
        logger.warning(
            "rag_retrieval_failed",
            extra={"champion": champion_name},
            exc_info=True,
        )
        return []


def format_few_shot_examples(examples: list[LLMAnalysis]) -> list[dict[str, Any]]:
    """Serialize LLMAnalysis records into prompt-friendly dicts.

    Args:
        examples: Retrieved LLMAnalysis records.

    Returns:
        List of dicts with champion_name, rank_tier, and recommendations summary.
    """
    result: list[dict[str, Any]] = []
    for ex in examples:
        result.append(
            {
                "champion_name": ex.champion_name,
                "rank_tier": ex.rank_tier or "UNKNOWN",
                "recommendations": ex.recommendations,
                "overall_assessment": (
                    ex.output_payload.get("overall_assessment") if ex.output_payload else None
                ),
            }
        )
    return result
