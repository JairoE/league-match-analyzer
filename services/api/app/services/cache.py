from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redaction import redact_url


_redis_client: Redis | None = None
logger = get_logger("league_api.cache")


def get_redis() -> Redis:
    """Create or return the shared Redis client.

    Returns:
        Redis client instance connected to the configured URL.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        logger.info("redis_connect", extra={"redis_url": redact_url(settings.redis_url)})
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client
