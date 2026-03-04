"""Redis-cached live game lookup via Riot Spectator v5 API."""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.services.cache import get_redis
from app.services.riot_api_client import RiotApiClient

logger = get_logger("league_api.services.live_game")

CACHE_TTL_SECONDS = 30
CACHE_KEY_PREFIX = "live_game:"
_NOT_IN_GAME_SENTINEL = "null"


async def get_live_game(puuid: str) -> dict[str, Any] | None:
    """Fetch live game data for a summoner, with Redis caching.

    Checks Redis first (30s TTL). On cache miss, queries Riot Spectator v5.
    Stores a "null" sentinel for not-in-game to avoid redundant API calls
    within the cache window.

    Args:
        puuid: Riot PUUID of the summoner.

    Returns:
        Spectator payload dict if in game, None otherwise.
    """
    redis = get_redis()
    cache_key = f"{CACHE_KEY_PREFIX}{puuid}"

    cached = await redis.get(cache_key)
    if cached is not None:
        if cached == _NOT_IN_GAME_SENTINEL:
            logger.info("live_game_cache_hit_not_in_game", extra={"puuid": puuid})
            return None
        logger.info("live_game_cache_hit", extra={"puuid": puuid})
        return json.loads(cached)

    logger.info("live_game_cache_miss", extra={"puuid": puuid})
    async with RiotApiClient() as client:
        payload = await client.fetch_active_game_by_puuid(puuid)

    if payload is None:
        await redis.set(cache_key, _NOT_IN_GAME_SENTINEL, ex=CACHE_TTL_SECONDS)
        return None

    await redis.set(cache_key, json.dumps(payload), ex=CACHE_TTL_SECONDS)
    return payload
