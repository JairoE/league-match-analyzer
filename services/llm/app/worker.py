"""ARQ worker configuration for LLM jobs."""

from arq.connections import RedisSettings

from app.config import get_settings
from app.logging import get_logger, setup_logging


setup_logging()
logger = get_logger("league_llm.worker")


async def on_startup(ctx: dict) -> None:
    """Initialize worker resources on startup.

    Args:
        ctx: Worker context dictionary.

    Returns:
        None.
    """
    logger.info("llm_worker_startup")


async def on_shutdown(ctx: dict) -> None:
    """Clean up worker resources on shutdown.

    Args:
        ctx: Worker context dictionary.

    Returns:
        None.
    """
    logger.info("llm_worker_shutdown")


class WorkerSettings:
    """ARQ worker settings for LLM background processing."""

    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions: list = []
    on_startup = on_startup
    on_shutdown = on_shutdown
