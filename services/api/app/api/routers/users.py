from fastapi import APIRouter, status

from app.core.logging import get_logger


router = APIRouter(tags=["users"])
logger = get_logger("league_api.users")


@router.post("/fetch_user", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def fetch_user() -> dict[str, str]:
    """Placeholder for the fetch_user endpoint implementation.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("fetch_user_not_implemented")
    return {"detail": "Not implemented"}


@router.get("/users/{user_id}/fetch_rank", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def fetch_rank(user_id: int) -> dict[str, str]:
    """Placeholder for the fetch_rank endpoint implementation.

    Args:
        user_id: User identifier from the route.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("fetch_rank_not_implemented", extra={"user_id": user_id})
    return {"detail": "Not implemented"}
