from __future__ import annotations

from typing import Any

from contextlib import asynccontextmanager
import httpx

from app.core.logging import get_logger

logger = get_logger("league_api.services.ddragon")


class DdragonClient:
    """Data Dragon client for champion metadata fetches.

    Retrieves: Riot Data Dragon versions and champion data payloads.
    Transforms: Maps raw payloads into a normalized champion catalog.
    Why: Keeps champion data seeded without Rails controller side effects.
    """

    VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
    CDN_BASE_URL = "https://ddragon.leagueoflegends.com/cdn"

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    async def fetch_latest_version(self) -> str:
        """Fetch the latest Data Dragon version string.

        Returns:
            Latest available Data Dragon version.
        """
        logger.info("ddragon_versions_fetch_start", extra={"url": self.VERSIONS_URL})
        async with self._get_client() as client:
            response = await client.get(self.VERSIONS_URL)
            response.raise_for_status()
            versions = response.json()
        version = versions[0]
        logger.info("ddragon_versions_fetch_done", extra={"latest": version})
        return version

    async def fetch_champion_catalog(self) -> list[dict[str, Any]]:
        """Fetch and normalize champion metadata.

        Retrieves: Data Dragon champion payload for the latest version.
        Transforms: Normalizes champion fields for persistence.
        Why: Keeps champion catalog in sync with Riot metadata.

        Returns:
            List of normalized champion dictionaries.
        """
        version = await self.fetch_latest_version()
        url = f"{self.CDN_BASE_URL}/{version}/data/en_US/champion.json"
        logger.info("ddragon_champions_fetch_start", extra={"url": url, "version": version})
        async with self._get_client() as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        data = payload.get("data", {})
        champions: list[dict[str, Any]] = []
        for champion in data.values():
            image_file = champion.get("image", {}).get("full", "")
            champions.append(
                {
                    "champ_id": int(champion["key"]),
                    "name": champion["name"],
                    "nickname": champion["title"],
                    "image_url": f"{self.CDN_BASE_URL}/{version}/img/champion/{image_file}",
                }
            )
        logger.info("ddragon_champions_fetch_done", extra={"count": len(champions)})
        return champions

    @asynccontextmanager
    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client:
            yield self._http_client
            return
        async with httpx.AsyncClient(timeout=20.0) as client:
            yield client
