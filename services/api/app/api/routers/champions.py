from fastapi import APIRouter, status

from app.core.logging import get_logger


router = APIRouter(prefix="/champions", tags=["champions"])
logger = get_logger("league_api.champions")


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_champions() -> dict[str, str]:
    """Placeholder for champion listing.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("list_champions_not_implemented")
    return {"detail": "Not implemented"}


@router.get("/{champ_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_champion(champ_id: int) -> dict[str, str]:
    """Placeholder for champion detail retrieval.

    Args:
        champ_id: Champion identifier from the route.

    Returns:
        A placeholder response while Phase 3 is pending.
    """
    logger.info("get_champion_not_implemented", extra={"champ_id": champ_id})
    return {"detail": "Not implemented"}
