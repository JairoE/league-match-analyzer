"""Enqueue match detail fetch jobs from the FastAPI process."""

from __future__ import annotations

from sqlalchemy import String, cast, or_
from sqlmodel import select

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.match import Match
from app.services.arq_pool import get_arq_pool

logger = get_logger("league_api.services.enqueue_match_details")

BATCH_SIZE = 5


async def enqueue_missing_detail_jobs(match_ids: list[str]) -> int:
    """Enqueue ARQ detail-fetch jobs for matches with NULL game_info.

    Queries the DB for matches in ``match_ids`` that lack game_info,
    then enqueues ``fetch_match_details_job`` in batches of 5.

    Args:
        match_ids: Riot match IDs to check.

    Returns:
        Number of match IDs enqueued.
    """
    if not match_ids:
        return 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(Match.game_id).where(
                Match.game_id.in_(match_ids),
                or_(
                    Match.game_info.is_(None),
                    cast(Match.game_info, String) == "null",
                ),
            )
        )
        missing_details = [row[0] for row in result.fetchall()]

    if not missing_details:
        logger.info(
            "enqueue_missing_details_none_needed",
            extra={"checked": len(match_ids)},
        )
        return 0

    pool = await get_arq_pool()
    enqueued = 0
    for i in range(0, len(missing_details), BATCH_SIZE):
        batch = missing_details[i : i + BATCH_SIZE]
        await pool.enqueue_job("fetch_match_details_job", batch)
        enqueued += len(batch)

    logger.info(
        "enqueue_missing_details_done",
        extra={"total": len(missing_details), "enqueued": enqueued},
    )
    return enqueued
