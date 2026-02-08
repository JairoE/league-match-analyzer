"""Match ingestion jobs for ARQ workers.

Fetches match IDs and details for individual users with rate limiting.
"""

from __future__ import annotations

from uuid import UUID

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.match import Match
from app.services.riot_match_id import normalize_match_id
from app.services.match_sync import upsert_matches_for_user
from app.services.riot_api_client import RiotApiClient, RiotRequestError
from app.services.users import get_user_by_id

logger = get_logger("league_api.jobs.match_ingestion")

# Default batch size for match ingestion
DEFAULT_MATCH_COUNT = 20


async def fetch_user_matches_job(
    ctx: dict,
    user_id: str,
    start: int = 0,
    count: int = DEFAULT_MATCH_COUNT,
) -> dict:
    """Fetch latest match IDs for a single user.

    Retrieves: Match IDs from Riot API for the user's PUUID.
    Transforms: Upserts match records and user-match links.
    Why: Enables background ingestion without blocking request handlers.

    Args:
        ctx: ARQ worker context.
        user_id: UUID string of the user.
        start: Offset for match list pagination.
        count: Number of matches to fetch.

    Returns:
        Dict with user_id, new_matches count, and status.
    """
    logger.info(
        "fetch_user_matches_job_start",
        extra={"user_id": user_id, "start": start, "count": count},
    )

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        logger.error("fetch_user_matches_job_invalid_uuid", extra={"user_id": user_id})
        return {"user_id": user_id, "status": "error", "error": "invalid_uuid"}

    async with async_session_factory() as session:
        user = await get_user_by_id(session, user_uuid)
        if not user:
            logger.warning(
                "fetch_user_matches_job_user_not_found",
                extra={"user_id": user_id},
            )
            return {"user_id": user_id, "status": "error", "error": "user_not_found"}

        try:
            client = RiotApiClient()
            match_ids = await client.fetch_match_ids_by_puuid(
                user.puuid, start=start, count=count
            )

            if not match_ids:
                logger.info(
                    "fetch_user_matches_job_no_matches",
                    extra={"user_id": user_id},
                )
                return {"user_id": user_id, "status": "ok", "new_matches": 0}

            new_links = await upsert_matches_for_user(session, user.id, match_ids)

            logger.info(
                "fetch_user_matches_job_done",
                extra={
                    "user_id": user_id,
                    "fetched": len(match_ids),
                    "new_links": new_links,
                },
            )

            # Enqueue detail fetch jobs for matches without game_info
            await _enqueue_detail_jobs(ctx, match_ids)

            return {
                "user_id": user_id,
                "status": "ok",
                "fetched": len(match_ids),
                "new_matches": new_links,
            }

        except RiotRequestError as exc:
            logger.error(
                "fetch_user_matches_job_riot_error",
                extra={
                    "user_id": user_id,
                    "status": exc.status,
                    "error_message": exc.message,
                },
            )
            return {
                "user_id": user_id,
                "status": "error",
                "error": "riot_api_error",
                "details": exc.message,
            }


async def _enqueue_detail_jobs(ctx: dict, match_ids: list[str]) -> None:
    """Enqueue match detail fetch jobs for matches without cached details.

    Args:
        ctx: ARQ worker context with redis pool.
        match_ids: List of Riot match IDs to check.
    """
    redis = ctx.get("redis")
    if not redis:
        logger.warning("fetch_user_matches_job_no_redis_context")
        return

    # Check which matches need detail fetching
    async with async_session_factory() as session:
        from sqlmodel import select

        result = await session.execute(
            select(Match.game_id).where(
                Match.game_id.in_(match_ids),
                Match.game_info.is_(None),
            )
        )
        missing_details = [row[0] for row in result.fetchall()]

    if missing_details:
        logger.info(
            "fetch_user_matches_job_enqueue_details",
            extra={"count": len(missing_details)},
        )
        # Enqueue in batches of 5 to avoid overwhelming rate limits
        for i in range(0, len(missing_details), 5):
            batch = missing_details[i : i + 5]
            await redis.enqueue_job("fetch_match_details_job", batch)


async def fetch_match_details_job(ctx: dict, match_ids: list[str]) -> dict:
    """Batch fetch match details for a list of match IDs.

    Retrieves: Match detail payloads from Riot API.
    Transforms: Persists game_info JSONB to Match records.
    Why: Populates match details for AI analysis pipeline.

    Args:
        ctx: ARQ worker context.
        match_ids: List of Riot match IDs to fetch.

    Returns:
        Dict with fetched count and any errors.
    """
    logger.info(
        "fetch_match_details_job_start",
        extra={"match_count": len(match_ids)},
    )

    fetched = 0
    errors = []

    async with async_session_factory() as session:
        from sqlmodel import select

        client = RiotApiClient()

        pending_commit = False
        for match_id in match_ids:
            try:
                riot_match_id, was_normalized = normalize_match_id(match_id)
                if was_normalized:
                    logger.info(
                        "fetch_match_details_job_normalized_id",
                        extra={"match_id": match_id, "riot_match_id": riot_match_id},
                    )

                payload = await client.fetch_match_by_id(riot_match_id)

                # Update match record
                result = await session.execute(
                    select(Match).where(Match.game_id == match_id)
                )
                match = result.scalar_one_or_none()

                if match:
                    match.game_info = payload
                    if (
                        payload
                        and "info" in payload
                        and "gameStartTimestamp" in payload["info"]
                    ):
                        match.game_start_timestamp = payload["info"][
                            "gameStartTimestamp"
                        ]

                    fetched += 1
                    pending_commit = True
                    logger.info(
                        "fetch_match_details_job_fetched",
                        extra={"match_id": match_id},
                    )
                else:
                    logger.warning(
                        "fetch_match_details_job_match_not_found",
                        extra={"match_id": match_id},
                    )

            except RiotRequestError as exc:
                logger.error(
                    "fetch_match_details_job_error",
                    extra={
                        "match_id": match_id,
                        "status": exc.status,
                        "message": exc.message,
                    },
                )
                errors.append({"match_id": match_id, "error": exc.message})

    if pending_commit:
        await session.commit()
    logger.info(
        "fetch_match_details_job_done",
        extra={"fetched": fetched, "errors": len(errors)},
    )

    return {
        "status": "ok" if not errors else "partial",
        "fetched": fetched,
        "errors": errors,
    }
