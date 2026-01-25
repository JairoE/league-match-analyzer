from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.schemas.champion import ChampionPublic
from app.services.champions import get_champion_by_id, list_champions


router = APIRouter(prefix="/champions", tags=["champions"])
logger = get_logger("league_api.champions")


@router.get(
    "",
    response_model=list[ChampionPublic],
    status_code=status.HTTP_200_OK,
)
async def list_champions_endpoint(
    session: AsyncSession = Depends(get_session),
) -> list[ChampionPublic]:
    """Return all champion metadata.

    Returns:
        List of champion payloads for the catalog.
    """
    logger.info("list_champions_start")
    champions = await list_champions(session)
    logger.info("list_champions_done", extra={"count": len(champions)})
    return [ChampionPublic.model_validate(champion) for champion in champions]


@router.get(
    "/{champ_id}",
    response_model=ChampionPublic,
    status_code=status.HTTP_200_OK,
)
async def get_champion(
    champ_id: int,
    session: AsyncSession = Depends(get_session),
) -> ChampionPublic:
    """Return champion metadata by ID.

    Args:
        champ_id: Champion identifier from the route.
        session: Async database session for queries.

    Returns:
        Champion payload for the requested ID.
    """
    logger.info("get_champion_start", extra={"champ_id": champ_id})
    champion = await get_champion_by_id(session, champ_id)
    if not champion:
        logger.info("get_champion_missing", extra={"champ_id": champ_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Champion not found")
    logger.info("get_champion_success", extra={"champ_id": champ_id})
    return ChampionPublic.model_validate(champion)
