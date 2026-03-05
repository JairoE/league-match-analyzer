"""Enqueue timeline pre-fetch jobs.

Mirrors ``enqueue_match_details.py`` but targets timeline caching
instead of match detail backfill.  Timelines are historical and
never change, so once cached in Redis they stay forever.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services.arq_pool import get_arq_pool

logger = get_logger("league_api.services.enqueue_match_timelines")

BATCH_SIZE = 5


async def enqueue_missing_timeline_jobs(
    match_ids: list[str],
) -> int:
    """Enqueue ARQ timeline-cache jobs for a list of Riot match IDs.

    Each batch is idempotent — the job itself checks Redis before
    hitting the Riot API, and the deterministic ``_job_id`` prevents
    ARQ from scheduling duplicates.

    Args:
        match_ids: Riot match ID strings to pre-fetch timelines for.

    Returns:
        Number of match IDs enqueued.
    """
    if not match_ids:
        return 0

    pool = await get_arq_pool()
    enqueued = 0
    sorted_ids = sorted(match_ids)

    for i in range(0, len(sorted_ids), BATCH_SIZE):
        batch = sorted_ids[i : i + BATCH_SIZE]
        job_id = f"timeline:{batch[0]}..{batch[-1]}:{len(batch)}"
        await pool.enqueue_job("fetch_timeline_cache_job", batch, _job_id=job_id)
        enqueued += len(batch)

    logger.info(
        "enqueue_missing_timelines_done",
        extra={"total": len(match_ids), "enqueued": enqueued},
    )
    return enqueued
