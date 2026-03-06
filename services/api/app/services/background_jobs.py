from arq.connections import RedisSettings
from arq.cron import cron
from arq.worker import func

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.jobs.match_ingestion import (
    fetch_match_details_job,
    fetch_riot_account_matches_job,
    fetch_timeline_cache_job,
)
from app.jobs.scheduled import sync_all_riot_accounts_matches
from app.jobs.timeline_extraction import extract_match_timeline_job
from app.services.riot_api_client import RiotApiClient

logger = get_logger("league_api.jobs")


async def on_startup(ctx: dict) -> None:
    """Initialize shared resources for ARQ workers.

    Creates a shared RiotApiClient so all jobs reuse the same
    HTTP connection pool and rate limiter instance. Also sets up
    structured logging so worker logs use the same formatter as the API.

    Args:
        ctx: Worker context dictionary.
    """
    setup_logging()
    ctx["riot_client"] = RiotApiClient()
    logger.info("arq_startup")


async def on_shutdown(ctx: dict) -> None:
    """Clean up shared resources on ARQ worker shutdown.

    Args:
        ctx: Worker context dictionary.
    """
    client: RiotApiClient | None = ctx.get("riot_client")
    if client:
        await client.close()
    logger.info("arq_shutdown")


class WorkerSettings:
    """ARQ worker configuration for background processing.

    Manages scheduled and on-demand jobs for match ingestion.
    Jobs run with rate limiting to respect Riot API limits.
    """

    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # On-demand job functions
    functions = [
        fetch_riot_account_matches_job,
        fetch_match_details_job,
        fetch_timeline_cache_job,
        func(extract_match_timeline_job, max_tries=5),
    ]

    # Scheduled cron jobs
    # sync_all_riot_accounts_matches runs every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
    cron_jobs = [
        cron(
            sync_all_riot_accounts_matches,
            hour={0, 6, 12, 18},
            minute={0},
            run_at_startup=settings.arq_cron_run_at_startup,
        ),
    ]

    on_startup = on_startup
    on_shutdown = on_shutdown
