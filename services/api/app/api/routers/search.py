from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.api.routers.match_detail_enqueue import enqueue_details_background
from app.db.session import get_session
from app.schemas.match import MatchListItem, PaginatedMatchList, PaginationMeta
from app.schemas.user import RiotAccountResponse
from app.services.match_sync import upsert_matches_for_riot_account
from app.services.matches import list_matches_for_riot_account
from app.services.riot_account_upsert import find_or_create_riot_account
from app.services.riot_accounts import get_riot_account_by_riot_id
from app.services.riot_api_client import RiotApiClient, RiotRequestError
from app.services.riot_id_parser import parse_riot_id
from app.services.riot_sync import backfill_match_details_inline

router = APIRouter(prefix="/search", tags=["search"])
logger = get_logger("league_api.search")


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
    session: AsyncSession = Depends(get_session),
) -> PaginatedMatchList:
    """Search for a riot account by Riot ID and return their matches.

    This is a stateless lookup: finds or creates the riot_account,
    syncs their recent matches, and returns the list. Does not
    auto-link to any user.

    Args:
        riot_id: Riot ID in gameName#tagLine format (URL-encoded # as %23).
        background_tasks: FastAPI background task runner.
        page: Page number (1-based).
        limit: Items per page (max 100).
        session: Async database session for queries.

    Returns:
        Paginated match list for the searched account.
    """
    logger.info("search_matches_start", extra={"riot_id": riot_id})

    # Parse and validate the riot ID
    try:
        parsed = parse_riot_id(riot_id)
    except ValueError:
        logger.info("search_matches_invalid_riot_id", extra={"riot_id": riot_id})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_riot_id")

    # Only sync with Riot API on page 1; page 2+ just queries DB
    if page == 1:
        try:
            async with RiotApiClient() as client:
                account_info = await client.fetch_account_by_riot_id(parsed.game_name, parsed.tag_line)
                summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
                match_ids = await client.fetch_match_ids_by_puuid(account_info["puuid"], start=0, count=20)
        except RiotRequestError:
            logger.exception("search_matches_riot_request_error", extra={"riot_id": riot_id})
            raise
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
            background_tasks.add_task(
                enqueue_details_background,
                logger=logger,
                match_ids=match_ids,
                context={"riot_account_id": str(riot_account.id)},
                success_event="search_matches_enqueued_details",
                failure_event="search_matches_enqueue_failed",
            )
    else:
        riot_account = await get_riot_account_by_riot_id(session, parsed.canonical)
        if not riot_account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Riot account not found")

    # Return the paginated match list
    matches, total = await list_matches_for_riot_account(session, riot_account.id, page, limit)

    # Inline backfill: fetch missing game_info directly from Riot API
    missing_count = sum(1 for m in matches if not m.game_info)
    if missing_count:
        logger.info(
            "search_matches_backfill_start",
            extra={"riot_id": riot_id, "missing": missing_count},
        )
        await backfill_match_details_inline(session, matches)

    logger.info(
        "search_matches_done",
        extra={"riot_id": riot_id, "riot_account_id": str(riot_account.id), "count": len(matches)},
    )
    return PaginatedMatchList(
        data=[MatchListItem.model_validate(match) for match in matches],
        meta=PaginationMeta.build(page=page, limit=limit, total=total),
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
    """Search for a riot account by Riot ID and return account info.

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

    try:
        async with RiotApiClient() as client:
            account_info = await client.fetch_account_by_riot_id(parsed.game_name, parsed.tag_line)
            summoner_info = await client.fetch_summoner_by_puuid(account_info["puuid"])
    except RiotRequestError:
        logger.exception("search_account_riot_request_error", extra={"riot_id": riot_id})
        raise
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
