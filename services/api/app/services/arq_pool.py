"""Lazy ARQ Redis pool for enqueueing jobs from the FastAPI process."""

from __future__ import annotations

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("league_api.services.arq_pool")

_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    """Return or lazily create the shared ARQ Redis pool.

    Returns:
        ArqRedis pool for enqueuing jobs.
    """
    global _arq_pool
    if _arq_pool is None:
        settings = get_settings()
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        _arq_pool = await create_pool(redis_settings)
        logger.info("arq_pool_created")
    return _arq_pool


async def close_arq_pool() -> None:
    """Close the ARQ pool on shutdown."""
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.aclose()
        _arq_pool = None
        logger.info("arq_pool_closed")
