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

    Retrieves: Existing matches and user-match links in batch.
    Transforms: Creates missing matches and links to the user.
    Why: Keeps match list sync lightweight while persisting IDs.

    Args:
        session: Async database session for queries.
        user_id: UUID of the user to link.
        match_ids: Riot match IDs to upsert.

    Returns:
        Number of new user-match links created.
    """
    if not match_ids:
        return 0

    # Batch fetch existing matches
    result = await session.execute(
        select(Match).where(Match.game_id.in_(match_ids))
    )
    existing_matches = {m.game_id: m for m in result.scalars().all()}

    # Create missing match records
    for match_id in match_ids:
        if match_id not in existing_matches:
            match = Match(game_id=match_id)
            session.add(match)
            existing_matches[match_id] = match

    await session.flush()

    # Batch fetch existing user-match links
    all_match_uuids = [m.id for m in existing_matches.values()]
    result = await session.execute(
        select(UserMatch.match_id).where(
            UserMatch.user_id == user_id,
            UserMatch.match_id.in_(all_match_uuids),
        )
    )
    already_linked = {row[0] for row in result.fetchall()}

    # Create missing links
    created = 0
    for match in existing_matches.values():
        if match.id not in already_linked:
            session.add(UserMatch(user_id=user_id, match_id=match.id))
            created += 1

    await session.commit()
    logger.info(
        "match_sync_upsert_done",
        extra={"user_id": str(user_id), "match_count": len(match_ids), "linked": created},
    )
    return created
