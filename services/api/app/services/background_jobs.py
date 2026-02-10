from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import get_settings
from app.core.logging import get_logger
from app.jobs.match_ingestion import fetch_match_details_job, fetch_user_matches_job
from app.jobs.scheduled import sync_all_users_matches
from app.services.riot_api_client import RiotApiClient

logger = get_logger("league_api.jobs")


async def on_startup(ctx: dict) -> None:
    """Initialize shared resources for ARQ workers.

    Creates a shared RiotApiClient so all jobs reuse the same
    HTTP connection pool and rate limiter instance.

    Args:
        ctx: Worker context dictionary.
    """
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
        fetch_user_matches_job,
        fetch_match_details_job,
    ]

    # Scheduled cron jobs
    # sync_all_users_matches runs every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
    cron_jobs = [
        cron(
            sync_all_users_matches,
            hour={0, 6, 12, 18},
            minute={0},
            run_at_startup=False,
        ),
    ]

    on_startup = on_startup
    on_shutdown = on_shutdown
