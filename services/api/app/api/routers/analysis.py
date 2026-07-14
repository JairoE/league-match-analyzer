"""AI Coach analysis endpoints — enqueue the LLM analysis job and poll results."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.db.session import get_session
from app.models.llm_analysis import LLMAnalysis
from app.schemas.analysis import (
    AnalysisEnqueueRequest,
    AnalysisEnqueueResponse,
    AnalysisResponse,
    RecommendationResponse,
)
from app.services.arq_pool import get_arq_pool
from app.services.champions import get_champion_by_id
from app.services.riot_accounts import resolve_riot_account_identifier

router = APIRouter(tags=["analysis"])
logger = get_logger("league_api.analysis")

ANALYSIS_CACHE_HOURS = 24


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    """Extract a string field from output_payload, tolerating parse_error rows."""
    value = payload.get(key)
    return value if isinstance(value, str) else None


def build_analysis_response(row: LLMAnalysis) -> AnalysisResponse:
    """Shape a persisted LLMAnalysis row into the frontend response model.

    Args:
        row: Persisted analysis row.

    Returns:
        AnalysisResponse with defensively extracted summary fields;
        recommendations that fail validation are skipped rather than 500ing.
    """
    recommendations: list[RecommendationResponse] = []
    for item in row.recommendations:
        try:
            recommendations.append(RecommendationResponse.model_validate(item))
        except Exception:
            logger.warning("analysis_recommendation_invalid", extra={"analysis_id": str(row.id)})
    return AnalysisResponse(
        id=row.id,
        riot_account_id=row.riot_account_id,
        champion_name=row.champion_name,
        rank_tier=row.rank_tier,
        match_count=len(row.match_ids),
        recommendations=recommendations,
        overall_assessment=_payload_str(row.output_payload, "overall_assessment"),
        selection_bias_summary=_payload_str(row.output_payload, "selection_bias_summary"),
        model_name=row.model_name,
        created_at=row.created_at,
    )


async def _latest_analysis(
    session: AsyncSession,
    riot_account_id: Any,
    champion_name: str,
    since: datetime | None = None,
) -> LLMAnalysis | None:
    """Return the newest analysis row for an account + champion."""
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


@router.post(
    "/riot-accounts/{riot_account_id}/analysis",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_analysis(
    riot_account_id: str,
    payload: AnalysisEnqueueRequest,
    session: AsyncSession = Depends(get_session),
) -> AnalysisEnqueueResponse:
    """Enqueue an LLM analysis job for an account + champion.

    Short-circuits to "already_exists" when an analysis for the same
    account + champion was created within the last 24 hours.

    Args:
        riot_account_id: Riot account UUID or Riot ID.
        payload: Champion id and optional rank tier.
        session: Async database session.

    Returns:
        Enqueue status with the resolved champion name for polling.
    """
    account = await resolve_riot_account_identifier(session, riot_account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Riot account not found",
        )
    champion = await get_champion_by_id(session, payload.champion_id)
    if champion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Champion not found",
        )

    cutoff = datetime.now(UTC) - timedelta(hours=ANALYSIS_CACHE_HOURS)
    existing = await _latest_analysis(session, account.id, champion.name, since=cutoff)
    if existing is not None:
        logger.info(
            "analysis_cache_hit",
            extra={"riot_account_id": str(account.id), "champion_name": champion.name},
        )
        return AnalysisEnqueueResponse(
            status="already_exists",
            analysis_id=existing.id,
            champion_name=champion.name,
        )

    # Deterministic id dedupes concurrent clicks; the worker registers the
    # job with a short keep_result (background_jobs.py) so a failed run
    # frees the id for retries in seconds. Day bucket is a residual guard.
    job_id = f"llm-{account.id}-{payload.champion_id}-{date.today().isoformat()}"
    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "llm_analysis_job",
        str(account.id),
        str(payload.champion_id),
        payload.rank_tier,
        _job_id=job_id,
    )
    # A None job means the id is already enqueued/in-flight — same outcome for the client.
    logger.info(
        "analysis_enqueued",
        extra={"job_id": job_id, "deduped": job is None},
    )
    return AnalysisEnqueueResponse(status="enqueued", champion_name=champion.name)


@router.get("/riot-accounts/{riot_account_id}/analysis", status_code=status.HTTP_200_OK)
async def get_analysis(
    riot_account_id: str,
    champion_name: str = Query(description="Champion name returned by the enqueue endpoint"),
    session: AsyncSession = Depends(get_session),
) -> AnalysisResponse | None:
    """Return the latest analysis for an account + champion, or null.

    A null body means no analysis exists yet — the frontend keeps polling.

    Args:
        riot_account_id: Riot account UUID or Riot ID.
        champion_name: Champion name to look up.
        session: Async database session.

    Returns:
        Latest AnalysisResponse, or None when no row exists.
    """
    account = await resolve_riot_account_identifier(session, riot_account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Riot account not found",
        )
    row = await _latest_analysis(session, account.id, champion_name)
    if row is None:
        return None
    return build_analysis_response(row)
