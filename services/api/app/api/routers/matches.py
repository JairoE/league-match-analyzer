from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.schemas.match import MatchListItem
from app.services.enqueue_match_details import enqueue_missing_detail_jobs
from app.services.matches import list_matches_for_riot_account
from app.services.riot_accounts import resolve_riot_account_identifier
from app.services.riot_sync import (
    backfill_match_details_inline,
    fetch_match_detail,
    fetch_match_list_for_riot_account,
)


router = APIRouter(tags=["matches"])
logger = get_logger("league_api.matches")


@router.get(
    "/riot-accounts/{riot_account_id}/matches",
    response_model=list[MatchListItem],
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def list_riot_account_matches(
    riot_account_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> list[MatchListItem]:
    """Return match list entries for a riot account.

    Args:
        riot_account_id: Riot account identifier from the route.
        background_tasks: FastAPI background task runner.
        session: Async database session for queries.

    Returns:
        List of match list items ordered by most recent first.
    """
    logger.info("list_riot_account_matches_start", extra={"riot_account_id": riot_account_id})
    match_ids = await fetch_match_list_for_riot_account(session, riot_account_id, 0, 20)
    if match_ids is None:
        logger.info("list_riot_account_matches_not_found", extra={"riot_account_id": riot_account_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found")
    logger.info(
        "list_riot_account_matches_synced",
        extra={"riot_account_id": riot_account_id, "match_count": len(match_ids)},
    )

    background_tasks.add_task(_enqueue_details_background, riot_account_id, match_ids)

    riot_account = await resolve_riot_account_identifier(session, riot_account_id)
    if not riot_account:
        logger.info("list_riot_account_matches_not_found_after_sync", extra={"riot_account_id": riot_account_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found")
    matches = await list_matches_for_riot_account(session, riot_account.id)

    # Inline backfill: fetch missing game_info directly from Riot API
    # so matches render immediately without needing the ARQ worker.
    missing_count = sum(1 for m in matches if not m.game_info)
    if missing_count:
        logger.info(
            "list_riot_account_matches_backfill_start",
            extra={"riot_account_id": riot_account_id, "missing": missing_count},
        )
        await backfill_match_details_inline(session, matches)

    logger.info("list_riot_account_matches_done", extra={"riot_account_id": riot_account_id, "count": len(matches)})
    return [MatchListItem.model_validate(match) for match in matches]


async def _enqueue_details_background(riot_account_id: str, match_ids: list[str]) -> None:
    """Fire-and-forget wrapper for ``enqueue_missing_detail_jobs``."""
    try:
        enqueued = await enqueue_missing_detail_jobs(match_ids)
        if enqueued:
            logger.info(
                "list_riot_account_matches_enqueued_details",
                extra={"riot_account_id": riot_account_id, "enqueued": enqueued},
            )
    except Exception:
        logger.exception(
            "list_riot_account_matches_enqueue_failed",
            extra={"riot_account_id": riot_account_id},
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
