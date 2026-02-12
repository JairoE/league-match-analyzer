"""Lazy ARQ Redis pool for enqueueing jobs from the FastAPI process."""

from __future__ import annotations

import asyncio

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("league_api.services.arq_pool")

_arq_pool_task: asyncio.Task[ArqRedis] | None = None


async def _create_arq_pool() -> ArqRedis:
    """Create the ARQ Redis pool once."""
    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    pool = await create_pool(redis_settings)
    logger.info("arq_pool_created")
    return pool


async def get_arq_pool() -> ArqRedis:
    """Return or lazily create the shared ARQ Redis pool.

    Returns:
        ArqRedis pool for enqueuing jobs.
    """
    global _arq_pool_task
    if _arq_pool_task is None:
        _arq_pool_task = asyncio.create_task(_create_arq_pool())
        logger.debug("arq_pool_task_created")
    task = _arq_pool_task
    try:
        return await task
    except Exception:
        if _arq_pool_task is task:
            _arq_pool_task = None
        logger.exception("arq_pool_create_failed")
        raise


async def close_arq_pool() -> None:
    """Close the ARQ pool on shutdown."""
    global _arq_pool_task
    if _arq_pool_task is None:
        return
    task = _arq_pool_task
    try:
        pool = await task
    except Exception:
        if _arq_pool_task is task:
            _arq_pool_task = None
        logger.exception("arq_pool_close_failed_create")
        return
    await pool.aclose()
    if _arq_pool_task is task:
        _arq_pool_task = None
    logger.info("arq_pool_closed")
