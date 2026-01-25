from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.schemas.auth import UserFetchRequest
from app.schemas.user import UserResponse
from app.services.users import resolve_user_identifier


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
    user = await resolve_user_identifier(session, payload.summoner_name)
    if not user:
        logger.info("fetch_user_missing", extra={"summoner_name": payload.summoner_name})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info("fetch_user_success", extra={"user_id": str(user.id)})
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}/fetch_rank", status_code=status.HTTP_200_OK)
async def fetch_rank(
    user_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return cached ranked data for a user.

    Args:
        user_id: User identifier from the route.
        session: Async database session for queries.

    Returns:
        Ranked payload stored for the user if available.
    """
    logger.info("fetch_rank_start", extra={"user_id": user_id})
    user = await resolve_user_identifier(session, user_id)
    if not user:
        logger.info("fetch_rank_user_missing", extra={"user_id": user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info("fetch_rank_empty", extra={"user_id": user_id})
    return []
