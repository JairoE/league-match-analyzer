"""Timeline extraction jobs for the LLM data pipeline.

Fetches match timelines, extracts state vectors and actions, and persists
them to Postgres for downstream ΔW computation and LLM analysis.
"""

from __future__ import annotations

import json

from sqlmodel import select

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.match import Match
from app.models.match_action import MatchActionRecord
from app.models.match_state_vector import MatchStateVector
from app.services.action_extraction import extract_actions
from app.services.cache import get_redis
from app.services.riot_api_client import RiotApiClient, RiotRequestError
from app.services.riot_match_id import normalize_match_id
from app.services.state_vector import extract_state_vectors
from app.services.worker_metrics import increment_metric_safe

logger = get_logger("league_api.jobs.timeline_extraction")

# Redis TTL for cached timeline payloads (1 hour)
TIMELINE_CACHE_TTL_SECONDS = 3600


async def extract_match_timeline_job(
    ctx: dict,
    match_id: str,
    average_rank: str | None = None,
) -> dict:
    """Fetch timeline for a match, extract state vectors and actions, persist to DB.

    Pipeline steps covered:
    1. Ingest: fetch timeline from Riot API (with Redis cache + TTL)
    2. Extract: pull per-minute state vectors and discrete action events
    3. Store: persist extracted data to match_state_vector and match_action tables

    Skips extraction if state vectors already exist for this match (idempotent).

    Args:
        ctx: ARQ worker context.
        match_id: Riot match ID (e.g., "NA1_12345").
        average_rank: Average rank tier of players (optional).

    Returns:
        Dict with extraction results (state_vectors, actions counts, or skip/error).
    """
    logger.info(
        "extract_match_timeline_job_start",
        extra={"match_id": match_id},
    )
    await increment_metric_safe("jobs.timeline_extraction.started")

    async with async_session_factory() as session:
        # Resolve match record
        result = await session.execute(
            select(Match).where(Match.game_id == match_id)
        )
        match = result.scalar_one_or_none()
        if not match:
            logger.warning(
                "extract_match_timeline_job_match_not_found",
                extra={"match_id": match_id},
            )
            await increment_metric_safe(
                "jobs.timeline_extraction.failed",
                tags={"reason": "match_not_found"},
            )
            return {"match_id": match_id, "status": "error", "error": "match_not_found"}

        # Idempotency check: skip if already extracted
        existing = await session.execute(
            select(MatchStateVector.id)
            .where(MatchStateVector.match_id == match.id)
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            logger.info(
                "extract_match_timeline_job_already_extracted",
                extra={"match_id": match_id},
            )
            await increment_metric_safe("jobs.timeline_extraction.skipped")
            return {"match_id": match_id, "status": "skipped"}

        # Fetch timeline (Redis cache with TTL)
        timeline = await _fetch_timeline_cached(ctx, match_id)
        if timeline is None:
            return {"match_id": match_id, "status": "error", "error": "timeline_fetch_failed"}

        # Extract state vectors
        state_vectors = extract_state_vectors(timeline, average_rank=average_rank)
        if not state_vectors:
            logger.warning(
                "extract_match_timeline_job_no_vectors",
                extra={"match_id": match_id},
            )
            await increment_metric_safe(
                "jobs.timeline_extraction.failed",
                tags={"reason": "no_vectors"},
            )
            return {"match_id": match_id, "status": "error", "error": "no_state_vectors"}

        # Extract actions
        actions = extract_actions(timeline, state_vectors)

        # Persist state vectors
        for sv in state_vectors:
            session.add(MatchStateVector(
                match_id=match.id,
                game_id=match_id,
                minute=sv.minute,
                timestamp_ms=sv.timestamp_ms,
                features=sv.to_feature_dict(),
            ))

        # Persist actions
        for action in actions:
            session.add(MatchActionRecord(
                match_id=match.id,
                game_id=match_id,
                action_type=action.action_type.value,
                timestamp_ms=action.timestamp_ms,
                participant_id=action.participant_id,
                team_id=action.team_id,
                action_detail=action.action_detail,
                pre_state_minute=action.pre_state_minute,
                post_state_minute=action.post_state_minute,
                was_undone=action.was_undone,
            ))

        await session.commit()

        logger.info(
            "extract_match_timeline_job_done",
            extra={
                "match_id": match_id,
                "state_vectors": len(state_vectors),
                "actions": len(actions),
            },
        )
        await increment_metric_safe("jobs.timeline_extraction.success")
        await increment_metric_safe(
            "jobs.timeline_extraction.vectors_stored",
            amount=len(state_vectors),
        )
        await increment_metric_safe(
            "jobs.timeline_extraction.actions_stored",
            amount=len(actions),
        )

        return {
            "match_id": match_id,
            "status": "ok",
            "state_vectors": len(state_vectors),
            "actions": len(actions),
        }


async def _fetch_timeline_cached(
    ctx: dict,
    match_id: str,
) -> dict | None:
    """Fetch timeline from Redis cache or Riot API with TTL caching.

    Transiently caches timeline payloads (~1MB) with TTL to save storage,
    as specified in the pipeline doc.

    Args:
        ctx: ARQ worker context (may contain riot_client).
        match_id: Riot match ID.

    Returns:
        Timeline payload dict, or None on failure.
    """
    riot_match_id, _ = normalize_match_id(match_id)
    cache_key = f"timeline:{riot_match_id}"

    redis = get_redis()
    raw = await redis.get(cache_key)
    if raw is not None:
        logger.info("timeline_cache_hit", extra={"match_id": match_id})
        return json.loads(raw)

    client = ctx.get("riot_client") or RiotApiClient()
    try:
        timeline = await client.fetch_match_timeline(riot_match_id)
    except RiotRequestError as exc:
        logger.error(
            "timeline_fetch_failed",
            extra={"match_id": match_id, "status": exc.status, "message": exc.message},
        )
        await increment_metric_safe(
            "jobs.timeline_extraction.failed",
            tags={"reason": "riot_api_error", "status": str(exc.status or 0)},
        )
        return None

    # Cache with TTL (transient, per pipeline spec)
    await redis.set(cache_key, json.dumps(timeline), ex=TIMELINE_CACHE_TTL_SECONDS)
    logger.info("timeline_cached", extra={"match_id": match_id, "ttl": TIMELINE_CACHE_TTL_SECONDS})
    return timeline
