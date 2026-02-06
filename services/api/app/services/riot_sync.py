from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.match import Match
from app.models.user import User
from app.services.match_sync import upsert_matches_for_user
from app.services.matches import get_match_by_identifier
from app.services.riot_api_client import RiotApiClient
from app.services.riot_id_parser import parse_riot_id
from app.services.riot_user_upsert import upsert_user_from_riot
from app.services.users import resolve_user_identifier

logger = get_logger("league_api.services.riot_sync")


async def fetch_user_profile(
    session: AsyncSession,
    summoner_name: str,
    email: str | None,
) -> User:
    """Fetch Riot profile data and upsert a user record.

    Retrieves: Riot account and summoner payloads.
    Transforms: Normalizes Riot ID and maps payload into user fields.
    Why: Keeps synchronous auth flows aligned with stored user data.

    Args:
        session: Async database session for queries.
        summoner_name: Riot ID or summoner name from the client.
        email: Optional email address for the user.

    Returns:
        Stored user record after upsert.
    """
    logger.info("riot_sync_fetch_user_start", extra={"summoner_name": summoner_name})
    parsed = parse_riot_id(summoner_name)
    client = RiotApiClient()
    account_info = await client.fetch_account_by_riot_id(parsed.game_name, parsed.tag_line)
    summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
    user = await upsert_user_from_riot(
        session,
        parsed.canonical,
        account_info["puuid"],
        summoner_info,
        email=email,
    )
    logger.info("riot_sync_fetch_user_done", extra={"user_id": str(user.id)})
    return user


async def fetch_sign_in_user(
    session: AsyncSession,
    summoner_name: str,
    email: str | None,
) -> User | None:
    """Fetch Riot profile data and validate sign-in credentials.

    Retrieves: Existing user record and Riot profile payloads.
    Transforms: Updates stored user fields from the Riot payload.
    Why: Ensures sign-in returns the latest Riot profile snapshot.

    Args:
        session: Async database session for queries.
        summoner_name: Riot ID or summoner name from the client.
        email: Email address supplied for sign-in verification.

    Returns:
        Stored user record if credentials match, otherwise None.
    """
    logger.info("riot_sync_sign_in_start", extra={"summoner_name": summoner_name, "has_email": bool(email)})
    parsed = parse_riot_id(summoner_name)
    result = await session.execute(
        select(User).where(User.riot_id == parsed.canonical, User.email == email),
    )
    existing_user = result.scalar_one_or_none()
    if not existing_user:
        logger.info("riot_sync_sign_in_user_missing", extra={"summoner_name": summoner_name})
        return None
    client = RiotApiClient()
    account_info = await client.fetch_account_by_riot_id(parsed.game_name, parsed.tag_line)
    summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
    user = await upsert_user_from_riot(
        session,
        parsed.canonical,
        account_info["puuid"],
        summoner_info,
        email=existing_user.email,
    )
    logger.info("riot_sync_sign_in_done", extra={"user_id": str(user.id)})
    return user


async def fetch_rank_for_user(
    session: AsyncSession,
    user_identifier: str,
) -> dict[str, Any] | None:
    """Fetch ranked data for a stored user.

    Retrieves: Riot ranked entry object for the user's PUUID.
    Transforms: None, returns raw Riot payload object.
    Why: Keeps rank requests synchronous and aligned with Riot data.

    Args:
        session: Async database session for queries.
        user_identifier: User identifier from the route.

    Returns:
        Ranked payload object from Riot, or None if user missing.
    """
    logger.info("riot_sync_fetch_rank_start", extra={"user_identifier": user_identifier})
    user = await resolve_user_identifier(session, user_identifier)
    if not user:
        logger.info("riot_sync_fetch_rank_user_missing", extra={"user_identifier": user_identifier})
        return None
    client = RiotApiClient()
    payload = await client.fetch_rank_by_puuid(user.puuid)
    logger.info("riot_sync_fetch_rank_done", extra={"user_identifier": user_identifier})
    return payload


async def fetch_match_list_for_user(
    session: AsyncSession,
    user_identifier: str,
    start: int,
    count: int,
) -> list[str] | None:
    """Fetch match ids for a user and upsert match records.

    Retrieves: Riot match ID list for the user's PUUID.
    Transforms: Upserts match records and user-match links.
    Why: Keeps match list endpoints synchronous while persisting IDs.

    Args:
        session: Async database session for queries.
        user_identifier: User identifier from the route.
        start: Start offset for match list.
        count: Number of matches to retrieve.

    Returns:
        Match ID list fetched from Riot, or None if user missing.
    """
    logger.info(
        "riot_sync_fetch_match_list_start",
        extra={"user_identifier": user_identifier, "start": start, "count": count},
    )
    user = await resolve_user_identifier(session, user_identifier)
    if not user:
        logger.info("riot_sync_fetch_match_list_user_missing", extra={"user_identifier": user_identifier})
        return None
    client = RiotApiClient()
    match_ids = await client.fetch_match_ids_by_puuid(user.puuid, start=start, count=count)
    await upsert_matches_for_user(session, user.id, match_ids)
    logger.info(
        "riot_sync_fetch_match_list_done",
        extra={"user_identifier": user_identifier, "match_count": len(match_ids)},
    )
    return match_ids


async def fetch_match_detail(
    session: AsyncSession,
    match_identifier: str,
) -> dict[str, Any] | None:
    """Fetch match detail payload and persist it to Postgres.

    Retrieves: Riot match detail payload by match ID.
    Transforms: Persists payload into `Match.game_info` JSONB.
    Why: Matches Rails behavior while keeping response synchronous.

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
    riot_match_id = stored_match_id
    if "_" not in riot_match_id:
        riot_match_id = f"NA1_{riot_match_id}"
    client = RiotApiClient()
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
