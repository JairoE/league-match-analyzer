from __future__ import annotations

import asyncio

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.champion import Champion
from app.services.ddragon_client import DdragonClient

logger = get_logger("league_api.services.champion_seed")


async def ensure_champions_loaded(session: AsyncSession, force_reset: bool) -> int:
    """Ensure champions are present, optionally resetting the table first.

    Retrieves: Existing champion presence to avoid redundant seeding.
    Transforms: Clears and rebuilds the champion catalog when forced.
    Why: Mirrors Rails auto-seed behavior without controller side effects.

    Args:
        session: Async database session for queries.
        force_reset: Whether to clear the table before seeding.

    Returns:
        Count of champions inserted.
    """
    if not force_reset:
        result = await session.execute(select(Champion.id).limit(1))
        if result.scalar_one_or_none():
            logger.info("champion_seed_skipped", extra={"reason": "already_seeded"})
            return 0

    if force_reset:
        await session.execute(delete(Champion))
        logger.info("champion_seed_cleared", extra={"reason": "force_reset"})

    client = DdragonClient()
    champions = await client.fetch_champion_catalog()
    records = [
        Champion(
            champ_id=champion["champ_id"],
            name=champion["name"],
            nickname=champion["nickname"],
            image_url=champion["image_url"],
        )
        for champion in champions
    ]
    session.add_all(records)
    await session.commit()
    logger.info("champion_seed_completed", extra={"inserted": len(records)})
    return len(records)


async def reset_champion_by_id(session: AsyncSession, champ_id: int) -> bool:
    """Reset a single champion row using Data Dragon metadata.

    Retrieves: Latest Data Dragon champion payload.
    Transforms: Deletes and recreates the requested champion row.
    Why: Enables targeted refreshes without full table rebuilds.

    Args:
        session: Async database session for queries.
        champ_id: Numeric Riot champion identifier.

    Returns:
        True if the champion was found and reset; otherwise False.
    """
    client = DdragonClient()
    champions = await client.fetch_champion_catalog()
    match = next((champ for champ in champions if champ["champ_id"] == champ_id), None)
    if not match:
        logger.info("champion_reset_missing", extra={"champ_id": champ_id})
        return False

    await session.execute(delete(Champion).where(Champion.champ_id == champ_id))
    session.add(
        Champion(
            champ_id=match["champ_id"],
            name=match["name"],
            nickname=match["nickname"],
            image_url=match["image_url"],
        )
    )
    await session.commit()
    logger.info("champion_reset_completed", extra={"champ_id": champ_id})
    return True


def schedule_champion_seed_job(
    reason: str,
    force_reset: bool = False,
    champ_id: int | None = None,
) -> asyncio.Task[None]:
    """Schedule a champion seed/reset job in the background.

    Retrieves: None.
    Transforms: Spawns an async task to seed or reset champion data.
    Why: Keeps HTTP handlers fast and avoids blocking startup.

    Args:
        reason: Context for logging (startup, reset_route, etc.).
        force_reset: Whether to clear the table before seeding.
        champ_id: Optional single champion id to reset.

    Returns:
        Asyncio task running the job.
    """
    logger.info(
        "champion_seed_scheduled",
        extra={"reason": reason, "force_reset": force_reset, "champ_id": champ_id},
    )
    return asyncio.create_task(_run_champion_seed_job(reason, force_reset, champ_id))


async def _run_champion_seed_job(reason: str, force_reset: bool, champ_id: int | None) -> None:
    """Run a seed/reset job with its own session.

    Retrieves: None.
    Transforms: Writes champion metadata to the database.
    Why: Isolates background jobs from request sessions.
    """
    logger.info(
        "champion_seed_job_start",
        extra={"reason": reason, "force_reset": force_reset, "champ_id": champ_id},
    )
    try:
        async with AsyncSessionLocal() as session:
            if champ_id is None:
                inserted = await ensure_champions_loaded(session, force_reset=force_reset)
                logger.info(
                    "champion_seed_job_done",
                    extra={
                        "reason": reason,
                        "force_reset": force_reset,
                        "inserted": inserted,
                    },
                )
                return
            reset = await reset_champion_by_id(session, champ_id)
            logger.info(
                "champion_seed_job_done",
                extra={"reason": reason, "champ_id": champ_id, "reset": reset},
            )
    except Exception:
        logger.exception(
            "champion_seed_job_failed",
            extra={"reason": reason, "force_reset": force_reset, "champ_id": champ_id},
        )
