"""Scheduled jobs for ARQ cron tasks.

Contains orchestrator jobs that run on a schedule.
"""

from __future__ import annotations

import time

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.services.riot_accounts import list_all_active_riot_accounts
from app.services.worker_metrics import increment_metric_safe

logger = get_logger("league_api.jobs.scheduled")


async def sync_all_riot_accounts_matches(ctx: dict) -> dict:
    """Scheduled job: Enqueue match sync for all active riot accounts.

    Retrieves: All riot accounts with recent match activity.
    Transforms: Enqueues fetch_riot_account_matches_job for each.
    Why: Periodic ingestion keeps match data fresh for AI analysis.

    Args:
        ctx: ARQ worker context with redis pool.

    Returns:
        Dict with account count and enqueue status.
    """
    logger.info("sync_all_riot_accounts_matches_start")
    await increment_metric_safe("jobs.sync_all_riot_accounts_matches.started")

    redis = ctx.get("redis")
    if not redis:
        logger.error("sync_all_riot_accounts_matches_no_redis")
        await increment_metric_safe(
            "jobs.sync_all_riot_accounts_matches.failed",
            tags={"reason": "no_redis"},
        )
        return {"status": "error", "error": "no_redis_context"}

    async with async_session_factory() as session:
        accounts = await list_all_active_riot_accounts(session, active_window_days=7)

    if not accounts:
        logger.info("sync_all_riot_accounts_matches_no_accounts")
        await increment_metric_safe("jobs.sync_all_riot_accounts_matches.success")
        return {"status": "ok", "accounts_queued": 0}

    enqueued = 0
    for account in accounts:
        try:
            await redis.enqueue_job(
                "fetch_riot_account_matches_job",
                str(account.id),
                _job_id=f"sync_matches_{account.id}_{int(time.time())}",
            )
            enqueued += 1
            logger.info(
                "sync_all_riot_accounts_matches_enqueued",
                extra={"riot_account_id": str(account.id), "riot_id": account.riot_id},
            )
        except Exception as exc:
            logger.error(
                "sync_all_riot_accounts_matches_enqueue_error",
                extra={"riot_account_id": str(account.id), "error": str(exc)},
            )
            await increment_metric_safe(
                "jobs.sync_all_riot_accounts_matches.enqueue_failed",
                tags={"reason": "enqueue_exception"},
            )

    logger.info(
        "sync_all_riot_accounts_matches_done",
        extra={"total_accounts": len(accounts), "enqueued": enqueued},
    )
    await increment_metric_safe("jobs.sync_all_riot_accounts_matches.success")
    await increment_metric_safe(
        "jobs.sync_all_riot_accounts_matches.accounts_enqueued", amount=enqueued
    )

    return {
        "status": "ok",
        "total_accounts": len(accounts),
        "accounts_queued": enqueued,
    }
