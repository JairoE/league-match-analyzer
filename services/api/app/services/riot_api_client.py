from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("league_api.services.riot_api_client")


@dataclass
class RiotRequestError(Exception):
    """Structured error from Riot API calls."""

    message: str
    status: int | None = None
    body: str | None = None


class RiotApiClient:
    """Async Riot API client without caching or rate limiting.

    Retrieves: Riot account, summoner, rank, and match payloads.
    Transforms: Minimal mapping, returns raw JSON payloads.
    Why: Keeps synchronous API handlers simple until async workers return.
    """

    ACCOUNT_BY_RIOT_ID_URL = "https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
    SUMMONER_BY_PUUID_URL = "https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/"
    RANK_BY_PUUID_URL = "https://na1.api.riotgames.com/lol/league/v4/entries/by-puuid/"
    MATCH_IDS_BY_PUUID_URL = "https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/"
    MATCH_DETAIL_URL = "https://americas.api.riotgames.com/lol/match/v5/matches/"

    def __init__(self) -> None:
        self._settings = get_settings()

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
        api_key = self._settings.riot_api_key
        # logger.info("riot_api_key", extra={"api_key": api_key})
        if not api_key or api_key == "replace-me":
            logger.info("riot_api_missing_key", extra={"url": url})
            raise RiotRequestError("missing_riot_api_key", status=401)
        headers = {"X-Riot-Token": api_key}
        timeout = httpx.Timeout(self._settings.riot_api_timeout_seconds)
        logger.info("riot_request_start", extra={"url": url, "bucket": bucket})
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.info(
                    "riot_request_failed",
                    extra={"url": url, "status": exc.response.status_code, "body": exc.response.text},
                )
                raise RiotRequestError(
                    "riot_api_failed",
                    status=exc.response.status_code,
                    body=exc.response.text,
                ) from exc
            except httpx.RequestError as exc:
                logger.info("riot_request_error", extra={"url": url, "detail": str(exc)})
                raise RiotRequestError("riot_api_failed", status=502, body=str(exc)) from exc
        logger.info("riot_request_ok", extra={"url": url, "status": response.status_code})
        return response.json()
