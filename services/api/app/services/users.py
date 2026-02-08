from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.match import Match
from app.models.user import User
from app.models.user_match import UserMatch
from app.services.riot_id_parser import ParsedRiotId, parse_riot_id


logger = get_logger("league_api.services.users")


def parse_user_uuid(identifier: str) -> UUID | None:
    """Parse a user identifier into a UUID when possible.

    Args:
        identifier: User ID supplied in a route path or payload.

    Returns:
        Parsed UUID if valid, otherwise None.
    """
    try:
        return UUID(identifier)
    except (TypeError, ValueError):
        return None


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    """Fetch a user by UUID.

    Args:
        session: Async database session for queries.
        user_id: UUID for the user record.

    Returns:
        User instance if found.
    """
    logger.info("get_user_by_id_start", extra={"user_id": str(user_id)})
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    logger.info("get_user_by_id_done", extra={"user_id": str(user_id), "found": bool(user)})
    return user


async def get_user_by_riot_id(session: AsyncSession, riot_id: str) -> User | None:
    """Fetch a user by Riot ID.

    Args:
        session: Async database session for queries.
        riot_id: Riot ID in gameName#tagLine format.

    Returns:
        User instance if found.
    """
    logger.info("get_user_by_riot_id_start", extra={"riot_id": riot_id})
    result = await session.execute(select(User).where(User.riot_id == riot_id))
    user = result.scalar_one_or_none()
    logger.info("get_user_by_riot_id_done", extra={"riot_id": riot_id, "found": bool(user)})
    return user


async def get_user_by_summoner_name(session: AsyncSession, summoner_name: str) -> User | None:
    """Fetch a user by summoner name (case-insensitive).

    Args:
        session: Async database session for queries.
        summoner_name: Summoner name value to match.

    Returns:
        User instance if found.
    """
    logger.info("get_user_by_summoner_name_start", extra={"summoner_name": summoner_name})
    result = await session.execute(
        select(User).where(func.lower(User.summoner_name) == summoner_name.lower()),
    )
    user = result.scalar_one_or_none()
    logger.info(
        "get_user_by_summoner_name_done",
        extra={"summoner_name": summoner_name, "found": bool(user)},
    )
    return user


async def resolve_user_identifier(
    session: AsyncSession,
    identifier: str,
    parsed_riot_id: ParsedRiotId | None = None,
) -> User | None:
    """Resolve a user by UUID, Riot ID, or summoner name.

    Args:
        session: Async database session for queries.
        identifier: User identifier provided by the client.
        parsed_riot_id: Parsed Riot ID pieces when already normalized.

    Returns:
        User instance if found.
    """
    logger.info("resolve_user_identifier_start", extra={"identifier": identifier})
    parsed_uuid = parse_user_uuid(identifier)
    if parsed_uuid:
        user = await get_user_by_id(session, parsed_uuid)
        if user:
            return user
    if parsed_riot_id is None:
        try:
            parsed_riot_id = parse_riot_id(identifier)
        except ValueError:
            logger.info("resolve_user_identifier_invalid_riot_id", extra={"identifier": identifier})
            return None

    logger.info(
        "resolve_user_identifier_parsed",
        extra={
            "game_name": parsed_riot_id.game_name,
            "tag_line": parsed_riot_id.tag_line,
            "canonical": parsed_riot_id.canonical,
        },
    )
    user = await get_user_by_riot_id(session, parsed_riot_id.canonical)
    if user:
        return user

    logger.info(
        "resolve_user_identifier_fallback_summoner",
        extra={"summoner_name": parsed_riot_id.game_name},
    )
    return await get_user_by_summoner_name(session, parsed_riot_id.game_name)


async def list_all_users(session: AsyncSession) -> list[User]:
    """List all users in the database.

    Retrieves: All user records for background sync jobs.
    Transforms: Returns list of User objects.
    Why: Enables batch processing of match ingestion for all users.

    Args:
        session: Async database session for queries.

    Returns:
        List of all User records.
    """
    logger.info("list_all_users_start")
    result = await session.execute(select(User))
    users = list(result.scalars().all())
    logger.info("list_all_users_done", extra={"user_count": len(users)})
    return users


async def list_all_active_users(
    session: AsyncSession,
    active_window_days: int = 7,
) -> list[User]:
    """List users with match activity in the last N days.

    Retrieves: Users linked to matches within the active window.
    Transforms: De-duplicates user records via DISTINCT.
    Why: Limits scheduled ingestion to recently active users.

    Args:
        session: Async database session for queries.
        active_window_days: Number of days to consider a user active.

    Returns:
        List of active User records.
    """
    now_ms = int(time.time() * 1000)
    window_ms = active_window_days * 24 * 60 * 60 * 1000
    cutoff_ms = now_ms - window_ms
    logger.info(
        "list_all_active_users_start",
        extra={"active_window_days": active_window_days, "cutoff_ms": cutoff_ms},
    )
    result = await session.execute(
        select(User)
        .join(UserMatch, UserMatch.user_id == User.id)
        .join(Match, Match.id == UserMatch.match_id)
        .where(Match.game_start_timestamp.is_not(None))
        .where(Match.game_start_timestamp >= cutoff_ms)
        .distinct()
    )
    users = list(result.scalars().all())
    logger.info("list_all_active_users_done", extra={"user_count": len(users)})
    return users
