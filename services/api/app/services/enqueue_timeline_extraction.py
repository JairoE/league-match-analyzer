"""Enqueue timeline extraction jobs for the LLM data pipeline.

Shared by both the FastAPI process (via ``get_arq_pool``) and the ARQ
worker (which passes its own ``ctx["redis"]`` pool).
"""

from __future__ import annotations

from typing import Protocol

from sqlmodel import select

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.match import Match
from app.models.match_state_vector import MatchStateVector
from app.services.arq_pool import get_arq_pool

logger = get_logger("league_api.services.enqueue_timeline_extraction")


class _EnqueuePool(Protocol):
    async def enqueue_job(self, function_name: str, *args: object, **kwargs: object) -> object: ...


async def enqueue_missing_extraction_jobs(
    match_ids: list[str],
    *,
    pool: _EnqueuePool | None = None,
) -> int:
    """Enqueue ARQ extraction jobs for matches without state vectors.

    Queries the DB for matches in ``match_ids`` that have no rows in
    ``match_state_vector`` yet, then enqueues one
    ``extract_match_timeline_job`` per match with a deterministic
    ``_job_id`` to prevent duplicate scheduling.

    Args:
        match_ids: Riot match IDs to check.
        pool: Optional ARQ-compatible pool.  Falls back to the lazy
              singleton from ``get_arq_pool()`` when not provided.

    Returns:
        Number of match IDs enqueued.
    """
    if not match_ids:
        return 0

    async with async_session_factory() as session:
        already_extracted_result = await session.execute(
            select(MatchStateVector.game_id)
            .where(MatchStateVector.game_id.in_(match_ids))
            .distinct()
        )
        already_extracted = {row[0] for row in already_extracted_result.fetchall()}

        needs_game_info_result = await session.execute(
            select(Match.game_id).where(
                Match.game_id.in_(match_ids),
                Match.game_info.isnot(None),
            )
        )
        has_game_info = {row[0] for row in needs_game_info_result.fetchall()}

    missing = sorted(
        mid for mid in match_ids
        if mid not in already_extracted and mid in has_game_info
    )

    if not missing:
        logger.info(
            "enqueue_missing_extraction_none_needed",
            extra={"checked": len(match_ids), "already_extracted": len(already_extracted)},
        )
        return 0

    if pool is None:
        pool = await get_arq_pool()

    enqueued = 0
    for match_id in missing:
        job_id = f"timeline-extract:{match_id}"
        try:
            await pool.enqueue_job(
                "extract_match_timeline_job", match_id, _job_id=job_id,
            )
            enqueued += 1
        except Exception:
            logger.warning(
                "enqueue_extraction_job_failed",
                extra={"match_id": match_id, "job_id": job_id},
            )

    logger.info(
        "enqueue_missing_extraction_done",
        extra={
            "checked": len(match_ids),
            "already_extracted": len(already_extracted),
            "enqueued": enqueued,
        },
    )
    return enqueued
