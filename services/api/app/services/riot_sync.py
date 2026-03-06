from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.match import Match
from app.models.riot_account import RiotAccount
from app.models.user import User
from app.models.user_riot_account import UserRiotAccount
from app.services.match_sync import upsert_matches_for_riot_account
from app.services.matches import get_match_by_identifier
from app.services.riot_account_upsert import upsert_riot_account, upsert_user_and_riot_account
from app.services.riot_api_client import RiotApiClient
from app.services.riot_id_parser import parse_riot_id
from app.services.riot_match_id import normalize_match_id

logger = get_logger("league_api.services.riot_sync")


async def fetch_user_profile(
    session: AsyncSession,
    summoner_name: str,
    email: str,
) -> tuple[User, RiotAccount]:
    """Fetch Riot profile data and upsert user + riot account + link.

    Used for sign-up flows. Creates the 3-way relationship:
    user ↔ user_riot_account ↔ riot_account.

    Args:
        session: Async database session for queries.
        summoner_name: Riot ID or summoner name from the client.
        email: Email address for the user.

    Returns:
        Tuple of (User, RiotAccount) after upsert.
    """
    logger.info("riot_sync_fetch_user_start", extra={"summoner_name": summoner_name})
    parsed = parse_riot_id(summoner_name)
    async with RiotApiClient() as client:
        account_info = await client.fetch_account_by_riot_id(parsed.game_name, parsed.tag_line)
        summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
    user, riot_account = await upsert_user_and_riot_account(
        session,
        email=email,
        riot_id=parsed.canonical,
        puuid=account_info["puuid"],
        summoner_info=summoner_info,
    )
    logger.info(
        "riot_sync_fetch_user_done",
        extra={"user_id": str(user.id), "riot_account_id": str(riot_account.id)},
    )
    return user, riot_account


async def fetch_sign_in_user(
    session: AsyncSession,
    summoner_name: str,
    email: str,
) -> tuple[User, RiotAccount] | None:
    """Fetch Riot profile data and validate sign-in credentials.

    Verifies the user exists by email, then checks that the riot account
    is linked to them. Updates riot account data from Riot API.

    Args:
        session: Async database session for queries.
        summoner_name: Riot ID or summoner name from the client.
        email: Email address supplied for sign-in verification.

    Returns:
        Tuple of (User, RiotAccount) if credentials match, otherwise None.
    """
    logger.info(
        "riot_sync_sign_in_start", extra={"summoner_name": summoner_name, "has_email": bool(email)}
    )
    parsed = parse_riot_id(summoner_name)

    # Find user by email
    result = await session.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()
    if not existing_user:
        logger.info("riot_sync_sign_in_user_missing", extra={"email": email})
        return None

    # Check that this user has a linked riot account with this riot_id
    result = await session.execute(
        select(RiotAccount)
        .join(UserRiotAccount, UserRiotAccount.riot_account_id == RiotAccount.id)
        .where(
            UserRiotAccount.user_id == existing_user.id,
            RiotAccount.riot_id == parsed.canonical,
        )
    )
    existing_account = result.scalar_one_or_none()
    if not existing_account:
        logger.info(
            "riot_sync_sign_in_riot_account_not_linked",
            extra={"email": email, "riot_id": parsed.canonical},
        )
        return None

    # Refresh riot account data from Riot API
    async with RiotApiClient() as client:
        account_info = await client.fetch_account_by_riot_id(parsed.game_name, parsed.tag_line)
        summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])

    riot_account = await upsert_riot_account(
        session,
        parsed.canonical,
        account_info["puuid"],
        summoner_info,
    )
    await session.commit()
    await session.refresh(riot_account)

    logger.info(
        "riot_sync_sign_in_done",
        extra={"user_id": str(existing_user.id), "riot_account_id": str(riot_account.id)},
    )
    return existing_user, riot_account


async def fetch_rank_for_riot_account(
    session: AsyncSession,
    riot_account_id: str,
) -> dict[str, Any] | None:
    """Fetch ranked data for a riot account.

    Args:
        session: Async database session for queries.
        riot_account_id: Riot account UUID string.

    Returns:
        Ranked payload object from Riot, or None if account missing.
    """
    logger.info("riot_sync_fetch_rank_start", extra={"riot_account_id": riot_account_id})
    from app.services.riot_accounts import resolve_riot_account_identifier

    riot_account = await resolve_riot_account_identifier(session, riot_account_id)
    if not riot_account:
        logger.info(
            "riot_sync_fetch_rank_account_missing", extra={"riot_account_id": riot_account_id}
        )
        return None
    async with RiotApiClient() as client:
        payload = await client.fetch_rank_by_puuid(riot_account.puuid)
    logger.info("riot_sync_fetch_rank_done", extra={"riot_account_id": riot_account_id})
    return payload


async def fetch_match_list_for_riot_account(
    session: AsyncSession,
    riot_account_id: str,
    start: int,
    count: int,
) -> list[str] | None:
    """Fetch match ids for a riot account and upsert match records.

    Args:
        session: Async database session for queries.
        riot_account_id: Riot account UUID string.
        start: Start offset for match list.
        count: Number of matches to retrieve.

    Returns:
        Match ID list fetched from Riot, or None if account missing.
    """
    logger.info(
        "riot_sync_fetch_match_list_start",
        extra={"riot_account_id": riot_account_id, "start": start, "count": count},
    )
    from app.services.riot_accounts import resolve_riot_account_identifier

    riot_account = await resolve_riot_account_identifier(session, riot_account_id)
    if not riot_account:
        logger.info(
            "riot_sync_fetch_match_list_account_missing", extra={"riot_account_id": riot_account_id}
        )
        return None
    async with RiotApiClient() as client:
        match_ids = await client.fetch_match_ids_by_puuid(
            riot_account.puuid, start=start, count=count
        )
    await upsert_matches_for_riot_account(session, riot_account.id, match_ids)
    logger.info(
        "riot_sync_fetch_match_list_done",
        extra={"riot_account_id": riot_account_id, "match_count": len(match_ids)},
    )
    return match_ids


async def _backfill_single_match(
    client: RiotApiClient,
    match: Match,
) -> bool:
    """Fetch and persist game_info for a single match.

    Args:
        client: Active Riot API client.
        match: Match record to populate.

    Returns:
        True if the match was successfully backfilled.
    """
    try:
        riot_match_id, _ = normalize_match_id(match.game_id)
        payload = await client.fetch_match_by_id(riot_match_id)
        timestamp = None
        if payload and "info" in payload and "gameStartTimestamp" in payload["info"]:
            timestamp = payload["info"]["gameStartTimestamp"]
        match.game_info = payload
        match.game_start_timestamp = timestamp
        return True
    except Exception:
        logger.exception(
            "backfill_single_match_error",
            extra={"game_id": match.game_id},
        )
        return False


async def _commit_backfilled(
    session: AsyncSession,
    fetched: int,
) -> None:
    """Commit matches that were backfilled."""
    if fetched:
        await session.commit()


async def backfill_match_details_inline(
    session: AsyncSession,
    matches: list[Match],
    max_fetch: int = 20,
) -> int:
    """Fetch missing game_info for matches inline (no ARQ worker needed).

    Iterates over matches that lack game_info and fetches details from
    the Riot API directly, persisting each payload to the DB.

    Args:
        session: Async database session for queries.
        matches: List of Match records to check and backfill.
        max_fetch: Maximum number of detail fetches per call.

    Returns:
        Number of matches that were backfilled.
    """
    missing = [m for m in matches if not m.game_info]
    if not missing:
        return 0

    logger.info(
        "backfill_match_details_inline_start",
        extra={"missing": len(missing), "max_fetch": max_fetch},
    )

    to_process = missing[:max_fetch]
    fetched = 0
    async with RiotApiClient() as client:
        for match in to_process:
            if await _backfill_single_match(client, match):
                fetched += 1

    await _commit_backfilled(session, fetched)

    logger.info(
        "backfill_match_details_inline_done",
        extra={"fetched": fetched, "total_missing": len(missing)},
    )
    return fetched


async def backfill_match_details_by_game_ids(
    session: AsyncSession,
    game_ids: list[str],
    max_fetch: int = 20,
) -> int:
    """Fetch missing game_info for matches identified by Riot game IDs.

    Unlike ``backfill_match_details_inline`` (which operates on already-loaded
    Match objects), this queries the DB for Match records whose ``game_id`` is in
    ``game_ids`` and whose ``game_info`` is NULL, then fetches details from Riot.
    Call this *before* the ordering query so new matches get timestamps and sort
    correctly on the first request.

    Args:
        session: Async database session.
        game_ids: Riot match ID strings (e.g. ``["NA1_12345", ...]``).
        max_fetch: Maximum number of Riot API calls to make.

    Returns:
        Number of matches backfilled.
    """
    if not game_ids:
        return 0

    from sqlalchemy import String, cast, or_

    result = await session.execute(
        select(Match).where(
            Match.game_id.in_(game_ids),
            or_(
                Match.game_info.is_(None),
                cast(Match.game_info, String) == "null",
            ),
        )
    )
    missing = list(result.scalars().all())

    if not missing:
        logger.info(
            "backfill_by_game_ids_none_needed",
            extra={"checked": len(game_ids)},
        )
        return 0

    logger.info(
        "backfill_by_game_ids_start",
        extra={"missing": len(missing), "max_fetch": max_fetch},
    )

    to_process = missing[:max_fetch]
    fetched = 0
    async with RiotApiClient() as client:
        for match in to_process:
            if await _backfill_single_match(client, match):
                fetched += 1

    await _commit_backfilled(session, fetched)

    logger.info(
        "backfill_by_game_ids_done",
        extra={"fetched": fetched, "total_missing": len(missing)},
    )
    return fetched


def _get_cs(frame: dict) -> int:
    """Extract total CS (minions + neutrals) from a timeline participant frame."""
    return frame.get("minionsKilled", 0) + frame.get("jungleMinionsKilled", 0)


def _find_lane_opponent(
    participants: list[dict],
    current_participant_id: int,
    current_team_id: int,
    current_position: str,
) -> dict | None:
    """Return the participant on the opposing team with the closest lane position."""
    for p in participants:
        if p.get("teamId") == current_team_id:
            continue
        if p.get("individualPosition") == current_position:
            return p
    return None


async def fetch_timeline_stats(
    session: AsyncSession,
    match_identifier: str,
    target_participant_id: int,
) -> dict | None:
    """Fetch and parse laning stats from the Riot timeline.

    Caches the raw timeline in Redis only (key: timeline:{match_id}, no TTL).
    Returns pre-computed LaneStats dict so the client never sees the 1MB payload.

    Args:
        session: Async database session (used to resolve match game_id).
        match_identifier: Match UUID or Riot match ID.
        target_participant_id: 1-based participantId of the tracked player.

    Returns:
        LaneStats dict, or None if timeline unavailable.
    """
    from app.services.cache import get_redis
    from app.services.riot_match_id import normalize_match_id

    # Resolve the canonical Riot match ID
    match = await get_match_by_identifier(session, match_identifier)
    stored_id = match.game_id if match else match_identifier
    riot_match_id, _ = normalize_match_id(stored_id)

    redis = get_redis()
    cache_key = f"timeline:{riot_match_id}"

    raw = await redis.get(cache_key)
    if raw is None:
        async with RiotApiClient() as client:
            try:
                timeline = await client.fetch_match_timeline(riot_match_id)
            except Exception:
                logger.exception("fetch_timeline_stats_error", extra={"match_id": riot_match_id})
                return None
        await redis.set(cache_key, json.dumps(timeline))
        logger.info("fetch_timeline_cached", extra={"match_id": riot_match_id})
    else:
        timeline = json.loads(raw)

    timeline_info: dict = timeline.get("info") or {}
    frames: list[dict] = timeline_info.get("frames") or []
    if not frames:
        return None

    # frameInterval is in ms; default 60 000 ms = 1 frame/min.
    # Guard against malformed/zero values so we never divide by zero.
    raw_frame_interval = timeline_info.get("frameInterval")
    try:
        frame_interval_ms = int(raw_frame_interval or 60_000)
    except (TypeError, ValueError):
        frame_interval_ms = 60_000
    frame_interval_ms = max(1, frame_interval_ms)
    idx_10 = round(10 * 60_000 / frame_interval_ms)
    idx_15 = round(15 * 60_000 / frame_interval_ms)

    def participant_frame(frame: dict, pid: int) -> dict:
        return (frame.get("participantFrames") or {}).get(str(pid)) or {}

    current_frame_10 = (
        participant_frame(frames[idx_10], target_participant_id) if len(frames) > idx_10 else {}
    )
    current_frame_15 = (
        participant_frame(frames[idx_15], target_participant_id) if len(frames) > idx_15 else {}
    )

    # Participant metadata (individualPosition, teamId, championName) lives in the match
    # detail response, not the timeline — timeline participants only carry participantId + puuid.
    p_info_list: list[dict] = []
    if match and match.game_info:
        p_info_list = (match.game_info.get("info") or {}).get("participants") or []
    current_meta = next(
        (p for p in p_info_list if p.get("participantId") == target_participant_id), {}
    )
    opponent_meta = None
    current_pos = current_meta.get("individualPosition") or ""
    current_team = current_meta.get("teamId") or 0
    if current_pos and current_team:
        opponent_meta = _find_lane_opponent(
            p_info_list, target_participant_id, current_team, current_pos
        )

    result: dict = {}

    if current_frame_10:
        my_cs_10 = _get_cs(current_frame_10)
        my_gold_10 = current_frame_10.get("totalGold", 0)
        if opponent_meta:
            opp_id = opponent_meta.get("participantId")
            opp_frame_10 = participant_frame(frames[idx_10], opp_id) if opp_id else {}
            result["cs_diff_at_10"] = my_cs_10 - _get_cs(opp_frame_10)
            result["gold_diff_at_10"] = my_gold_10 - opp_frame_10.get("totalGold", 0)

    if current_frame_15:
        my_cs_15 = _get_cs(current_frame_15)
        my_gold_15 = current_frame_15.get("totalGold", 0)
        if opponent_meta:
            opp_id = opponent_meta.get("participantId")
            opp_frame_15 = participant_frame(frames[idx_15], opp_id) if opp_id else {}
            result["cs_diff_at_15"] = my_cs_15 - _get_cs(opp_frame_15)
            result["gold_diff_at_15"] = my_gold_15 - opp_frame_15.get("totalGold", 0)

    if opponent_meta:
        result["lane_opponent_name"] = (
            opponent_meta.get("riotIdGameName")
            or opponent_meta.get("summonerName")
            or opponent_meta.get("puuid", "")[:8]
        )
        result["lane_opponent_champion"] = opponent_meta.get("championName")

    return result or None


async def fetch_match_detail(
    session: AsyncSession,
    match_identifier: str,
) -> dict[str, Any] | None:
    """Fetch match detail payload and persist it to Postgres.

    Args:
        session: Async database session for queries.
        match_identifier: Match UUID or Riot match ID.

    Returns:
        Riot match payload, or None if no match record exists and fetch fails.
    """
    logger.info("riot_sync_fetch_match_detail_start", extra={"match_identifier": match_identifier})
    match = await get_match_by_identifier(session, match_identifier)
    if match and match.game_info:
        # Lazy backfill: extract timestamp from cached JSONB when column is NULL
        if match.game_start_timestamp is None:
            ts = match.game_info.get("info", {}).get("gameStartTimestamp")
            if ts is not None:
                match.game_start_timestamp = ts
                await session.commit()
                await session.refresh(match)
                logger.info(
                    "riot_sync_backfill_timestamp",
                    extra={"match_id": str(match.id), "timestamp": ts},
                )
        logger.info("riot_sync_fetch_match_detail_cached", extra={"match_id": str(match.id)})
        return match.game_info

    stored_match_id = match.game_id if match else match_identifier
    riot_match_id, was_normalized = normalize_match_id(stored_match_id)
    if was_normalized:
        logger.info(
            "riot_sync_normalized_match_id",
            extra={"match_id": stored_match_id, "riot_match_id": riot_match_id},
        )
    async with RiotApiClient() as client:
        payload = await client.fetch_match_by_id(riot_match_id)

    if not match:
        match = Match(game_id=stored_match_id)
        session.add(match)
    match.game_info = payload
    # Extract gameStartTimestamp for indexed ordering
    if payload and "info" in payload and "gameStartTimestamp" in payload["info"]:
        match.game_start_timestamp = payload["info"]["gameStartTimestamp"]
        logger.info(
            "riot_sync_extracted_timestamp",
            extra={"match_id": str(match.id), "timestamp": match.game_start_timestamp},
        )
    await session.commit()
    await session.refresh(match)

    logger.info(
        "riot_sync_fetch_match_detail_done",
        extra={"match_identifier": match_identifier, "match_id": str(match.id)},
    )
    return payload
