"""Tool registry for the coach chat — each tool wraps an existing service.

Every tool pairs a Pydantic args model (source of the OpenAI function
schema) with an async executor that reads the player's data. Executors
always return a JSON-safe dict; missing data is reported as a
``{"message": ...}`` payload rather than an exception so a bad tool call
never crashes the stream.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.jobs.llm_analysis import OBJECTIVE_LABELS, load_item_name_map
from app.models.champion import Champion
from app.models.llm_analysis import LLMAnalysis
from app.models.riot_account import RiotAccount
from app.services.action_aggregation import aggregate_action_stats_for_player
from app.services.action_comparison import compare_action_stats
from app.services.matches import list_matches_for_riot_account

logger = get_logger("league_api.services.chat.tools")

MAX_TOOL_RESULT_CHARS = 4000


def cap_tool_result(payload: dict[str, Any], max_chars: int = MAX_TOOL_RESULT_CHARS) -> str:
    """Serialize a tool result compactly, hard-capping its size.

    Args:
        payload: JSON-safe tool result.
        max_chars: Maximum serialized length.

    Returns:
        Compact JSON string; oversized payloads are cut with a marker
        (the model reads tool output as text, so a clipped tail is fine).
    """
    serialized = json.dumps(payload, separators=(",", ":"), default=str)
    if len(serialized) <= max_chars:
        return serialized
    logger.warning("chat_tool_result_truncated", extra={"length": len(serialized)})
    return serialized[:max_chars] + "…[truncated]"


# ── Args models ───────────────────────────────────────────────────────


class PlayerProfileArgs(BaseModel):
    """No arguments — profile of the player being discussed."""


class LatestAnalysisArgs(BaseModel):
    champion_name: str | None = Field(
        default=None,
        description="Champion to fetch the analysis for; omit for the newest overall.",
    )


class ActionStatsArgs(BaseModel):
    champion_name: str | None = Field(
        default=None,
        description="Champion to filter stats to; omit for all champions.",
    )
    rank_tier: str | None = Field(
        default=None,
        description="Rank tier bucket (e.g. GOLD); omit to use all data.",
    )


class RecentMatchesArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=10, description="How many matches (max 10).")


# ── Executors ─────────────────────────────────────────────────────────


async def _get_player_profile(
    session: AsyncSession,
    account: RiotAccount,
    args: PlayerProfileArgs,
) -> dict[str, Any]:
    result = await session.execute(
        select(LLMAnalysis.champion_name)
        .where(LLMAnalysis.riot_account_id == account.id)
        .distinct()
    )
    analyzed = sorted({row[0] for row in result.fetchall()})
    return {
        "riot_id": account.riot_id,
        "rank_tier": account.rank_tier,
        "summoner_level": account.summoner_level,
        "analyzed_champions": analyzed,
    }


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


async def _get_latest_analysis(
    session: AsyncSession,
    account: RiotAccount,
    args: LatestAnalysisArgs,
) -> dict[str, Any]:
    statement = select(LLMAnalysis).where(LLMAnalysis.riot_account_id == account.id)
    if args.champion_name:
        statement = statement.where(
            func.lower(LLMAnalysis.champion_name) == args.champion_name.lower()
        )
    statement = statement.order_by(
        LLMAnalysis.created_at.desc()  # type: ignore[attr-defined]
    ).limit(1)
    result = await session.execute(statement)
    row = result.scalars().first()
    if row is None:
        return {
            "message": (
                "No AI Coach analysis exists for this player"
                + (f" on {args.champion_name}" if args.champion_name else "")
                + ". Suggest running the AI Coach analysis from the match page."
            )
        }
    return {
        "champion_name": row.champion_name,
        "rank_tier": row.rank_tier,
        "created_at": str(row.created_at),
        "match_count": len(row.match_ids),
        "recommendations": row.recommendations,
        "overall_assessment": _payload_str(row.output_payload, "overall_assessment"),
        "selection_bias_summary": _payload_str(row.output_payload, "selection_bias_summary"),
    }


def _trim_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": action.get("action_name") or action.get("action_key"),
        "effective_delta_w": action.get("effective_delta_w"),
        "personal_count": action.get("personal_count"),
        "rank": action.get("rank"),
    }


def _trim_gap(gap: dict[str, Any]) -> dict[str, Any]:
    return {
        "current": _trim_action(gap.get("summoner_action") or {}),
        "better": _trim_action(gap.get("better_alternative") or {}),
        "delta_w_gap": gap.get("delta_w_gap"),
    }


def _trim_comparison(comparison: dict[str, Any]) -> dict[str, Any]:
    """Reduce a full ComparisonResult dict to a chat-sized summary.

    Per-group improvement gaps are dropped — the global
    top_improvement_gaps list already carries the actionable ones.
    """
    groups = []
    for group in comparison.get("groups", [])[:4]:
        groups.append(
            {
                "champion_id": group.get("champion_id"),
                "rank_tier": group.get("rank_tier"),
                "action_type": group.get("action_type"),
                "top_actions": [
                    _trim_action(a) for a in group.get("ranked_actions", [])[:5]
                ],
            }
        )
    return {
        "groups": groups,
        "top_improvement_gaps": [
            _trim_gap(g)
            for g in comparison.get("top_improvement_opportunities", [])[:5]
        ],
        "selection_bias_flags": [
            {
                "name": f.get("action_name") or f.get("action_key"),
                "mean_pre_win_prob": f.get("mean_pre_win_prob"),
                "effective_delta_w": f.get("effective_delta_w"),
            }
            for f in comparison.get("top_selection_bias_flags", [])[:3]
        ],
    }


async def _get_action_stats(
    session: AsyncSession,
    account: RiotAccount,
    args: ActionStatsArgs,
) -> dict[str, Any]:
    champion_filter: str | None = None
    if args.champion_name:
        result = await session.execute(
            select(Champion).where(func.lower(Champion.name) == args.champion_name.lower())
        )
        champion = result.scalars().first()
        if champion is None:
            return {"message": f"Unknown champion '{args.champion_name}'."}
        champion_filter = str(champion.champ_id)

    aggregates = await aggregate_action_stats_for_player(
        session,
        account.id,
        champion=champion_filter,
        rank_tier=args.rank_tier,
    )
    if not aggregates:
        return {
            "message": (
                "No scored match data for this player"
                + (f" on {args.champion_name}" if args.champion_name else "")
                + ". Their matches may not be scored yet."
            )
        }

    item_names = await load_item_name_map()
    comparison = compare_action_stats(
        aggregates,
        item_names=item_names,
        objective_names=OBJECTIVE_LABELS,
    )
    if comparison is None:
        return {"message": "Match actions exist but none have win-probability scores yet."}
    return _trim_comparison(comparison.to_dict())


async def _list_recent_matches(
    session: AsyncSession,
    account: RiotAccount,
    args: RecentMatchesArgs,
) -> dict[str, Any]:
    matches, total = await list_matches_for_riot_account(
        session, account.id, page=1, limit=args.limit
    )
    summaries: list[dict[str, Any]] = []
    for match in matches:
        info = (match.game_info or {}).get("info", {})
        participants = info.get("participants") or []
        me = next(
            (p for p in participants if isinstance(p, dict) and p.get("puuid") == account.puuid),
            None,
        )
        if me is None:
            continue
        summaries.append(
            {
                "champion": me.get("championName"),
                "win": me.get("win"),
                "kills": me.get("kills"),
                "deaths": me.get("deaths"),
                "assists": me.get("assists"),
                "cs": (me.get("totalMinionsKilled") or 0) + (me.get("neutralMinionsKilled") or 0),
                "duration_s": info.get("gameDuration"),
                "queue_id": info.get("queueId"),
                "game_start_timestamp": match.game_start_timestamp,
            }
        )
    if not summaries:
        return {"message": "No stored matches with details for this player."}
    return {"total_matches": total, "matches": summaries}


# ── Registry ──────────────────────────────────────────────────────────


@dataclass
class ChatTool:
    """A callable tool exposed to the coach model.

    Attributes:
        name: OpenAI function name.
        description: What the model reads when deciding to call it.
        label: Human-readable activity line shown in the UI.
        args_model: Pydantic model that validates the call arguments.
        executor: Async function producing the JSON-safe result.
    """

    name: str
    description: str
    label: str
    args_model: type[BaseModel]
    executor: Callable[[AsyncSession, RiotAccount, Any], Awaitable[dict[str, Any]]]

    def to_openai_schema(self) -> dict[str, Any]:
        """Build the OpenAI function spec from the args model."""
        parameters = self.args_model.model_json_schema()
        parameters.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


CHAT_TOOLS: dict[str, ChatTool] = {
    tool.name: tool
    for tool in [
        ChatTool(
            name="get_player_profile",
            description=(
                "Get the player's riot id, rank tier, level, and which champions "
                "already have AI Coach analyses."
            ),
            label="Looking up the player profile…",
            args_model=PlayerProfileArgs,
            executor=_get_player_profile,
        ),
        ChatTool(
            name="get_latest_analysis",
            description=(
                "Get the most recent AI Coach analysis (recommendations, assessment, "
                "selection-bias notes), optionally for a specific champion."
            ),
            label="Reading the latest coaching analysis…",
            args_model=LatestAnalysisArgs,
            executor=_get_latest_analysis,
        ),
        ChatTool(
            name="get_action_stats",
            description=(
                "Get win-probability (ΔW) action statistics for the player: top-ranked "
                "item/objective choices, improvement gaps vs better alternatives, and "
                "selection-bias flags. Optionally filtered by champion and rank tier."
            ),
            label="Crunching win-probability stats…",
            args_model=ActionStatsArgs,
            executor=_get_action_stats,
        ),
        ChatTool(
            name="list_recent_matches",
            description=(
                "List the player's recent stored matches with champion, result, "
                "KDA, CS, queue, and duration."
            ),
            label="Fetching recent matches…",
            args_model=RecentMatchesArgs,
            executor=_list_recent_matches,
        ),
    ]
}


def openai_tool_schemas() -> list[dict[str, Any]]:
    """Return the OpenAI function specs for all registered chat tools."""
    return [tool.to_openai_schema() for tool in CHAT_TOOLS.values()]
