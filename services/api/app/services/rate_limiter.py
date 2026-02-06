"""Redis-backed rate limiter for Riot API's 3-tier rate limit system.

Implements sliding window counters using Redis sorted sets.
Handles app-level, method-level, and service-level rate limits.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("league_api.services.rate_limiter")


@dataclass
class RateLimitConfig:
    """Configuration for a single rate limit bucket.

    Attributes:
        max_requests: Maximum requests allowed in the window.
        window_seconds: Time window in seconds.
    """

    max_requests: int
    window_seconds: int


class RiotRateLimiter:
    """Redis-backed rate limiter for Riot's 3-tier limits.

    Retrieves: Current request counts from Redis sorted sets.
    Transforms: Sliding window algorithm with automatic cleanup.
    Why: Prevents 429 errors by proactively throttling requests.
    """

    # Default Riot rate limits (development key limits)
    # Production keys have higher limits, configurable via headers
    DEFAULT_LIMITS: dict[str, RateLimitConfig] = {
        "app_short": RateLimitConfig(max_requests=20, window_seconds=1),
        "app_long": RateLimitConfig(max_requests=100, window_seconds=120),
    }

    # Method-specific limits (some endpoints have stricter limits)
    METHOD_LIMITS: dict[str, RateLimitConfig] = {
        "match_ids": RateLimitConfig(max_requests=2000, window_seconds=10),
        "match_detail": RateLimitConfig(max_requests=2000, window_seconds=10),
    }

    # Backoff configuration
    MAX_RETRIES = 5
    BASE_BACKOFF_SECONDS = 1.0
    MAX_BACKOFF_SECONDS = 60.0
    JITTER_FACTOR = 0.5

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        """Initialize rate limiter with optional Redis client.

        Args:
            redis_client: Optional Redis client. Creates one if not provided.
        """
        self._settings = get_settings()
        self._redis: redis.Redis | None = redis_client
        self._retry_after: float = 0.0

    async def _get_redis(self) -> redis.Redis:
        """Lazy initialization of Redis client.

        Returns:
            Redis async client instance.
        """
        if self._redis is None:
            self._redis = redis.from_url(
                self._settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    def _get_key(self, bucket: str) -> str:
        """Build Redis key for rate limit bucket.

        Args:
            bucket: Rate limit bucket name.

        Returns:
            Redis key string.
        """
        return f"rl:{bucket}"

    async def _count_requests_in_window(
        self, key: str, window_start: float, now: float
    ) -> int:
        """Count requests in the sliding window.

        Args:
            key: Redis key for the bucket.
            window_start: Start timestamp of the window.
            now: Current timestamp.

        Returns:
            Number of requests in the window.
        """
        r = await self._get_redis()
        # Remove expired entries
        await r.zremrangebyscore(key, "-inf", window_start)
        # Count remaining entries
        count = await r.zcard(key)
        logger.debug(
            "rate_limit_count",
            extra={"key": key, "count": count, "window_start": window_start},
        )
        return count

    async def _record_request(self, key: str, now: float, ttl_seconds: int) -> None:
        """Record a request in the sliding window.

        Args:
            key: Redis key for the bucket.
            now: Current timestamp.
            ttl_seconds: TTL for the key.
        """
        r = await self._get_redis()
        # Add request with current timestamp as score
        request_id = f"{now}:{random.random()}"
        await r.zadd(key, {request_id: now})
        # Set expiry on the key
        await r.expire(key, ttl_seconds + 1)
        logger.debug("rate_limit_record", extra={"key": key, "request_id": request_id})

    async def check_limit(self, bucket: str) -> tuple[bool, float]:
        """Check if request is within rate limit.

        Args:
            bucket: Rate limit bucket name (e.g., 'app_short', 'match_ids').

        Returns:
            Tuple of (allowed, wait_seconds). If allowed is False, wait_seconds
            indicates how long to wait before retrying.
        """
        now = time.time()

        # Check global retry-after from 429 response
        if self._retry_after > now:
            wait = self._retry_after - now
            logger.info(
                "rate_limit_global_backoff",
                extra={"bucket": bucket, "wait_seconds": wait},
            )
            return False, wait

        # Get limit config for bucket
        limit = self.DEFAULT_LIMITS.get(bucket) or self.METHOD_LIMITS.get(bucket)
        if not limit:
            # Unknown bucket, allow but log warning
            logger.warning("rate_limit_unknown_bucket", extra={"bucket": bucket})
            return True, 0.0

        key = self._get_key(bucket)
        window_start = now - limit.window_seconds

        count = await self._count_requests_in_window(key, window_start, now)

        if count >= limit.max_requests:
            # Calculate wait time (time until oldest request expires)
            wait = limit.window_seconds / limit.max_requests
            logger.info(
                "rate_limit_exceeded",
                extra={
                    "bucket": bucket,
                    "count": count,
                    "max": limit.max_requests,
                    "wait_seconds": wait,
                },
            )
            return False, wait

        return True, 0.0

    async def acquire(self, bucket: str) -> bool:
        """Check and acquire a rate limit slot.

        Args:
            bucket: Rate limit bucket name.

        Returns:
            True if slot acquired, False if rate limited.
        """
        allowed, _ = await self.check_limit(bucket)
        if not allowed:
            return False

        # Check app-level limits too
        for app_bucket in ["app_short", "app_long"]:
            if app_bucket != bucket:
                app_allowed, _ = await self.check_limit(app_bucket)
                if not app_allowed:
                    return False

        # Record the request in all applicable buckets
        now = time.time()
        limit = self.DEFAULT_LIMITS.get(bucket) or self.METHOD_LIMITS.get(bucket)
        if limit:
            await self._record_request(
                self._get_key(bucket), now, limit.window_seconds
            )

        # Always record in app-level buckets
        for app_bucket, app_limit in self.DEFAULT_LIMITS.items():
            await self._record_request(
                self._get_key(app_bucket), now, app_limit.window_seconds
            )

        logger.debug("rate_limit_acquired", extra={"bucket": bucket})
        return True

    async def wait_if_needed(self, bucket: str) -> None:
        """Block until a rate limit slot is available.

        Uses exponential backoff with jitter when rate limited.

        Args:
            bucket: Rate limit bucket name.

        Raises:
            RuntimeError: If max retries exceeded.
        """
        retries = 0

        while retries < self.MAX_RETRIES:
            allowed, wait_seconds = await self.check_limit(bucket)

            # Also check app-level limits
            if allowed:
                for app_bucket in ["app_short", "app_long"]:
                    if app_bucket != bucket:
                        app_allowed, app_wait = await self.check_limit(app_bucket)
                        if not app_allowed:
                            allowed = False
                            wait_seconds = max(wait_seconds, app_wait)
                            break

            if allowed:
                # Record the request
                now = time.time()
                limit = (
                    self.DEFAULT_LIMITS.get(bucket) or self.METHOD_LIMITS.get(bucket)
                )
                if limit:
                    await self._record_request(
                        self._get_key(bucket), now, limit.window_seconds
                    )

                for app_bucket, app_limit in self.DEFAULT_LIMITS.items():
                    await self._record_request(
                        self._get_key(app_bucket), now, app_limit.window_seconds
                    )

                logger.debug(
                    "rate_limit_wait_complete",
                    extra={"bucket": bucket, "retries": retries},
                )
                return

            # Calculate backoff with jitter
            backoff = min(
                self.BASE_BACKOFF_SECONDS * (2**retries),
                self.MAX_BACKOFF_SECONDS,
            )
            jitter = backoff * self.JITTER_FACTOR * random.random()
            sleep_time = max(wait_seconds, backoff + jitter)

            logger.info(
                "rate_limit_waiting",
                extra={
                    "bucket": bucket,
                    "retry": retries,
                    "sleep_seconds": sleep_time,
                },
            )

            await asyncio.sleep(sleep_time)
            retries += 1

        logger.error(
            "rate_limit_max_retries",
            extra={"bucket": bucket, "retries": retries},
        )
        raise RuntimeError(f"Rate limit max retries exceeded for bucket: {bucket}")

    def set_retry_after(self, seconds: float) -> None:
        """Set global retry-after from 429 response.

        Called when Riot API returns 429 with Retry-After header.

        Args:
            seconds: Seconds to wait before next request.
        """
        self._retry_after = time.time() + seconds
        logger.warning(
            "rate_limit_429_received",
            extra={"retry_after_seconds": seconds},
        )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Singleton instance for shared rate limiting
_rate_limiter: RiotRateLimiter | None = None


def get_rate_limiter() -> RiotRateLimiter:
    """Get or create the singleton rate limiter instance.

    Returns:
        Shared RiotRateLimiter instance.
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RiotRateLimiter()
    return _rate_limiter
