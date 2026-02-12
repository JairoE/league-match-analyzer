from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.match import Match
from app.models.riot_account import RiotAccount
from app.models.riot_account_match import RiotAccountMatch

logger = get_logger("league_api.services.riot_accounts")


def parse_riot_account_uuid(identifier: str) -> UUID | None:
    """Parse a riot account identifier into a UUID when possible.

    Args:
        identifier: Riot account ID supplied in a route path or payload.

    Returns:
        Parsed UUID if valid, otherwise None.
    """
    try:
        return UUID(identifier)
    except (TypeError, ValueError):
        return None


async def get_riot_account_by_id(session: AsyncSession, riot_account_id: UUID) -> RiotAccount | None:
    """Fetch a riot account by UUID.

    Args:
        session: Async database session for queries.
        riot_account_id: UUID for the riot account record.

    Returns:
        RiotAccount instance if found.
    """
    logger.info("get_riot_account_by_id_start", extra={"riot_account_id": str(riot_account_id)})
    result = await session.execute(select(RiotAccount).where(RiotAccount.id == riot_account_id))
    account = result.scalar_one_or_none()
    logger.info("get_riot_account_by_id_done", extra={"riot_account_id": str(riot_account_id), "found": bool(account)})
    return account


async def get_riot_account_by_riot_id(session: AsyncSession, riot_id: str) -> RiotAccount | None:
    """Fetch a riot account by Riot ID.

    Args:
        session: Async database session for queries.
        riot_id: Riot ID in gameName#tagLine format.

    Returns:
        RiotAccount instance if found.
    """
    logger.info("get_riot_account_by_riot_id_start", extra={"riot_id": riot_id})
    result = await session.execute(select(RiotAccount).where(RiotAccount.riot_id == riot_id))
    account = result.scalar_one_or_none()
    logger.info("get_riot_account_by_riot_id_done", extra={"riot_id": riot_id, "found": bool(account)})
    return account


async def get_riot_account_by_puuid(session: AsyncSession, puuid: str) -> RiotAccount | None:
    """Fetch a riot account by PUUID.

    Args:
        session: Async database session for queries.
        puuid: Riot PUUID identifier.

    Returns:
        RiotAccount instance if found.
    """
    result = await session.execute(select(RiotAccount).where(RiotAccount.puuid == puuid))
    return result.scalar_one_or_none()


async def resolve_riot_account_identifier(
    session: AsyncSession,
    identifier: str,
) -> RiotAccount | None:
    """Resolve a riot account by UUID or Riot ID.

    Args:
        session: Async database session for queries.
        identifier: Riot account UUID or Riot ID string.

    Returns:
        RiotAccount instance if found.
    """
    logger.info("resolve_riot_account_identifier_start", extra={"identifier": identifier})
    parsed_uuid = parse_riot_account_uuid(identifier)
    if parsed_uuid:
        account = await get_riot_account_by_id(session, parsed_uuid)
        if account:
            return account

    # Try as riot_id
    account = await get_riot_account_by_riot_id(session, identifier)
    if account:
        return account

    logger.info("resolve_riot_account_identifier_not_found", extra={"identifier": identifier})
    return None


async def list_all_active_riot_accounts(
    session: AsyncSession,
    active_window_days: int = 7,
) -> list[RiotAccount]:
    """List riot accounts with match activity in the last N days.

    Retrieves: Riot accounts linked to matches within the active window.
    Transforms: De-duplicates via DISTINCT.
    Why: Limits scheduled ingestion to recently active accounts.

    Args:
        session: Async database session for queries.
        active_window_days: Number of days to consider an account active.

    Returns:
        List of active RiotAccount records.
    """
    now_ms = int(time.time() * 1000)
    window_ms = active_window_days * 24 * 60 * 60 * 1000
    cutoff_ms = now_ms - window_ms
    logger.info(
        "list_all_active_riot_accounts_start",
        extra={"active_window_days": active_window_days, "cutoff_ms": cutoff_ms},
    )
    result = await session.execute(
        select(RiotAccount)
        .join(RiotAccountMatch, RiotAccountMatch.riot_account_id == RiotAccount.id)
        .join(Match, Match.id == RiotAccountMatch.match_id)
        .where(Match.game_start_timestamp.is_not(None))
        .where(Match.game_start_timestamp >= cutoff_ms)
        .distinct()
    )
    accounts = list(result.scalars().all())
    logger.info("list_all_active_riot_accounts_done", extra={"account_count": len(accounts)})
    return accounts
