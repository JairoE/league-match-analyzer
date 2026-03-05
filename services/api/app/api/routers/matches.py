from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.api.routers.match_timeline_enqueue import enqueue_timelines_background
from app.db.session import get_session
from app.schemas.match import LaneStats, MatchListItem, PaginatedMatchList, PaginationMeta
from app.services.matches import list_matches_for_riot_account
from app.services.riot_accounts import resolve_riot_account_identifier
from app.services.riot_sync import (
    backfill_match_details_by_game_ids,
    backfill_match_details_inline,
    fetch_match_detail,
    fetch_match_list_for_riot_account,
    fetch_timeline_stats,
)


router = APIRouter(tags=["matches"])
logger = get_logger("league_api.matches")


@router.get(
    "/riot-accounts/{riot_account_id}/matches",
    response_model=PaginatedMatchList,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def list_riot_account_matches(
    riot_account_id: str,
    background_tasks: BackgroundTasks,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_session),
) -> PaginatedMatchList:
    """Return paginated match list entries for a riot account.

    Args:
        riot_account_id: Riot account identifier from the route.
        background_tasks: FastAPI background task runner.
        page: Page number (1-based).
        limit: Items per page (max 100).
        session: Async database session for queries.

    Returns:
        Paginated match list with metadata.
    """
    logger.info("list_riot_account_matches_start", extra={"riot_account_id": riot_account_id})

    # Only sync with Riot API on page 1; page 2+ just queries DB
    if page == 1:
        match_ids = await fetch_match_list_for_riot_account(session, riot_account_id, 0, 20)
        if match_ids is None:
            logger.info("list_riot_account_matches_not_found", extra={"riot_account_id": riot_account_id})
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found")
        logger.info(
            "list_riot_account_matches_synced",
            extra={"riot_account_id": riot_account_id, "match_count": len(match_ids)},
        )

        # Pre-query backfill: populate game_info + game_start_timestamp for newly
        # upserted matches so they sort correctly on the first request.
        await backfill_match_details_by_game_ids(session, match_ids)

        # Pre-fetch timelines in background for instant UX on row expand.
        background_tasks.add_task(
            enqueue_timelines_background,
            logger=logger,
            match_ids=match_ids,
            context={"riot_account_id": riot_account_id},
            success_event="list_riot_account_matches_enqueued_timelines",
            failure_event="list_riot_account_matches_timeline_enqueue_failed",
        )

    riot_account = await resolve_riot_account_identifier(session, riot_account_id)
    if not riot_account:
        logger.info("list_riot_account_matches_not_found_after_sync", extra={"riot_account_id": riot_account_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found")
    matches, total = await list_matches_for_riot_account(session, riot_account.id, page, limit)

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
    return PaginatedMatchList(
        data=[MatchListItem.model_validate(match) for match in matches],
        meta=PaginationMeta.build(page=page, limit=limit, total=total),
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


@router.get(
    "/matches/{match_id}/timeline-stats",
    response_model=LaneStats,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def get_match_timeline_stats(
    match_id: str,
    participant_id: int = Query(description="1-based participantId of the tracked player"),
    session: AsyncSession = Depends(get_session),
) -> LaneStats:
    """Return pre-computed laning stats for one participant from the match timeline.

    Fetches the Riot timeline (cached indefinitely in Redis), parses CS/gold
    diffs vs the lane opponent at 10 and 15 minutes, and returns a compact
    LaneStats payload — no 1MB+ timeline JSON is ever shipped to the client.

    Args:
        match_id: Match UUID or Riot match ID.
        participant_id: 1-based participantId of the player to analyse.
        session: Async database session for queries.

    Returns:
        LaneStats with available diff fields and opponent info.
    """
    logger.info("get_timeline_stats_start", extra={"match_id": match_id, "participant_id": participant_id})
    stats = await fetch_timeline_stats(session, match_id, participant_id)
    if stats is None:
        logger.info("get_timeline_stats_unavailable", extra={"match_id": match_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timeline not available")
    logger.info("get_timeline_stats_done", extra={"match_id": match_id})
    return LaneStats(**stats)
