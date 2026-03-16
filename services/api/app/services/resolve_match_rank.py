"""Resolve the average rank tier for a match from Redis cache and DB.

Used by the extraction job to populate the average_rank feature in state vectors.
"""

from __future__ import annotations

import json
from statistics import median_low

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.riot_account import RiotAccount
from app.services.win_prob_features import RANK_ORDER

logger = get_logger("league_api.services.resolve_match_rank")

# Minimum number of known ranks to produce a result
_MIN_KNOWN_RANKS = 3

# Lookup table: tier name -> ordinal (skip index 0 which is empty string)
_TIER_TO_ORDINAL: dict[str, int] = {
    tier: i for i, tier in enumerate(RANK_ORDER) if tier
}


def _tier_to_ordinal(tier: str | None) -> int | None:
    """Convert a tier string to its ordinal, or None if unknown."""
    if not tier:
        return None
    return _TIER_TO_ORDINAL.get(tier.strip().upper())


def _ordinal_to_tier(ordinal: int) -> str:
    """Convert an ordinal back to the tier string."""
    return RANK_ORDER[ordinal]


async def resolve_average_rank(
    game_info: dict,
    redis: Redis,
    session: AsyncSession,
) -> str | None:
    """Compute the average (median) rank tier for a match's participants.

    Checks Redis cache first, then falls back to riot_account.rank_tier in the DB.
    Returns None if fewer than _MIN_KNOWN_RANKS participants have known ranks.

    Args:
        game_info: The match game_info JSONB payload (contains info.participants).
        redis: Redis client for rank cache lookups.
        session: Async DB session for riot_account queries.

    Returns:
        Tier string (e.g. "GOLD") representing the median rank, or None.
    """
    participants = (game_info.get("info") or {}).get("participants") or []
    puuids = [p.get("puuid") for p in participants if p.get("puuid")]
    if not puuids:
        return None

    known_ordinals: list[int] = []
    redis_misses: list[str] = []

    # Step 1: batch-check Redis
    for puuid in puuids:
        raw = await redis.get(f"rank:{puuid}")
        if raw is not None:
            try:
                data = json.loads(raw)
            except Exception:
                redis_misses.append(puuid)
                continue
            if data and isinstance(data, dict):
                ordinal = _tier_to_ordinal(data.get("tier"))
                if ordinal is not None:
                    known_ordinals.append(ordinal)
        else:
            redis_misses.append(puuid)

    # Step 2: batch-query DB for misses
    if redis_misses:
        result = await session.execute(
            select(RiotAccount.rank_tier).where(
                RiotAccount.puuid.in_(redis_misses),
                RiotAccount.rank_tier.is_not(None),
            )
        )
        for (tier,) in result.all():
            ordinal = _tier_to_ordinal(tier)
            if ordinal is not None:
                known_ordinals.append(ordinal)

    if len(known_ordinals) < _MIN_KNOWN_RANKS:
        logger.info(
            "resolve_average_rank_insufficient",
            extra={"known": len(known_ordinals), "total": len(puuids)},
        )
        return None

    median_ordinal = median_low(known_ordinals)
    tier = _ordinal_to_tier(median_ordinal)
    logger.info(
        "resolve_average_rank_done",
        extra={"known": len(known_ordinals), "median_tier": tier},
    )
    return tier
