from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger("league_api.jobs")


async def on_startup(ctx: dict) -> None:
    """Log ARQ worker startup.

    Args:
        ctx: Worker context dictionary.

    Returns:
        None.
    """
    logger.info("arq_startup")


async def on_shutdown(ctx: dict) -> None:
    """Log ARQ worker shutdown.

    Args:
        ctx: Worker context dictionary.

    Returns:
        None.
    """
    logger.info("arq_shutdown")


class WorkerSettings:
    """ARQ worker configuration for background processing."""

    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = []
    on_startup = on_startup
    on_shutdown = on_shutdown
