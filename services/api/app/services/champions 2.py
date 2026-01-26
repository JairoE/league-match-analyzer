from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.champion import Champion


logger = get_logger("league_api.services.champions")


async def list_champions(session: AsyncSession) -> list[Champion]:
    """List all champions in the catalog.

    Args:
        session: Async database session for queries.

    Returns:
        List of Champion records ordered by name.
    """
    logger.info("list_champions_start")
    result = await session.execute(select(Champion).order_by(Champion.name))
    champions = list(result.scalars().all())
    logger.info("list_champions_done", extra={"count": len(champions)})
    return champions


async def get_champion_by_id(session: AsyncSession, champ_id: int) -> Champion | None:
    """Fetch a champion by numeric Riot ID.

    Args:
        session: Async database session for queries.
        champ_id: Numeric Riot champion identifier.

    Returns:
        Champion instance if found.
    """
    logger.info("get_champion_by_id_start", extra={"champ_id": champ_id})
    result = await session.execute(select(Champion).where(Champion.champ_id == champ_id))
    champion = result.scalar_one_or_none()
    logger.info(
        "get_champion_by_id_done",
        extra={"champ_id": champ_id, "found": bool(champion)},
    )
    return champion
