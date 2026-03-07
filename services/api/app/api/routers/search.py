from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import map_riot_status
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.riot_account import RiotAccount
from app.schemas.match import MatchListItem, PaginatedMatchList, PaginationMeta
from app.schemas.user import RiotAccountResponse
from app.services.enqueue_match_timelines import enqueue_missing_timeline_jobs
from app.services.match_sync import upsert_matches_for_riot_account
from app.services.matches import list_matches_for_riot_account
from app.services.riot_account_upsert import find_or_create_riot_account
from app.services.riot_accounts import get_riot_account_by_riot_id
from app.services.riot_api_client import RiotApiClient, RiotRequestError
from app.services.riot_id_parser import ParsedRiotId, parse_riot_id
from app.services.riot_sync import backfill_match_details_by_game_ids, backfill_match_details_inline

router = APIRouter(prefix="/search", tags=["search"])
logger = get_logger("league_api.search")


async def _first_sync_account_and_matches(
    session: AsyncSession,
    parsed: ParsedRiotId,
    riot_id: str,
    limit: int,
    background_tasks: BackgroundTasks,
) -> tuple[RiotAccount | None, bool, str | None]:
    """Fetch account + match IDs from Riot and upsert. Returns (account, sync_skipped, reason)."""
    sync_skipped = False
    sync_skip_reason: str | None = None
    account_info: dict[str, Any] = {}
    summoner_info: dict[str, Any] = {}

    try:
        async with RiotApiClient() as client:
            account_info = await client.fetch_account_by_riot_id(
                parsed.game_name, parsed.tag_line
            )
            summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
            match_ids = await client.fetch_match_ids_by_puuid(
                account_info["puuid"], start=0, count=limit
            )
    except RiotRequestError as exc:
        if exc.status == 429:
            sync_skipped = True
            sync_skip_reason = "rate_limited"
            logger.warning(
                "search_matches_rate_limited",
                extra={"riot_id": riot_id, "error_message": exc.message},
            )
            riot_account = await get_riot_account_by_riot_id(session, parsed.canonical)
            if not riot_account:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="riot_api_max_retries_exceeded",
                )
            return (riot_account, sync_skipped, sync_skip_reason)
        logger.warning(
            "search_matches_riot_request_error",
            extra={
                "riot_id": riot_id,
                "status": exc.status,
                "error_message": exc.message,
            },
        )
        raise HTTPException(
            status_code=map_riot_status(exc.status),
            detail=exc.message,
        )
    except Exception:
        logger.exception("search_matches_riot_api_error", extra={"riot_id": riot_id})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch account from Riot API",
        )

    riot_account = await find_or_create_riot_account(
        session,
        riot_id=parsed.canonical,
        puuid=account_info["puuid"],
        summoner_info=summoner_info,
    )
    await session.commit()
    await session.refresh(riot_account)
    await upsert_matches_for_riot_account(session, riot_account.id, match_ids)
    if match_ids:
        await backfill_match_details_by_game_ids(
            session, match_ids, max_fetch=limit
        )
        background_tasks.add_task(enqueue_missing_timeline_jobs, match_ids)
    return (riot_account, sync_skipped, sync_skip_reason)


async def _refresh_matches_if_requested(
    session: AsyncSession,
    riot_account: RiotAccount,
    riot_id: str,
    page: int,
    after: int,
    limit: int,
    refresh: bool,
    background_tasks: BackgroundTasks,
) -> tuple[bool, str | None]:
    """Fetch fresh match IDs when refresh/see-more; on 429 set stale. Returns (skipped, reason)."""
    sync_skipped = False
    sync_skip_reason: str | None = None
    want_fresh = (page == 1 and after == 0 and refresh) or (after > 0)
    if not want_fresh or not riot_account.puuid:
        return (sync_skipped, sync_skip_reason)
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
        if exc.status == 429:
            sync_skipped = True
            sync_skip_reason = "rate_limited"
            logger.warning(
                "search_matches_fresh_ids_rate_limited",
                extra={"riot_id": riot_id, "after": after},
            )
        else:
            logger.warning(
                "search_matches_fresh_ids_error",
                extra={
                    "riot_id": riot_id,
                    "status": exc.status,
                    "error_message": exc.message,
                },
            )
    except Exception:
        logger.exception(
            "search_matches_fresh_ids_error",
            extra={"riot_id": riot_id, "after": after},
        )
    return (sync_skipped, sync_skip_reason)


@router.get(
    "/{riot_id}/matches",
    response_model=PaginatedMatchList,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def search_riot_account_matches(
    riot_id: str,
    background_tasks: BackgroundTasks,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    after: int = Query(
        default=0,
        ge=0,
        description="Load-more offset: number of matches already loaded by the client.",
    ),
    refresh: bool = Query(
        default=False,
        description="When true (and page 1), fetch fresh match IDs from Riot.",
    ),
    session: AsyncSession = Depends(get_session),
) -> PaginatedMatchList:
    """Search for a riot account by Riot ID and return their matches.

    Account is resolved from DB when present; Riot is only called for account
    on first sync. Match IDs are fetched from Riot on first sync, refresh, or
    see more (after > 0).

    Args:
        riot_id: Riot ID in gameName#tagLine format (URL-encoded # as %23).
        background_tasks: FastAPI background task runner.
        page: Page number (1-based).
        limit: Items per page (max 100).
        after: Load-more offset; when >0 backend fetches fresh match IDs from Riot.
        refresh: When true and page 1, fetch fresh match IDs from Riot.
        session: Async database session for queries.

    Returns:
        Paginated match list for the searched account.
    """
    logger.info(
        "search_matches_start",
        extra={"riot_id": riot_id, "page": page, "after": after, "refresh": refresh},
    )

    try:
        parsed = parse_riot_id(riot_id)
    except ValueError:
        logger.info("search_matches_invalid_riot_id", extra={"riot_id": riot_id})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_riot_id")

    riot_account = await get_riot_account_by_riot_id(session, parsed.canonical)

    if riot_account is None and (page != 1 or after != 0):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found"
        )

    if riot_account is None:
        riot_account, sync_skipped, sync_skip_reason = await _first_sync_account_and_matches(
            session, parsed, riot_id, limit, background_tasks
        )
    else:
        sync_skipped, sync_skip_reason = await _refresh_matches_if_requested(
            session, riot_account, riot_id, page, after, limit, refresh, background_tasks
        )

    if riot_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found"
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
                "search_matches_backfill",
                extra={"riot_id": riot_id, "missing": missing_count, "page": page},
            )
            await backfill_match_details_inline(session, matches, max_fetch=limit)

    logger.info(
        "search_matches_done",
        extra={"riot_id": riot_id, "riot_account_id": str(riot_account.id), "count": len(matches)},
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


@router.get(
    "/{riot_id}/account",
    response_model=RiotAccountResponse,
    response_model_by_alias=True,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def search_riot_account(
    riot_id: str,
    session: AsyncSession = Depends(get_session),
) -> RiotAccountResponse:
    """Return riot account by Riot ID. Uses DB when present; calls Riot only if not found.

    Args:
        riot_id: Riot ID in gameName#tagLine format.
        session: Async database session for queries.

    Returns:
        Riot account data.
    """
    logger.info("search_account_start", extra={"riot_id": riot_id})

    try:
        parsed = parse_riot_id(riot_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_riot_id")

    riot_account = await get_riot_account_by_riot_id(session, parsed.canonical)
    if riot_account is not None:
        logger.info("search_account_from_db", extra={"riot_account_id": str(riot_account.id)})
        return RiotAccountResponse.model_validate(riot_account)

    try:
        async with RiotApiClient() as client:
            account_info = await client.fetch_account_by_riot_id(
                parsed.game_name, parsed.tag_line
            )
            summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
    except RiotRequestError as exc:
        logger.warning(
            "search_account_riot_request_error",
            extra={"riot_id": riot_id, "status": exc.status, "error_message": exc.message},
        )
        raise HTTPException(
            status_code=map_riot_status(exc.status),
            detail=exc.message,
        )
    except Exception:
        logger.exception("search_account_riot_api_error", extra={"riot_id": riot_id})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch account from Riot API",
        )

    riot_account = await find_or_create_riot_account(
        session,
        riot_id=parsed.canonical,
        puuid=account_info["puuid"],
        summoner_info=summoner_info,
    )
    await session.commit()
    await session.refresh(riot_account)

    logger.info("search_account_done", extra={"riot_account_id": str(riot_account.id)})
    return RiotAccountResponse.model_validate(riot_account)
