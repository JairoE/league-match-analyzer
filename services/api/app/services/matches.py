from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.match import Match
from app.models.riot_account_match import RiotAccountMatch


logger = get_logger("league_api.services.matches")


def parse_match_uuid(identifier: str) -> UUID | None:
    """Parse a match identifier into a UUID when possible.

    Args:
        identifier: Match ID supplied by the client.

    Returns:
        Parsed UUID if valid, otherwise None.
    """
    try:
        return UUID(identifier)
    except (TypeError, ValueError):
        return None


async def list_matches_for_riot_account(
    session: AsyncSession,
    riot_account_id: UUID,
) -> list[Match]:
    """List matches for a given riot account, ordered by most recently played first.

    Args:
        session: Async database session for queries.
        riot_account_id: UUID of the riot account.

    Returns:
        List of Match records associated with the riot account,
        sorted by game_start_timestamp DESC. Matches without timestamps appear last.
    """
    logger.info("list_matches_for_riot_account_start", extra={"riot_account_id": str(riot_account_id)})
    result = await session.execute(
        select(Match)
        .join(RiotAccountMatch, RiotAccountMatch.match_id == Match.id)
        .where(RiotAccountMatch.riot_account_id == riot_account_id)
        .order_by(Match.game_start_timestamp.desc().nulls_last()),
    )
    matches = list(result.scalars().all())
    logger.info(
        "list_matches_for_riot_account_done",
        extra={"riot_account_id": str(riot_account_id), "match_count": len(matches)},
    )
    return matches


async def get_match_by_identifier(session: AsyncSession, identifier: str) -> Match | None:
    """Fetch a match by UUID or Riot game ID.

    Args:
        session: Async database session for queries.
        identifier: Match UUID or Riot game ID.

    Returns:
        Match instance if found.
    """
    logger.info("get_match_by_identifier_start", extra={"identifier": identifier})
    parsed_uuid = parse_match_uuid(identifier)
    if parsed_uuid:
        result = await session.execute(select(Match).where(Match.id == parsed_uuid))
        match = result.scalar_one_or_none()
        if match:
            logger.info("get_match_by_identifier_uuid_found", extra={"match_id": str(match.id)})
            return match

    result = await session.execute(select(Match).where(Match.game_id == identifier))
    match = result.scalar_one_or_none()
    logger.info(
        "get_match_by_identifier_done",
        extra={"identifier": identifier, "found": bool(match)},
    )
    return match
