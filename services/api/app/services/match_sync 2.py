from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.match import Match
from app.models.user_match import UserMatch

logger = get_logger("league_api.services.match_sync")


async def upsert_matches_for_user(
    session: AsyncSession,
    user_id: UUID,
    match_ids: list[str],
) -> int:
    """Upsert match records and link them to a user.

    Retrieves: Existing matches and user-match links.
    Transforms: Creates missing matches and links to the user.
    Why: Keeps match list sync lightweight while persisting IDs.

    Args:
        session: Async database session for queries.
        user_id: UUID of the user to link.
        match_ids: Riot match IDs to upsert.

    Returns:
        Number of new user-match links created.
    """
    created = 0
    for match_id in match_ids:
        match = await _get_or_create_match(session, match_id)
        linked = await _ensure_user_match(session, user_id, match.id)
        created += int(linked)
    await session.commit()
    logger.info(
        "match_sync_upsert_done",
        extra={"user_id": str(user_id), "match_count": len(match_ids), "linked": created},
    )
    return created


async def _get_or_create_match(session: AsyncSession, match_id: str) -> Match:
    result = await session.execute(select(Match).where(Match.game_id == match_id))
    match = result.scalar_one_or_none()
    if match:
        return match
    match = Match(game_id=match_id)
    session.add(match)
    await session.flush()
    logger.info("match_sync_created", extra={"match_id": str(match.id), "game_id": match_id})
    return match


async def _ensure_user_match(session: AsyncSession, user_id: UUID, match_id: UUID) -> bool:
    result = await session.execute(
        select(UserMatch).where(UserMatch.user_id == user_id, UserMatch.match_id == match_id),
    )
    existing = result.scalar_one_or_none()
    if existing:
        return False
    link = UserMatch(user_id=user_id, match_id=match_id)
    session.add(link)
    return True
