from fastapi import APIRouter, status

from app.core.logging import get_logger


router = APIRouter(tags=["matches"])
logger = get_logger("league_api.matches")


@router.get("/users/{user_id}/matches", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_user_matches(user_id: int) -> dict[str, str]:
    """Placeholder for user match listing.

    Args:
        user_id: User identifier from the route.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("list_user_matches_not_implemented", extra={"user_id": user_id})
    return {"detail": "Not implemented"}


@router.get("/matches/{match_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_match(match_id: int) -> dict[str, str]:
    """Placeholder for match detail retrieval.

    Args:
        match_id: Match identifier from the route.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("get_match_not_implemented", extra={"match_id": match_id})
    return {"detail": "Not implemented"}
