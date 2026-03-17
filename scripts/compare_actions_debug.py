"""Print action comparison results for a riot account (pipeline step 6 debug).

Calls aggregate_action_stats_for_player (step 5), then compare_action_stats
(step 6) and prints ranked actions, improvement gaps, and selection bias flags.

Usage:
    python scripts/compare_actions_debug.py --riot-account-id <UUID>
    python scripts/compare_actions_debug.py --riot-id "name#NA1" --champion 157
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

_api_root = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(_api_root))

# Load env before importing app (database_url, etc.)
load_dotenv(_api_root / ".env")


_OBJECTIVE_LABELS: dict[str, str] = {
    "DRAGON": "Dragon",
    "RIFTHERALD": "Rift Herald",
    "BARON_NASHOR": "Baron Nashor",
}


async def _load_item_name_map() -> dict[str, str]:
    """Fetch a mapping of item_id -> human-readable item name from Data Dragon.

    Falls back to an empty dict on network failure so the script still works.
    """
    try:
        from app.services.ddragon_client import DdragonClient

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
        return {}


def _fmt(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}"


async def _run(
    riot_account_id: str | None,
    riot_id: str | None,
    champion: str | None,
    rank_tier: str | None,
) -> None:
    from uuid import UUID

    from sqlmodel import select

    from app.db.session import async_session_factory
    from app.models.riot_account import RiotAccount
    from app.services.action_aggregation import aggregate_action_stats_for_player
    from app.services.action_comparison import compare_action_stats

    if riot_account_id is None and riot_id is None:
        print("Provide --riot-account-id or --riot-id")
        return
    if riot_account_id is not None and riot_id is not None:
        print("Provide only one of --riot-account-id or --riot-id")
        return

    async with async_session_factory() as session:
        account_id = riot_account_id
        if riot_id is not None:
            result = await session.execute(
                select(RiotAccount).where(RiotAccount.riot_id == riot_id)
            )
            account = result.scalar_one_or_none()
            if not account:
                print(f"No riot account found for riot_id={riot_id!r}")
                return
            account_id = str(account.id)
            print(f"Resolved riot_id {riot_id!r} -> account_id={account_id}\n")

        aggregates = await aggregate_action_stats_for_player(
            session,
            UUID(account_id),
            champion=champion,
            rank_tier=rank_tier,
        )

    if not aggregates:
        print("No action aggregates (no scored actions for this account/filters).")
        return

    # Load item metadata
    item_names = await _load_item_name_map()

    comparison = compare_action_stats(
        aggregates,
        item_names=item_names,
        objective_names=_OBJECTIVE_LABELS,
    )

    if comparison is None:
        print("No comparison results (all actions had no effective ΔW).")
        return

    # Print each group
    for group in comparison.groups:
        print(
            f"=== {group.action_type} | champion={group.champion_id} "
            f"rank={group.rank_tier} ==="
        )
        print()

        print("  Ranked actions (by effective ΔW):")
        for a in group.ranked_actions:
            name = a.action_name or a.action_key
            fallback = " [population]" if a.used_population_fallback else ""
            print(
                f"    #{a.rank} {name} — ΔW={_fmt(a.effective_delta_w)} "
                f"W(x)={_fmt(a.mean_pre_win_prob)} "
                f"personal_K={a.personal_count}{fallback}"
            )
        print()

        if group.summoner_top_actions:
            print("  Summoner's most-used:")
            for a in group.summoner_top_actions:
                name = a.action_name or a.action_key
                print(f"    {name} — K={a.personal_count} (rank #{a.rank})")
            print()

        if group.improvement_gaps:
            print("  Improvement gaps:")
            for g in group.improvement_gaps:
                s_name = g.summoner_action.action_name or g.summoner_action.action_key
                b_name = (
                    g.better_alternative.action_name
                    or g.better_alternative.action_key
                )
                print(
                    f"    {s_name} (ΔW={_fmt(g.summoner_action.effective_delta_w)}) "
                    f"-> {b_name} (ΔW={_fmt(g.better_alternative.effective_delta_w)}) "
                    f"gap={_fmt(g.delta_w_gap)}"
                )
            print()

        if group.selection_bias_flags:
            print("  Selection bias flags (high W(x), low ΔW):")
            for f in group.selection_bias_flags:
                name = f.action_name or f.action_key
                print(
                    f"    {name} — W(x)={_fmt(f.mean_pre_win_prob)} "
                    f"ΔW={_fmt(f.effective_delta_w)} "
                    f"(best={_fmt(f.population_best_delta_w)})"
                )
            print()

    # Cross-group summary
    if comparison.top_improvement_opportunities:
        print("=== TOP IMPROVEMENT OPPORTUNITIES ===")
        for i, g in enumerate(comparison.top_improvement_opportunities, 1):
            s_name = g.summoner_action.action_name or g.summoner_action.action_key
            b_name = (
                g.better_alternative.action_name
                or g.better_alternative.action_key
            )
            print(
                f"  {i}. Switch {s_name} (ΔW={_fmt(g.summoner_action.effective_delta_w)}) "
                f"-> {b_name} (ΔW={_fmt(g.better_alternative.effective_delta_w)}) "
                f"gap={_fmt(g.delta_w_gap)}"
            )
        print()

    if comparison.top_selection_bias_flags:
        print("=== SELECTION BIAS FLAGS ===")
        for f in comparison.top_selection_bias_flags:
            name = f.action_name or f.action_key
            print(
                f"  {name} — W(x)={_fmt(f.mean_pre_win_prob)} "
                f"ΔW={_fmt(f.effective_delta_w)}"
            )
        print()

    print(f"Groups: {len(comparison.groups)}, Schema version: {comparison.schema_version}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print action comparison results for a riot account (debug)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--riot-account-id", type=str, help="Riot account UUID")
    group.add_argument(
        "--riot-id",
        type=str,
        help='Riot ID (e.g. "name#NA1") to resolve to account',
    )
    parser.add_argument("--champion", type=str, default=None, help="Filter by champion_id")
    parser.add_argument("--rank-tier", type=str, default=None, help="Filter by rank tier")
    args = parser.parse_args()
    asyncio.run(
        _run(
            args.riot_account_id,
            args.riot_id,
            args.champion,
            args.rank_tier,
        )
    )


if __name__ == "__main__":
    main()
