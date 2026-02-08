"""Scheduled jobs for ARQ cron tasks.

Contains orchestrator jobs that run on a schedule.
"""

from __future__ import annotations

import time

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.services.users import list_all_active_users

logger = get_logger("league_api.jobs.scheduled")


async def sync_all_users_matches(ctx: dict) -> dict:
    """Scheduled job: Enqueue match sync for all users.

    Retrieves: All users from the database.
    Transforms: Enqueues fetch_user_matches_job for each user.
    Why: Periodic ingestion keeps match data fresh for AI analysis.

    Args:
        ctx: ARQ worker context with redis pool.

    Returns:
        Dict with user count and enqueue status.
    """
    logger.info("sync_all_users_matches_start")

    redis = ctx.get("redis")
    if not redis:
        logger.error("sync_all_users_matches_no_redis")
        return {"status": "error", "error": "no_redis_context"}

    async with async_session_factory() as session:
        users = await list_all_active_users(session, active_window_days=7)

    if not users:
        logger.info("sync_all_users_matches_no_users")
        return {"status": "ok", "users_queued": 0}

    enqueued = 0
    for user in users:
        try:
            await redis.enqueue_job(
                "fetch_user_matches_job",
                str(user.id),
                _job_id=f"sync_matches_{user.id}_{int(time.time())}",
            )
            enqueued += 1
            logger.info(
                "sync_all_users_matches_enqueued",
                extra={"user_id": str(user.id), "riot_id": user.riot_id},
            )
        except Exception as exc:
            logger.error(
                "sync_all_users_matches_enqueue_error",
                extra={"user_id": str(user.id), "error": str(exc)},
            )

    logger.info(
        "sync_all_users_matches_done",
        extra={"total_users": len(users), "enqueued": enqueued},
    )

    return {
        "status": "ok",
        "total_users": len(users),
        "users_queued": enqueued,
    }
