from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.match import Match
from app.models.riot_account_match import RiotAccountMatch

logger = get_logger("league_api.services.match_sync")


async def upsert_matches_for_riot_account(
    session: AsyncSession,
    riot_account_id: UUID,
    match_ids: list[str],
) -> int:
    """Upsert match records and link them to a riot account.

    Uses INSERT ... ON CONFLICT DO NOTHING for both Match and
    RiotAccountMatch to avoid race conditions under concurrency.

    Args:
        session: Async database session for queries.
        riot_account_id: UUID of the riot account to link.
        match_ids: Riot match IDs to upsert.

    Returns:
        Number of new riot-account-match links created.
    """
    if not match_ids:
        return 0

    # Atomic upsert: insert all match IDs, skip duplicates on game_id unique constraint
    match_rows = [{"id": uuid4(), "game_id": mid} for mid in match_ids]
    stmt = pg_insert(Match).values(match_rows).on_conflict_do_nothing(index_elements=["game_id"])
    await session.execute(stmt)

    # Fetch all match UUIDs (existing + just-inserted) in one query
    result = await session.execute(
        select(Match.id, Match.game_id).where(Match.game_id.in_(match_ids))
    )
    match_uuid_map = {row.game_id: row.id for row in result.fetchall()}

    # Atomic link upsert: insert links, skip duplicates on (riot_account_id, match_id) constraint
    link_rows = [
        {
            "id": uuid4(),
            "riot_account_id": riot_account_id,
            "match_id": match_uuid_map[mid],
        }
        for mid in match_ids
        if mid in match_uuid_map
    ]
    if link_rows:
        link_stmt = (
            pg_insert(RiotAccountMatch)
            .values(link_rows)
            .on_conflict_do_nothing(
                constraint="uq_riot_account_match",
            )
        )
        result = await session.execute(link_stmt)
        created = result.rowcount if result.rowcount and result.rowcount > 0 else 0
    else:
        created = 0

    await session.commit()
    logger.info(
        "match_sync_upsert_done",
        extra={
            "riot_account_id": str(riot_account_id),
            "match_count": len(match_ids),
            "linked": created,
        },
    )
    return created
