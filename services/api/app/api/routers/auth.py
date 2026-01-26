from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.schemas.auth import UserSignInRequest, UserSignUpRequest
from app.schemas.user import UserResponse
from app.services.riot_id_parser import parse_riot_id
from app.services.riot_sync import fetch_sign_in_user, fetch_user_profile


router = APIRouter(prefix="/users", tags=["auth"])
logger = get_logger("league_api.auth")


@router.post(
    "/sign_up",
    response_model=UserResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def sign_up(
    payload: UserSignUpRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Return user data for a sign-up request.

    Returns:
        User profile payload matching the stored record.
    """
    logger.info("sign_up_start", extra={"summoner_name": payload.summoner_name})
    try:
        parsed_riot_id = parse_riot_id(payload.summoner_name)
    except ValueError:
        logger.info("sign_up_invalid_riot_id", extra={"summoner_name": payload.summoner_name})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_riot_id")
    logger.info(
        "sign_up_parsed_riot_id",
        extra={"canonical": parsed_riot_id.canonical, "summoner_name": parsed_riot_id.game_name},
    )
    user = await fetch_user_profile(session, parsed_riot_id.canonical, payload.email)
    logger.info("sign_up_success", extra={"user_id": str(user.id)})
    return user


@router.post(
    "/sign_in",
    response_model=UserResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def sign_in(
    payload: UserSignInRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Return user data for a sign-in request.

    Returns:
        User profile payload matching the stored record.
    """
    logger.info("sign_in_start", extra={"summoner_name": payload.summoner_name})
    try:
        parsed_riot_id = parse_riot_id(payload.summoner_name)
    except ValueError:
        logger.info("sign_in_invalid_riot_id", extra={"summoner_name": payload.summoner_name})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_riot_id")
    logger.info(
        "sign_in_parsed_riot_id",
        extra={"canonical": parsed_riot_id.canonical, "summoner_name": parsed_riot_id.game_name},
    )
    user = await fetch_sign_in_user(session, parsed_riot_id.canonical, payload.email)
    if not user:
        logger.info("sign_in_user_missing", extra={"summoner_name": payload.summoner_name})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info("sign_in_success", extra={"user_id": str(user.id)})
    return user
