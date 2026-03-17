"""Tests for resolve_average_rank — rank resolution from Redis + DB."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.resolve_match_rank import resolve_average_rank


def _make_game_info(puuids: list[str]) -> dict:
    """Build a minimal game_info with participant PUUIDs."""
    return {
        "info": {
            "participants": [{"puuid": p} for p in puuids],
        }
    }


def _make_redis(cache: dict[str, dict | None]) -> AsyncMock:
    """Create a mock Redis where cache maps puuid -> rank payload (or None for miss)."""
    redis = AsyncMock()

    async def _get(key: str) -> str | None:
        # key is "rank:{puuid}"
        puuid = key.split(":", 1)[1]
        if puuid in cache:
            return json.dumps(cache[puuid])
        return None

    redis.get = AsyncMock(side_effect=_get)
    return redis


def _make_session(db_tiers: dict[str, str]) -> AsyncMock:
    """Create a mock session that returns rank_tier rows for given puuids.

    Args:
        db_tiers: Mapping of puuid -> rank_tier for DB results.
    """
    session = AsyncMock()

    async def _execute(stmt):
        # Extract puuids from the WHERE clause — the mock returns matching tiers
        result = MagicMock()
        # We'll capture the puuids from the in_ clause
        rows = [(tier,) for tier in db_tiers.values()]
        result.all.return_value = rows
        return result

    session.execute = AsyncMock(side_effect=_execute)
    return session


@pytest.mark.asyncio
async def test_all_10_ranks_from_redis():
    """All 10 participants found in Redis — returns median tier."""
    puuids = [f"puuid_{i}" for i in range(10)]
    # 5 GOLD, 5 PLATINUM -> median_low of ordinals [4,4,4,4,4,5,5,5,5,5] = 4 = GOLD
    cache = {}
    for i, p in enumerate(puuids):
        tier = "GOLD" if i < 5 else "PLATINUM"
        cache[p] = {"tier": tier, "rank": "I", "leaguePoints": 50}

    redis = _make_redis(cache)
    session = AsyncMock()  # Should not be called since all from Redis

    result = await resolve_average_rank(_make_game_info(puuids), redis, session)
    assert result == "GOLD"


@pytest.mark.asyncio
async def test_mixed_redis_and_db():
    """Partial Redis + DB coverage meets threshold — returns median."""
    puuids = [f"puuid_{i}" for i in range(10)]
    # 2 from Redis: SILVER, GOLD
    cache = {
        "puuid_0": {"tier": "SILVER"},
        "puuid_1": {"tier": "GOLD"},
    }
    # 2 from DB: PLATINUM, DIAMOND — total 4 known, above threshold of 3
    db_tiers = {
        "puuid_2": "PLATINUM",
        "puuid_3": "DIAMOND",
    }

    redis = _make_redis(cache)
    session = AsyncMock()

    async def _execute(stmt):
        result = MagicMock()
        result.all.return_value = [(t,) for t in db_tiers.values()]
        return result

    session.execute = AsyncMock(side_effect=_execute)

    result = await resolve_average_rank(_make_game_info(puuids), redis, session)
    # Ordinals: SILVER=3, GOLD=4, PLATINUM=5, DIAMOND=7 -> sorted [3,4,5,7] -> median_low = 4
    assert result == "GOLD"


@pytest.mark.asyncio
async def test_fewer_than_threshold_returns_none():
    """< 3 known ranks — returns None."""
    puuids = [f"puuid_{i}" for i in range(10)]
    cache = {
        "puuid_0": {"tier": "GOLD"},
        "puuid_1": {"tier": "SILVER"},
    }

    redis = _make_redis(cache)
    session = AsyncMock()

    async def _execute(stmt):
        result = MagicMock()
        result.all.return_value = []
        return result

    session.execute = AsyncMock(side_effect=_execute)

    result = await resolve_average_rank(_make_game_info(puuids), redis, session)
    assert result is None


@pytest.mark.asyncio
async def test_unranked_players_excluded():
    """Unranked players (empty/null payloads) are excluded from the average."""
    puuids = [f"puuid_{i}" for i in range(10)]
    cache = {}
    for i, p in enumerate(puuids):
        if i < 3:
            cache[p] = {"tier": "GOLD"}
        elif i < 5:
            # Unranked: null value cached
            cache[p] = None
        elif i < 7:
            # Unranked: empty dict cached
            cache[p] = {}
        # else: Redis miss, not in DB either

    redis = _make_redis(cache)
    session = AsyncMock()

    async def _execute(stmt):
        result = MagicMock()
        result.all.return_value = []
        return result

    session.execute = AsyncMock(side_effect=_execute)

    result = await resolve_average_rank(_make_game_info(puuids), redis, session)
    # Only 3 known (all GOLD) — exactly at threshold
    assert result == "GOLD"


@pytest.mark.asyncio
async def test_no_participants_returns_none():
    """Empty game_info with no participants returns None."""
    redis = AsyncMock()
    session = AsyncMock()

    result = await resolve_average_rank({}, redis, session)
    assert result is None

    result = await resolve_average_rank({"info": {}}, redis, session)
    assert result is None

    result = await resolve_average_rank({"info": {"participants": []}}, redis, session)
    assert result is None
