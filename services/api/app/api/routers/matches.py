from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.schemas.match import MatchListItem
from app.services.enqueue_match_details import enqueue_missing_detail_jobs
from app.services.matches import list_matches_for_user
from app.services.riot_sync import fetch_match_detail, fetch_match_list_for_user
from app.services.users import resolve_user_identifier


router = APIRouter(tags=["matches"])
logger = get_logger("league_api.matches")


@router.get(
    "/users/{user_id}/matches",
    response_model=list[MatchListItem],
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def list_user_matches(
    user_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> list[MatchListItem]:
    """Return match list entries for the user.

    Args:
        user_id: User identifier from the route.
        background_tasks: FastAPI background task runner.
        session: Async database session for queries.

    Returns:
        List of match list items in stored association order.
    """
    logger.info("list_user_matches_start", extra={"user_id": user_id})
    match_ids = await fetch_match_list_for_user(session, user_id, 0, 20)
    if match_ids is None:
        logger.info("list_user_matches_user_missing", extra={"user_id": user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    logger.info("list_user_matches_synced", extra={"user_id": user_id, "match_count": len(match_ids)})

    background_tasks.add_task(_enqueue_details_background, user_id, match_ids)

    user = await resolve_user_identifier(session, user_id)
    if not user:
        logger.info("list_user_matches_user_missing_after_job", extra={"user_id": user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    matches = await list_matches_for_user(session, user.id)
    logger.info("list_user_matches_done", extra={"user_id": user_id, "count": len(matches)})
    return [MatchListItem.model_validate(match) for match in matches]


async def _enqueue_details_background(user_id: str, match_ids: list[str]) -> None:
    """Fire-and-forget wrapper for ``enqueue_missing_detail_jobs``."""
    try:
        enqueued = await enqueue_missing_detail_jobs(match_ids)
        if enqueued:
            logger.info(
                "list_user_matches_enqueued_details",
                extra={"user_id": user_id, "enqueued": enqueued},
            )
    except Exception:
        logger.exception(
            "list_user_matches_enqueue_failed",
            extra={"user_id": user_id},
        )


@router.get("/matches/{match_id}", status_code=status.HTTP_200_OK)
async def get_match(
    match_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return full match payload by identifier.

    Args:
        match_id: Match identifier from the route.
        session: Async database session for queries.

    Returns:
        Raw Riot match payload if stored.
    """
    logger.info("get_match_start", extra={"match_id": match_id})
    result = await fetch_match_detail(session, match_id)
    if result is None:
        logger.info("get_match_missing", extra={"match_id": match_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    logger.info("get_match_success", extra={"match_id": match_id})
    return result
