from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.schemas.auth import UserFetchRequest
from app.schemas.user import UserResponse
from app.services.riot_id_parser import parse_riot_id
from app.services.riot_sync import fetch_rank_for_user, fetch_user_profile


router = APIRouter(tags=["users"])
logger = get_logger("league_api.users")


@router.post(
    "/fetch_user",
    response_model=UserResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def fetch_user(
    payload: UserFetchRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Return user data for a fetch request.

    Returns:
        User profile payload matching the stored record.
    """
    logger.info("fetch_user_start", extra={"summoner_name": payload.summoner_name})
    try:
        parsed_riot_id = parse_riot_id(payload.summoner_name)
    except ValueError:
        logger.info("fetch_user_invalid_riot_id", extra={"summoner_name": payload.summoner_name})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_riot_id")
    user = await fetch_user_profile(session, parsed_riot_id.canonical, None)
    logger.info("fetch_user_success", extra={"user_id": str(user.id)})
    return user


@router.get("/users/{user_id}/fetch_rank", status_code=status.HTTP_200_OK)
async def fetch_rank(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return cached ranked data for a user.

    Args:
        user_id: User identifier from the route.
        session: Async database session for queries.

    Returns:
        Ranked payload object stored for the user if available.
    """
    logger.info("fetch_rank_start", extra={"user_id": user_id})
    result = await fetch_rank_for_user(session, user_id)
    if result is None:
        logger.info("fetch_rank_user_missing", extra={"user_id": user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info("fetch_rank_success", extra={"user_id": user_id})
    return result
