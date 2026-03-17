"""Print action aggregation stats for a riot account (pipeline step 5 debug).

Calls aggregate_action_stats_for_player and prints per-group K, mean ΔW,
mean pre_win_prob, stddev, and insufficient_personal_sample flag.

Usage:
    # Load .env from services/api if present
    python scripts/aggregate_actions_debug.py --riot-account-id <UUID>
    python scripts/aggregate_actions_debug.py --riot-id "name#NA1" --champion 157
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


def _fmt_stat(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}"


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
        # Debug helper should never block on metadata; fall back gracefully.
        return {}


_OBJECTIVE_LABELS: dict[str, str] = {
    "DRAGON": "Dragon",
    "RIFTHERALD": "Rift Herald",
    "BARON_NASHOR": "Baron Nashor",
}


def _format_action_label(
    action_type: str,
    action_key: str,
    item_names: dict[str, str],
) -> str:
    """Return a human-readable label for the action key."""
    if action_type == "ITEM_PURCHASE":
        name = item_names.get(action_key)
        if name:
            return f"{name} ({action_key})"
        return f"item_id={action_key}"

    if action_type == "OBJECTIVE_KILL":
        label = _OBJECTIVE_LABELS.get(action_key.upper(), action_key)
        return f"{label} ({action_key})"

    return action_key


async def _run(
    riot_account_id: str | None,
    riot_id: str | None,
    champion: str | None,
    rank_tier: str | None,
) -> None:
    from app.db.session import async_session_factory
    from app.models.riot_account import RiotAccount
    from app.services.action_aggregation import (
        MIN_PERSONAL_SAMPLE_SIZE,
        aggregate_action_stats_for_player,
    )
    from sqlmodel import select

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

        from uuid import UUID

        aggregates = await aggregate_action_stats_for_player(
            session,
            UUID(account_id),
            champion=champion,
            rank_tier=rank_tier,
        )

        # Load item metadata after querying aggregates so failures here don't
        # affect the core stats path.
        item_names = await _load_item_name_map()

    if not aggregates:
        print("No action aggregates (no scored actions for this account/filters).")
        return

    print(f"K_min={MIN_PERSONAL_SAMPLE_SIZE} (personal stats trusted when K >= K_min)\n")
    for a in aggregates:
        k = a.group_key
        p = a.personal_stats
        pop = a.population_stats
        insuf = " [INSUFFICIENT PERSONAL]" if a.insufficient_personal_sample else ""
        action_label = _format_action_label(
            k.action_type,
            k.action_key,
            item_names,
        )
        print(
            f"champion={k.champion_id} rank={k.rank_tier} "
            f"action_type={k.action_type} action_key={action_label}{insuf}"
        )
        print(
            f"  personal:   K={p.count} "
            f"mean_ΔW={_fmt_stat(p.mean_delta_w)} "
            f"mean_W(x)={_fmt_stat(p.mean_pre_win_prob)} "
            f"stddev_ΔW={_fmt_stat(p.stddev_delta_w)}"
        )
        print(
            f"  population: K={pop.count} "
            f"mean_ΔW={_fmt_stat(pop.mean_delta_w)} "
            f"mean_W(x)={_fmt_stat(pop.mean_pre_win_prob)} "
            f"stddev_ΔW={_fmt_stat(pop.stddev_delta_w)}"
        )
        print()
    print(f"Total groups: {len(aggregates)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print action aggregation stats for a riot account (debug)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--riot-account-id",
        type=str,
        help="Riot account UUID",
    )
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
