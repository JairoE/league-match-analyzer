"""Enqueue timeline pre-fetch jobs.

Mirrors ``enqueue_match_details.py`` but targets timeline caching
instead of match detail backfill.  Timelines are historical and
never change, so once cached in Redis they stay forever.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services.arq_pool import get_arq_pool
from app.services.cache import get_redis
from app.services.riot_match_id import normalize_match_id

logger = get_logger("league_api.services.enqueue_match_timelines")

BATCH_SIZE = 5


async def enqueue_missing_timeline_jobs(
    match_ids: list[str],
) -> int:
    """Enqueue ARQ timeline-cache jobs for match IDs not yet cached in Redis.

    Performs a bulk Redis MGET to skip already-cached timelines, then
    enqueues ``fetch_timeline_cache_job`` only for the remainder.
    Deterministic ``_job_id`` prevents ARQ from scheduling duplicates.

    Args:
        match_ids: Riot match ID strings to pre-fetch timelines for.

    Returns:
        Number of match IDs enqueued.
    """
    if not match_ids:
        return 0

    redis = get_redis()
    normalized = [(mid, normalize_match_id(mid)[0]) for mid in match_ids]
    cache_keys = [f"timeline:{riot_id}" for _, riot_id in normalized]

    cached_values = await redis.mget(cache_keys)
    uncached = [mid for (mid, _), val in zip(normalized, cached_values) if val is None]

    if not uncached:
        logger.info(
            "enqueue_missing_timelines_all_cached",
            extra={"checked": len(match_ids)},
        )
        return 0

    try:
        pool = await get_arq_pool()
    except Exception:
        logger.warning("enqueue_missing_timelines_pool_unavailable")
        return 0

    enqueued = 0
    sorted_ids = sorted(uncached)

    for i in range(0, len(sorted_ids), BATCH_SIZE):
        batch = sorted_ids[i : i + BATCH_SIZE]
        job_id = f"timeline:{batch[0]}..{batch[-1]}:{len(batch)}"
        try:
            await pool.enqueue_job("fetch_timeline_cache_job", batch, _job_id=job_id)
            enqueued += len(batch)
        except Exception:
            logger.warning(
                "enqueue_missing_timelines_batch_failed",
                extra={"job_id": job_id, "batch_size": len(batch)},
            )

    already_cached = len(match_ids) - len(uncached)
    logger.info(
        "enqueue_missing_timelines_done",
        extra={
            "total": len(match_ids),
            "already_cached": already_cached,
            "enqueued": enqueued,
        },
    )
    return enqueued
