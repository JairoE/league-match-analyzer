"""Shared lookup and scheduling rules for persisted AI Coach analyses.

Used by the analysis router and the one-command account pipeline so both
apply the same 24h cache window and the same deterministic ARQ job id.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.llm_analysis import LLMAnalysis

ANALYSIS_CACHE_HOURS = 24


def analysis_job_id(riot_account_id: Any, champion_id: int | str, day: date) -> str:
    """Build the deterministic ARQ job id for an analysis request.

    The day bucket lets a failed run be retried the next day even if the
    id were somehow still reserved; the worker's short keep_result frees it
    within seconds in practice.

    Args:
        riot_account_id: Riot account UUID.
        champion_id: Riot numeric champion id.
        day: Calendar day the request is made.

    Returns:
        Job id shared by UI clicks and the account pipeline.
    """
    return f"llm-{riot_account_id}-{champion_id}-{day.isoformat()}"


async def latest_analysis(
    session: AsyncSession,
    riot_account_id: Any,
    champion_name: str,
    since: datetime | None = None,
) -> LLMAnalysis | None:
    """Return the newest analysis row for an account + champion.

    Args:
        session: Async database session.
        riot_account_id: Riot account UUID.
        champion_name: Champion display name stored on the row.
        since: Optional lower bound on ``created_at``.

    Returns:
        Newest matching row, or None.
    """
    statement = (
        select(LLMAnalysis)
        .where(
            LLMAnalysis.riot_account_id == riot_account_id,
            LLMAnalysis.champion_name == champion_name,
        )
        .order_by(LLMAnalysis.created_at.desc())  # type: ignore[attr-defined]
        .limit(1)
    )
    if since is not None:
        statement = statement.where(LLMAnalysis.created_at >= since)
    result = await session.execute(statement)
    return result.scalars().first()
