"""Score match actions with the win probability model (ΔW pipeline step 4).

Populates pre_win_prob, post_win_prob, and delta_w on match_action rows
for a given match. Idempotent: re-running overwrites existing scores.
"""

from __future__ import annotations

from sqlmodel import select

from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.match import Match
from app.models.match_action import MatchActionRecord
from app.models.match_state_vector import MatchStateVector
from app.services.win_prob_scoring import score_state
from app.services.worker_metrics import increment_metric_safe

logger = get_logger("league_api.jobs.score_actions")


async def score_actions_job(
    ctx: dict,
    match_id: str,
) -> dict:
    """Score all actions for a match and persist pre_win_prob, post_win_prob, delta_w.

    Uses the V1 win probability model to compute w(x) at pre- and post-action
    states; delta_w = w(z) - w(x). If the model is not loaded (no path or
    load failure), skips scoring and returns status "skipped".

    Args:
        ctx: ARQ worker context (unused).
        match_id: Riot match ID (game_id).

    Returns:
        Dict with status, match_id, and counts (scored, skipped, no_model).
    """
    logger.info("score_actions_job_start", extra={"match_id": match_id})
    await increment_metric_safe("jobs.score_actions.started")

    async with async_session_factory() as session:
        result = await session.execute(select(Match).where(Match.game_id == match_id))
        match = result.scalar_one_or_none()
        if not match:
            logger.warning(
                "score_actions_job_match_not_found",
                extra={"match_id": match_id},
            )
            await increment_metric_safe(
                "jobs.score_actions.failed",
                tags={"reason": "match_not_found"},
            )
            return {"match_id": match_id, "status": "error", "error": "match_not_found"}

        # Load state vectors by minute
        vec_result = await session.execute(
            select(MatchStateVector)
            .where(MatchStateVector.match_id == match.id)
            .order_by(MatchStateVector.minute)
        )
        state_vectors = list(vec_result.scalars().all())
        vectors_by_minute = {sv.minute: sv.features for sv in state_vectors}

        # Load actions
        actions_result = await session.execute(
            select(MatchActionRecord).where(MatchActionRecord.match_id == match.id)
        )
        actions = list(actions_result.scalars().all())

        if not actions:
            logger.info(
                "score_actions_job_no_actions",
                extra={"match_id": match_id},
            )
            await increment_metric_safe("jobs.score_actions.success")
            return {
                "match_id": match_id,
                "status": "ok",
                "scored": 0,
                "skipped": 0,
                "no_model": 0,
            }

        scored = 0
        skipped = 0
        no_model = 0

        for action in actions:
            pre_features = vectors_by_minute.get(action.pre_state_minute)
            if pre_features is None:
                skipped += 1
                continue

            pre_win_prob = score_state(pre_features)
            if pre_win_prob is None:
                no_model += 1
                break

            post_win_prob: float | None = None
            if action.post_state_minute is not None:
                post_features = vectors_by_minute.get(action.post_state_minute)
                if post_features is not None:
                    post_win_prob = score_state(post_features)

            delta_w: float | None = None
            if pre_win_prob is not None and post_win_prob is not None:
                delta_w = post_win_prob - pre_win_prob

            action.pre_win_prob = pre_win_prob
            action.post_win_prob = post_win_prob
            action.delta_w = delta_w
            scored += 1

        if no_model > 0:
            logger.info(
                "score_actions_job_no_model",
                extra={"match_id": match_id},
            )
            await increment_metric_safe("jobs.score_actions.skipped")
            return {
                "match_id": match_id,
                "status": "skipped",
                "scored": 0,
                "skipped": skipped,
                "no_model": 1,
            }

        session.add_all(actions)
        await session.commit()

        logger.info(
            "score_actions_job_done",
            extra={"match_id": match_id, "scored": scored, "skipped": skipped},
        )
        await increment_metric_safe("jobs.score_actions.success")

        return {
            "match_id": match_id,
            "status": "ok",
            "scored": scored,
            "skipped": skipped,
            "no_model": 0,
        }
