"""Run LLM analysis for a summoner's champion (pipeline steps 5→8).

Orchestrates aggregation (step 5), comparison (step 6), LLM prompting (step 7),
and persistence (step 8) into a single ARQ job.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlmodel import select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.champion import Champion
from app.models.llm_analysis import LLMAnalysis
from app.services.action_aggregation import aggregate_action_stats_for_player
from app.services.action_comparison import compare_action_stats
from app.services.ddragon_client import DdragonClient
from app.services.llm_client import OpenAIClient
from app.services.llm_prompt import build_system_prompt, build_user_prompt
from app.services.llm_response_schema import LLMAnalysisResponse
from app.services.worker_metrics import increment_metric_safe

logger = get_logger("league_api.jobs.llm_analysis")

_OBJECTIVE_LABELS: dict[str, str] = {
    "DRAGON": "Dragon",
    "RIFTHERALD": "Rift Herald",
    "BARON_NASHOR": "Baron Nashor",
}


async def _load_item_name_map() -> dict[str, str]:
    """Fetch item_id → name mapping from Data Dragon.

    Returns:
        Mapping of item IDs to display names; empty dict on failure.
    """
    try:
        client = DdragonClient()
        version = await client.fetch_latest_version()
        url = f"{DdragonClient.CDN_BASE_URL}/{version}/data/en_US/item.json"
        async with httpx.AsyncClient(timeout=20.0) as http_client:
            response = await http_client.get(url)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        data = payload.get("data", {})
        return {
            item_id: (info.get("name") or str(item_id))
            for item_id, info in data.items()
            if isinstance(info, dict)
        }
    except Exception:
        logger.warning("load_item_name_map_failed")
        return {}


async def _resolve_champion_name(
    session: Any,
    champion_id: str,
) -> str:
    """Resolve a numeric champion ID to a display name via the Champion table.

    Args:
        session: Async database session.
        champion_id: Riot numeric champion ID as string.

    Returns:
        Champion display name, or the raw ID if not found.
    """
    try:
        champ_id_int = int(champion_id)
    except (ValueError, TypeError):
        return champion_id

    result = await session.execute(
        select(Champion).where(Champion.champ_id == champ_id_int)
    )
    champ = result.scalar_one_or_none()
    return champ.name if champ else champion_id


async def _get_scored_match_ids(
    session: Any,
    riot_account_id: UUID,
    champion: str | None,
    rank_tier: str | None,
) -> list[str]:
    """Collect Riot game_ids for scored matches matching the filters.

    Args:
        session: Async database session.
        riot_account_id: Account UUID.
        champion: Optional champion ID filter.
        rank_tier: Optional rank tier filter (unused in V1, reserved).

    Returns:
        List of Riot match IDs (game_id strings).
    """
    query = text("""
        SELECT DISTINCT m.game_id
        FROM match m
        JOIN riot_account_match ram ON ram.match_id = m.id
        JOIN match_action ma ON ma.match_id = m.id
        WHERE ram.riot_account_id = :account_id
          AND ma.delta_w IS NOT NULL
    """)
    params: dict[str, Any] = {"account_id": str(riot_account_id)}

    result = await session.execute(query, params)
    return [row[0] for row in result.fetchall()]


async def llm_analysis_job(
    ctx: dict,
    riot_account_id: str,
    champion: str,
    rank_tier: str | None = None,
) -> dict:
    """Run LLM analysis for a summoner's champion (pipeline steps 5→8).

    Aggregates action stats (step 5), compares against population optimal (step 6),
    sends gap analysis to LLM (step 7), and persists results (step 8).

    Args:
        ctx: ARQ worker context (unused).
        riot_account_id: Riot account UUID string.
        champion: Riot numeric champion ID (required in V1).
        rank_tier: Optional rank tier filter (e.g. "GOLD").

    Returns:
        Dict with status and metadata (analysis_id, token counts, etc.).
    """
    logger.info(
        "llm_analysis_job_start",
        extra={
            "riot_account_id": riot_account_id,
            "champion": champion,
            "rank_tier": rank_tier,
        },
    )
    await increment_metric_safe("jobs.llm_analysis.started")

    settings = get_settings()
    if not settings.openai_api_key:
        logger.warning("llm_analysis_job_no_api_key")
        await increment_metric_safe("jobs.llm_analysis.skipped", tags={"reason": "no_api_key"})
        return {"status": "skipped", "reason": "no_api_key"}

    account_uuid = UUID(riot_account_id)

    async with async_session_factory() as session:
        # Step 5: Aggregate
        aggregates = await aggregate_action_stats_for_player(
            session,
            account_uuid,
            champion=champion,
            rank_tier=rank_tier,
        )

        if not aggregates:
            logger.info(
                "llm_analysis_job_no_data",
                extra={"riot_account_id": riot_account_id},
            )
            await increment_metric_safe(
                "jobs.llm_analysis.skipped", tags={"reason": "no_data"}
            )
            return {"status": "no_data"}

        # Fetch item names for readable prompts
        item_names = await _load_item_name_map()

        # Step 6: Compare
        comparison = compare_action_stats(
            aggregates,
            item_names=item_names,
            objective_names=_OBJECTIVE_LABELS,
        )

        if comparison is None:
            logger.info(
                "llm_analysis_job_no_comparison",
                extra={"riot_account_id": riot_account_id},
            )
            await increment_metric_safe(
                "jobs.llm_analysis.skipped", tags={"reason": "no_comparison"}
            )
            return {"status": "no_comparison"}

        # Resolve champion name
        champion_name = await _resolve_champion_name(session, champion)

        # Collect match IDs
        match_ids = await _get_scored_match_ids(
            session, account_uuid, champion, rank_tier
        )

        # Determine rank_tier from comparison if not provided
        effective_rank = rank_tier
        if effective_rank is None and comparison.groups:
            effective_rank = comparison.groups[0].rank_tier

    # Step 7: Prompt LLM
    comparison_dict = comparison.to_dict()
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(comparison_dict, champion_name, effective_rank)

    try:
        client = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.llm_model_name,
        )
        llm_response = await client.complete(system_prompt, user_prompt)
    except Exception:
        logger.exception(
            "llm_analysis_job_llm_error",
            extra={"riot_account_id": riot_account_id},
        )
        await increment_metric_safe(
            "jobs.llm_analysis.failed", tags={"reason": "llm_error"}
        )
        return {"status": "llm_error"}

    # Parse response
    recommendations_list: list[dict[str, Any]] = []
    output_payload: dict[str, Any] = {}
    parse_status = "ok"

    try:
        parsed = LLMAnalysisResponse.model_validate_json(llm_response.content)
        recommendations_list = [r.model_dump() for r in parsed.recommendations]
        output_payload = parsed.model_dump()
    except Exception:
        logger.warning(
            "llm_analysis_job_parse_error",
            extra={"riot_account_id": riot_account_id},
        )
        # Store raw response even on parse failure
        try:
            output_payload = json.loads(llm_response.content)
        except (json.JSONDecodeError, TypeError):
            output_payload = {"raw": llm_response.content}
        parse_status = "parse_error"

    # Step 8: Persist
    async with async_session_factory() as session:
        analysis = LLMAnalysis(
            riot_account_id=account_uuid,
            champion_name=champion_name,
            rank_tier=effective_rank,
            match_ids=match_ids,
            schema_version=comparison.schema_version,
            input_payload=comparison_dict,
            output_payload=output_payload,
            recommendations=recommendations_list,
            model_name=llm_response.model_name,
            token_count_input=llm_response.token_count_input,
            token_count_output=llm_response.token_count_output,
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)
        analysis_id = str(analysis.id)

    logger.info(
        "llm_analysis_job_done",
        extra={
            "riot_account_id": riot_account_id,
            "analysis_id": analysis_id,
            "status": parse_status,
            "token_input": llm_response.token_count_input,
            "token_output": llm_response.token_count_output,
            "recommendations_count": len(recommendations_list),
        },
    )
    await increment_metric_safe("jobs.llm_analysis.success")

    return {
        "status": parse_status,
        "analysis_id": analysis_id,
        "champion_name": champion_name,
        "rank_tier": effective_rank,
        "match_count": len(match_ids),
        "recommendations_count": len(recommendations_list),
        "token_input": llm_response.token_count_input,
        "token_output": llm_response.token_count_output,
    }
