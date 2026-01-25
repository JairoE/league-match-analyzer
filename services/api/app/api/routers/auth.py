from fastapi import APIRouter, status

from app.core.logging import get_logger


router = APIRouter(prefix="/users", tags=["auth"])
logger = get_logger("league_api.auth")


@router.post("/sign_up", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def sign_up() -> dict[str, str]:
    """Placeholder for the sign-up endpoint implementation.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("sign_up_not_implemented")
    return {"detail": "Not implemented"}


@router.post("/sign_in", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def sign_in() -> dict[str, str]:
    """Placeholder for the sign-in endpoint implementation.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("sign_in_not_implemented")
    return {"detail": "Not implemented"}
