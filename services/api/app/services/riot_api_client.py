from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.rate_limiter import RiotRateLimiter, get_rate_limiter

logger = get_logger("league_api.services.riot_api_client")


@dataclass
class RiotRequestError(Exception):
    """Structured error from Riot API calls."""

    message: str
    status: int | None = None
    body: str | None = None


class RiotApiClient:
    """Async Riot API client with rate limiting and retry logic.

    Retrieves: Riot account, summoner, rank, and match payloads.
    Transforms: Minimal mapping, returns raw JSON payloads.
    Why: Provides rate-limited access for both sync handlers and background jobs.
    """

    ACCOUNT_BY_RIOT_ID_URL = "https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
    SUMMONER_BY_PUUID_URL = "https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/"
    RANK_BY_PUUID_URL = "https://na1.api.riotgames.com/lol/league/v4/entries/by-puuid/"
    MATCH_IDS_BY_PUUID_URL = "https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/"
    MATCH_DETAIL_URL = "https://americas.api.riotgames.com/lol/match/v5/matches/"

    # Retry configuration
    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 1.0

    def __init__(self, rate_limiter: RiotRateLimiter | None = None) -> None:
        """Initialize API client with optional rate limiter.

        Args:
            rate_limiter: Optional rate limiter. Uses singleton if not provided.
        """
        self._settings = get_settings()
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "RiotApiClient":
        """Enter async context for deterministic client cleanup."""
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Exit async context and close any open HTTP client."""
        await self.close()

    async def _get_client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        """Create or reuse an async HTTP client.

        Args:
            timeout: Timeout settings for the client.

        Returns:
            Async HTTP client instance.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def fetch_account_by_riot_id(self, game_name: str, tag_line: str) -> dict[str, Any]:
        """Retrieve Riot account payload by Riot ID.

        Retrieves: Riot account payload for gameName#tagLine.
        Transforms: None, returns raw account JSON.
        Why: Ensures we can resolve PUUID for downstream calls.

        Args:
            game_name: Riot ID game name.
            tag_line: Riot ID tag line.

        Returns:
            Riot account payload.
        """
        riot_id = f"{game_name}#{tag_line}"
        logger.info("riot_account_fetch_start", extra={"riot_id": riot_id})
        url = self.ACCOUNT_BY_RIOT_ID_URL + f"{quote(game_name)}/{quote(tag_line)}"
        payload = await self._get_json("account", url)
        return payload

    async def fetch_summoner_by_puuid(self, puuid: str) -> dict[str, Any]:
        """Retrieve summoner payload by PUUID.

        Retrieves: Summoner profile payload by PUUID.
        Transforms: None, returns raw summoner JSON.
        Why: Keeps user profile data aligned with Riot.

        Args:
            puuid: Riot PUUID.

        Returns:
            Summoner payload.
        """
        logger.info("riot_summoner_fetch_start", extra={"puuid": puuid})
        url = self.SUMMONER_BY_PUUID_URL + quote(puuid)
        payload = await self._get_json("summoner", url)
        return payload

    async def fetch_rank_by_puuid(self, puuid: str) -> dict[str, Any]:
        """Retrieve ranked payload by PUUID.

        Retrieves: Ranked entry object for a PUUID.
        Transforms: Returns single ranked entry object.
        Why: Keeps rank requests synchronous with minimal shaping.

        Args:
            puuid: Riot PUUID.

        Returns:
            Ranked entry payload object.
        """
        logger.info("riot_rank_fetch_start", extra={"puuid": puuid})
        url = self.RANK_BY_PUUID_URL + quote(puuid)
        payload = await self._get_json("rank", url)
        if not isinstance(payload, list):
            logger.info("riot_rank_payload_unexpected", extra={"puuid": puuid})
            raise RiotRequestError("unexpected_rank_payload_format", status=502)

        if not payload:  # Empty list check
            logger.info("riot_rank_not_found", extra={"puuid": puuid})
            return {}
    
        return payload[0]

    async def fetch_match_ids_by_puuid(self, puuid: str, start: int, count: int) -> list[str]:
        """Retrieve match ids for a PUUID.

        Retrieves: Riot match ID list for a PUUID.
        Transforms: Casts payload items to strings.
        Why: Allows immediate match list storage in Postgres.

        Args:
            puuid: Riot PUUID.
            start: Start offset for match list.
            count: Number of matches to retrieve.

        Returns:
            List of match identifiers.
        """
        logger.info("riot_match_ids_fetch_start", extra={"puuid": puuid, "start": start, "count": count})
        query = f"?start={start}&count={count}"
        url = self.MATCH_IDS_BY_PUUID_URL + quote(puuid) + "/ids" + query
        payload = await self._get_json("match_ids", url)
        match_ids = [str(item) for item in payload] if isinstance(payload, list) else []
        return match_ids

    async def fetch_match_by_id(self, match_id: str) -> dict[str, Any]:
        """Retrieve match detail by Riot match id.

        Retrieves: Riot match detail payload.
        Transforms: None, returns raw match JSON.
        Why: Supports synchronous match detail responses.

        Args:
            match_id: Riot match ID.

        Returns:
            Match payload.
        """
        logger.info("riot_match_fetch_start", extra={"match_id": match_id})
        url = self.MATCH_DETAIL_URL + quote(match_id)
        payload = await self._get_json("match_detail", url)
        return payload

    async def _get_json(self, bucket: str, url: str) -> dict[str, Any] | list[Any]:
        """Make rate-limited GET request with retry logic.

        Retrieves: JSON payload from Riot API.
        Transforms: Handles 429 responses with Retry-After header.
        Why: Ensures graceful rate limit handling for background jobs.

        Args:
            bucket: Rate limit bucket name for this endpoint.
            url: Full URL to request.

        Returns:
            Parsed JSON response.

        Raises:
            RiotRequestError: On API errors after retries exhausted.
        """
        api_key = self._settings.riot_api_key
        if not api_key or api_key == "replace-me":
            logger.info("riot_api_missing_key", extra={"url": url})
            raise RiotRequestError("missing_riot_api_key", status=401)

        headers = {"X-Riot-Token": api_key}
        timeout = httpx.Timeout(self._settings.riot_api_timeout_seconds)

        retries = 0
        while retries <= self.MAX_RETRIES:
            # Wait for rate limit slot
            await self._rate_limiter.wait_if_needed(bucket)

            logger.info(
                "riot_request_start",
                extra={"url": url, "bucket": bucket, "retry": retries},
            )

            client = await self._get_client(timeout)
            try:
                response = await client.get(url, headers=headers)

                self._rate_limiter.update_from_headers(bucket, dict(response.headers))

                # Handle 429 rate limit response
                if response.status_code == 429:
                    retry_after = self._parse_retry_after(response)
                    self._rate_limiter.set_retry_after(retry_after)
                    logger.warning(
                        "riot_request_429",
                        extra={
                            "url": url,
                            "retry_after": retry_after,
                            "retry": retries,
                        },
                    )
                    retries += 1
                    if retries > self.MAX_RETRIES:
                        break
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()

            except httpx.HTTPStatusError as exc:
                # Retry on server errors (5xx)
                if exc.response.status_code >= 500 and retries < self.MAX_RETRIES:
                    backoff = self.BASE_BACKOFF_SECONDS * (2**retries)
                    jitter = backoff * 0.5 * random.random()
                    sleep_time = backoff + jitter
                    logger.warning(
                        "riot_request_retry",
                        extra={
                            "url": url,
                            "status": exc.response.status_code,
                            "retry": retries,
                            "sleep": sleep_time,
                        },
                    )
                    retries += 1
                    await asyncio.sleep(sleep_time)
                    continue

                logger.info(
                    "riot_request_failed",
                    extra={
                        "url": url,
                        "status": exc.response.status_code,
                        "body": exc.response.text,
                    },
                )
                raise RiotRequestError(
                    "riot_api_failed",
                    status=exc.response.status_code,
                    body=exc.response.text,
                ) from exc

            except httpx.RequestError as exc:
                # Retry on network errors
                if retries < self.MAX_RETRIES:
                    backoff = self.BASE_BACKOFF_SECONDS * (2**retries)
                    logger.warning(
                        "riot_request_network_retry",
                        extra={"url": url, "error": str(exc), "retry": retries},
                    )
                    retries += 1
                    await asyncio.sleep(backoff)
                    continue

                logger.info(
                    "riot_request_error",
                    extra={"url": url, "detail": str(exc)},
                )
                raise RiotRequestError(
                    "riot_api_failed", status=502, body=str(exc)
                ) from exc

            logger.info(
                "riot_request_ok",
                extra={"url": url, "status": response.status_code},
            )
            return response.json()

        # Max retries exceeded
        logger.error(
            "riot_request_max_retries",
            extra={"url": url, "retries": retries},
        )
        raise RiotRequestError(
            "riot_api_max_retries_exceeded",
            status=429,
            body=f"Max retries ({self.MAX_RETRIES}) exceeded",
        )

    def _parse_retry_after(self, response: httpx.Response) -> float:
        """Parse Retry-After header from 429 response.

        Args:
            response: HTTP response with 429 status.

        Returns:
            Seconds to wait before retrying.
        """
        retry_after = response.headers.get("Retry-After", "1")
        try:
            return float(retry_after)
        except ValueError:
            logger.warning(
                "riot_retry_after_parse_error",
                extra={"retry_after": retry_after},
            )
            return 1.0
