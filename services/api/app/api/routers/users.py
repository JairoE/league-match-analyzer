from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.services.riot_sync import fetch_rank_for_riot_account


router = APIRouter(tags=["users"])
logger = get_logger("league_api.users")


@router.get("/riot-accounts/{riot_account_id}/fetch_rank", status_code=status.HTTP_200_OK)
async def fetch_rank(
    riot_account_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return ranked data for a riot account.

    Args:
        riot_account_id: Riot account identifier from the route.
        session: Async database session for queries.

    Returns:
        Ranked payload object from Riot if available.
    """
    logger.info("fetch_rank_start", extra={"riot_account_id": riot_account_id})
    result = await fetch_rank_for_riot_account(session, riot_account_id)
    if result is None:
        logger.info("fetch_rank_account_missing", extra={"riot_account_id": riot_account_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found")
    logger.info("fetch_rank_success", extra={"riot_account_id": riot_account_id})
    return result
