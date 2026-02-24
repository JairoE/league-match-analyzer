from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.api.routers.match_detail_enqueue import enqueue_details_background
from app.db.session import get_session
from app.schemas.match import MatchListItem
from app.schemas.user import RiotAccountResponse
from app.services.match_sync import upsert_matches_for_riot_account
from app.services.matches import list_matches_for_riot_account
from app.services.riot_account_upsert import find_or_create_riot_account
from app.services.riot_api_client import RiotApiClient, RiotRequestError
from app.services.riot_id_parser import parse_riot_id
from app.services.riot_sync import backfill_match_details_inline

router = APIRouter(prefix="/search", tags=["search"])
logger = get_logger("league_api.search")


@router.get(
    "/{riot_id}/matches",
    response_model=list[MatchListItem],
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
)
async def search_riot_account_matches(
    riot_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> list[MatchListItem]:
    """Search for a riot account by Riot ID and return their matches.

    This is a stateless lookup: finds or creates the riot_account,
    syncs their recent matches, and returns the list. Does not
    auto-link to any user.

    Args:
        riot_id: Riot ID in gameName#tagLine format (URL-encoded # as %23).
        background_tasks: FastAPI background task runner.
        session: Async database session for queries.

    Returns:
        List of match list items for the searched account.
    """
    logger.info("search_matches_start", extra={"riot_id": riot_id})

    # Parse and validate the riot ID
    try:
        parsed = parse_riot_id(riot_id)
    except ValueError:
        logger.info("search_matches_invalid_riot_id", extra={"riot_id": riot_id})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_riot_id")

    # Fetch from Riot API to get PUUID, summoner info, and match IDs
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

    # Find or create the riot account
    riot_account = await find_or_create_riot_account(
        session,
        riot_id=parsed.canonical,
        puuid=account_info["puuid"],
        summoner_info=summoner_info,
    )
    await session.commit()
    await session.refresh(riot_account)

    # Sync their recent matches
    await upsert_matches_for_riot_account(session, riot_account.id, match_ids)

    # Enqueue detail fetches in background
    if match_ids:
        background_tasks.add_task(
            enqueue_details_background,
            logger=logger,
            match_ids=match_ids,
            context={"riot_account_id": str(riot_account.id)},
            success_event="search_matches_enqueued_details",
            failure_event="search_matches_enqueue_failed",
        )

    # Return the match list
    matches = await list_matches_for_riot_account(session, riot_account.id)

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
    return [MatchListItem.model_validate(match) for match in matches]


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
