"""Rank batch endpoint — fetches ranked data for multiple PUUIDs concurrently."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.core.logging import get_logger
from app.services.cache import get_redis
from app.services.riot_api_client import RiotApiClient

router = APIRouter(tags=["rank"])
logger = get_logger("league_api.rank")

_RANK_TTL_SECONDS = 3600  # 1 hour — rank changes slowly


def _cache_key(puuid: str) -> str:
    return f"rank:{puuid}"


async def _fetch_rank_cached(
    client: RiotApiClient,
    redis: Redis,
    puuid: str,
) -> dict[str, Any] | None:
    """Return cached rank for a PUUID, or fetch from Riot and cache it.

    Args:
        client: Shared RiotApiClient instance (already inside async context).
        redis: Redis client for cache read/write.
        puuid: Riot PUUID to look up.

    Returns:
        Rank dict with tier/rank/leaguePoints, or None on miss/error.
    """
    key = _cache_key(puuid)
    cached = await redis.get(key)
    if cached is not None:
        try:
            return json.loads(cached)  # type: ignore[return-value]
        except Exception:
            pass

    try:
        payload = await client.fetch_rank_by_puuid(puuid)
    except Exception:
        logger.exception("rank_batch_fetch_error", extra={"puuid": puuid})
        return None

    # Empty dict == unranked
    value = payload if payload else None
    await redis.set(key, json.dumps(value), ex=_RANK_TTL_SECONDS)
    return value


@router.get("/rank/batch")
async def get_rank_batch(
    puuids: str = Query(description="Comma-separated list of PUUIDs (max 10)"),
    redis: Redis = Depends(get_redis),
) -> dict[str, dict[str, Any] | None]:
    """Fetch ranked data for up to 10 PUUIDs concurrently.

    Caches each PUUID individually so a miss for one player does not
    invalidate others. Returns null for unranked or errored lookups.

    Args:
        puuids: Comma-separated PUUID string, max 10 entries.
        redis: Redis client injected by FastAPI.

    Returns:
        Mapping of puuid → rank payload (or null).
    """
    puuid_list = [p.strip() for p in puuids.split(",") if p.strip()][:10]
    if not puuid_list:
        return {}

    logger.info("rank_batch_start", extra={"count": len(puuid_list)})

    async with RiotApiClient() as client:
        results = await asyncio.gather(
            *[_fetch_rank_cached(client, redis, p) for p in puuid_list],
        )

    response: dict[str, dict[str, Any] | None] = {}
    for puuid, result in zip(puuid_list, results):
        response[puuid] = result if isinstance(result, dict) and result else None

    logger.info("rank_batch_done", extra={"count": len(puuid_list)})
    return response
