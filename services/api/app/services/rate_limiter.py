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
        "account": RateLimitConfig(max_requests=20, window_seconds=1),
        "summoner": RateLimitConfig(max_requests=20, window_seconds=1),
        "rank": RateLimitConfig(max_requests=20, window_seconds=1),
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

    async def _get_window_state(
        self, key: str, window_start: float
    ) -> tuple[int, float | None]:
        """Get request count and oldest timestamp in the window.

        Args:
            key: Redis key for the bucket.
            window_start: Start timestamp of the window.

        Returns:
            Tuple of (count, oldest_timestamp) in the window.
        """
        r = await self._get_redis()
        pipe = r.pipeline(transaction=False)
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zcard(key)
        pipe.zrange(key, 0, 0, withscores=True)
        _, count, oldest = await pipe.execute()
        oldest_score = oldest[0][1] if oldest else None
        logger.debug(
            "rate_limit_window_state",
            extra={
                "key": key,
                "count": count,
                "window_start": window_start,
                "oldest_score": oldest_score,
            },
        )
        return int(count), oldest_score

    async def _record_request(self, key: str, now: float, ttl_seconds: int) -> None:
        """Record a request in the sliding window.

        Args:
            key: Redis key for the bucket.
            now: Current timestamp.
            ttl_seconds: TTL for the key.
        """
        r = await self._get_redis()
        request_id = f"{now}:{random.random()}"
        pipe = r.pipeline(transaction=False)
        pipe.zadd(key, {request_id: now})
        pipe.expire(key, ttl_seconds + 1)
        await pipe.execute()
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

        count, oldest_score = await self._get_window_state(key, window_start)

        if count >= limit.max_requests:
            # Calculate wait time until oldest request expires
            if oldest_score is not None:
                wait = max(0.0, oldest_score + limit.window_seconds - now)
            else:
                wait = limit.window_seconds / limit.max_requests
            logger.info(
                "rate_limit_exceeded",
                extra={
                    "bucket": bucket,
                    "count": count,
                    "max": limit.max_requests,
                    "wait_seconds": wait,
                    "oldest_score": oldest_score,
                },
            )
            return False, wait

        return True, 0.0

    async def _check_all_buckets(self, bucket: str) -> tuple[bool, float]:
        """Check the method bucket and all app-level buckets.

        Args:
            bucket: Rate limit bucket name for the endpoint.

        Returns:
            Tuple of (allowed, max_wait_seconds) across all applicable buckets.
        """
        allowed, wait_seconds = await self.check_limit(bucket)
        if not allowed:
            return False, wait_seconds

        for app_bucket in ["app_short", "app_long"]:
            if app_bucket != bucket:
                app_allowed, app_wait = await self.check_limit(app_bucket)
                if not app_allowed:
                    return False, max(wait_seconds, app_wait)

        return True, 0.0

    async def _record_all_buckets(self, bucket: str) -> None:
        """Record a request in the method bucket and all app-level buckets.

        Avoids double-counting when the bucket itself is an app-level bucket.

        Args:
            bucket: Rate limit bucket name for the endpoint.
        """
        now = time.time()
        recorded: set[str] = set()

        # Record in the method bucket
        limit = self.DEFAULT_LIMITS.get(bucket) or self.METHOD_LIMITS.get(bucket)
        if limit:
            await self._record_request(
                self._get_key(bucket), now, limit.window_seconds
            )
            recorded.add(bucket)

        # Record in app-level buckets (skip if already recorded above)
        for app_bucket, app_limit in self.DEFAULT_LIMITS.items():
            if app_bucket not in recorded:
                await self._record_request(
                    self._get_key(app_bucket), now, app_limit.window_seconds
                )

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
            allowed, wait_seconds = await self._check_all_buckets(bucket)

            if allowed:
                await self._record_all_buckets(bucket)
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

    def update_from_headers(self, bucket: str, headers: dict[str, str]) -> None:
        """Update rate limit configs from Riot response headers.

        Retrieves: Riot app/method rate limit headers from responses.
        Transforms: Applies smallest and largest app windows, and most
            restrictive method window for the requested bucket.
        Why: Keeps limiter aligned with Riot-provided limits.

        Args:
            bucket: Rate limit bucket name for this endpoint.
            headers: Response headers from Riot API.
        """
        normalized_headers = {key.lower(): value for key, value in headers.items()}

        app_limit_header = normalized_headers.get("x-app-rate-limit")
        app_count_header = normalized_headers.get("x-app-rate-limit-count")
        method_limit_header = normalized_headers.get("x-method-rate-limit")
        method_count_header = normalized_headers.get("x-method-rate-limit-count")

        # Backward-compatible fallback for legacy/non-Riot header names.
        legacy_limit_header = normalized_headers.get("x-rate-limit")
        legacy_count_header = normalized_headers.get("x-rate-limit-count")
        legacy_limit_type = normalized_headers.get("x-rate-limit-type")

        if app_count_header or method_count_header or legacy_count_header:
            logger.debug(
                "rate_limit_counts_seen",
                extra={
                    "bucket": bucket,
                    "app_counts": app_count_header,
                    "method_counts": method_count_header,
                    "legacy_counts": legacy_count_header,
                    "legacy_type": legacy_limit_type,
                },
            )

        # Riot application headers: e.g. X-App-Rate-Limit: 20:1,100:120
        if app_limit_header:
            parsed_app = self._parse_rate_limit_header(app_limit_header)
            if parsed_app:
                parsed_app.sort(key=lambda item: item[1])
                smallest = parsed_app[0]
                largest = parsed_app[-1]
                self.DEFAULT_LIMITS["app_short"] = RateLimitConfig(
                    max_requests=smallest[0], window_seconds=smallest[1]
                )
                self.DEFAULT_LIMITS["app_long"] = RateLimitConfig(
                    max_requests=largest[0], window_seconds=largest[1]
                )
                logger.info(
                    "rate_limit_app_updated",
                    extra={
                        "short": smallest,
                        "long": largest,
                        "bucket": bucket,
                    },
                )

        # Riot method headers: e.g. X-Method-Rate-Limit: 1000:60
        if method_limit_header:
            parsed_method = self._parse_rate_limit_header(method_limit_header)
            if parsed_method:
                parsed_method.sort(key=lambda item: item[1])
                max_requests, window_seconds = parsed_method[0]
                self.METHOD_LIMITS[bucket] = RateLimitConfig(
                    max_requests=max_requests, window_seconds=window_seconds
                )
                logger.info(
                    "rate_limit_method_updated",
                    extra={"bucket": bucket, "limit": (max_requests, window_seconds)},
                )

        # Legacy fallback when app/method headers are not present.
        if app_limit_header or method_limit_header or not legacy_limit_header:
            return

        parsed_legacy = self._parse_rate_limit_header(legacy_limit_header)
        if not parsed_legacy:
            return
        parsed_legacy.sort(key=lambda item: item[1])
        max_requests, window_seconds = parsed_legacy[0]

        if legacy_limit_type == "application":
            smallest = parsed_legacy[0]
            largest = parsed_legacy[-1]
            self.DEFAULT_LIMITS["app_short"] = RateLimitConfig(
                max_requests=smallest[0], window_seconds=smallest[1]
            )
            self.DEFAULT_LIMITS["app_long"] = RateLimitConfig(
                max_requests=largest[0], window_seconds=largest[1]
            )
            logger.info(
                "rate_limit_app_updated_legacy",
                extra={"short": smallest, "long": largest, "bucket": bucket},
            )
            return

        self.METHOD_LIMITS[bucket] = RateLimitConfig(
            max_requests=max_requests, window_seconds=window_seconds
        )
        logger.info(
            "rate_limit_method_updated_legacy",
            extra={"bucket": bucket, "limit": (max_requests, window_seconds)},
        )

    @staticmethod
    def _parse_rate_limit_header(value: str) -> list[tuple[int, int]]:
        """Parse X-Rate-Limit header into (max, window) pairs."""
        parsed: list[tuple[int, int]] = []
        for part in value.split(","):
            chunk = part.strip()
            if not chunk or ":" not in chunk:
                continue
            max_str, window_str = chunk.split(":", 1)
            try:
                parsed.append((int(max_str), int(window_str)))
            except ValueError:
                logger.warning(
                    "rate_limit_header_parse_error",
                    extra={"value": value, "chunk": chunk},
                )
        return parsed

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
