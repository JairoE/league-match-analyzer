from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_session
from app.schemas.match import LaneStats, MatchListItem, PaginatedMatchList, PaginationMeta
from app.services.enqueue_match_timelines import enqueue_missing_timeline_jobs
from app.services.match_sync import upsert_matches_for_riot_account
from app.services.matches import list_matches_for_riot_account
from app.services.rate_limiter import get_rate_limiter
from app.services.riot_accounts import resolve_riot_account_identifier
from app.services.riot_api_client import RiotApiClient, RiotRequestError
from app.services.riot_sync import (
    backfill_match_details_by_game_ids,
    backfill_match_details_inline,
    fetch_match_detail,
    fetch_timeline_stats,
)

router = APIRouter(tags=["matches"])
logger = get_logger("league_api.matches")


def _mark_rate_limited_or_reraise(exc: RiotRequestError) -> tuple[bool, str]:
    """On 429 return (True, 'rate_limited'); otherwise re-raise."""
    if exc.status == 429:
        return (True, "rate_limited")
    raise


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
    after: int = Query(
        default=0,
        ge=0,
        description="Load-more offset; when >0 backend fetches fresh match IDs from Riot.",
    ),
    refresh: bool = Query(
        default=False,
        description="When true (and page 1), fetch fresh match IDs from Riot.",
    ),
    session: AsyncSession = Depends(get_session),
) -> PaginatedMatchList:
    """Return paginated match list for a riot account.

    Match list is from DB unless refresh=true (page 1) or after > 0 (see more);
    then fresh match IDs are fetched from Riot, upserted, and backfilled.

    Args:
        riot_account_id: Riot account identifier from the route.
        background_tasks: FastAPI background task runner.
        page: Page number (1-based).
        limit: Items per page (max 100).
        after: Load-more offset; when >0 fetches fresh match IDs from Riot.
        refresh: When true and page 1, fetch fresh match IDs from Riot.
        session: Async database session for queries.

    Returns:
        Paginated match list with metadata.
    """
    logger.info(
        "list_riot_account_matches_start",
        extra={
            "riot_account_id": riot_account_id,
            "page": page,
            "after": after,
            "refresh": refresh,
        },
    )

    riot_account = await resolve_riot_account_identifier(session, riot_account_id)
    if not riot_account:
        logger.info(
            "list_riot_account_matches_not_found",
            extra={"riot_account_id": riot_account_id},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found"
        )

    sync_skipped = False
    sync_skip_reason: str | None = None

    # Fetch fresh match IDs only on refresh (page 1) or see more (after > 0).
    want_fresh_match_ids = (page == 1 and after == 0 and refresh) or (after > 0)
    if want_fresh_match_ids and riot_account.puuid:
        try:
            async with RiotApiClient() as client:
                start = after if after > 0 else 0
                new_ids = await client.fetch_match_ids_by_puuid(
                    riot_account.puuid, start=start, count=limit
                )
            if new_ids:
                await upsert_matches_for_riot_account(session, riot_account.id, new_ids)
                await backfill_match_details_by_game_ids(
                    session, new_ids, max_fetch=limit
                )
                background_tasks.add_task(enqueue_missing_timeline_jobs, new_ids)
        except RiotRequestError as exc:
            sync_skipped, sync_skip_reason = _mark_rate_limited_or_reraise(exc)
            logger.warning(
                "list_riot_account_matches_rate_limited",
                extra={"riot_account_id": riot_account_id, "error_message": exc.message},
            )
        except Exception:
            logger.exception(
                "list_riot_account_matches_fresh_ids_error",
                extra={"riot_account_id": riot_account_id, "after": after},
            )

    offset_override = after if after > 0 else None
    matches, total = await list_matches_for_riot_account(
        session, riot_account.id, page, limit, offset_override=offset_override
    )

    if sync_skipped and total == 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="riot_api_max_retries_exceeded",
        )

    if not sync_skipped:
        missing_count = sum(1 for m in matches if not m.game_info)
        if missing_count:
            logger.info(
                "list_riot_account_matches_backfill",
                extra={
                    "riot_account_id": riot_account_id,
                    "missing": missing_count,
                    "page": page,
                },
            )
            await backfill_match_details_inline(session, matches, max_fetch=limit)

    logger.info(
        "list_riot_account_matches_done",
        extra={"riot_account_id": riot_account_id, "count": len(matches)},
    )
    # Mark DB-only responses as stale when API is in global backoff so frontend can show warning
    if not sync_skipped and await get_rate_limiter().is_globally_backing_off():
        sync_skipped = True
        sync_skip_reason = "rate_limited"
        logger.info(
            "list_matches_stale_global_backoff",
            extra={"riot_account_id": riot_account_id},
        )
    return PaginatedMatchList(
        data=[MatchListItem.model_validate(match) for match in matches],
        meta=PaginationMeta.build(
            page=page,
            limit=limit,
            total=total,
            stale=sync_skipped,
            stale_reason=sync_skip_reason,
        ),
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
    participant_id: int = Query(
        ge=1, le=10, description="1-based participantId of the tracked player"
    ),
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
    logger.info(
        "get_timeline_stats_start", extra={"match_id": match_id, "participant_id": participant_id}
    )
    stats = await fetch_timeline_stats(session, match_id, participant_id)
    if stats is None:
        logger.info("get_timeline_stats_unavailable", extra={"match_id": match_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timeline not available")
    logger.info("get_timeline_stats_done", extra={"match_id": match_id})
    return LaneStats(**stats)
