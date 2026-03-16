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

from dotenv import load_dotenv

_api_root = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(_api_root))

# Load env before importing app (database_url, etc.)
load_dotenv(_api_root / ".env")


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

    if not aggregates:
        print("No action aggregates (no scored actions for this account/filters).")
        return

    print(f"K_min={MIN_PERSONAL_SAMPLE_SIZE} (personal stats trusted when K >= K_min)\n")
    for a in aggregates:
        k = a.group_key
        p = a.personal_stats
        pop = a.population_stats
        insuf = " [INSUFFICIENT PERSONAL]" if a.insufficient_personal_sample else ""
        print(
            f"champion={k.champion_id} rank={k.rank_tier} "
            f"action_type={k.action_type} action_key={k.action_key}{insuf}"
        )
        print(
            f"  personal:   K={p.count} "
            f"mean_ΔW={p.mean_delta_w:.4f if p.mean_delta_w is not None else 'N/A'} "
            f"mean_W(x)={p.mean_pre_win_prob:.4f if p.mean_pre_win_prob is not None else 'N/A'} "
            f"stddev_ΔW={p.stddev_delta_w:.4f if p.stddev_delta_w is not None else 'N/A'}"
        )
        print(
            f"  population: K={pop.count} "
            f"mean_ΔW={pop.mean_delta_w:.4f if pop.mean_delta_w is not None else 'N/A'} "
            f"mean_W(x)={pop.mean_pre_win_prob:.4f if pop.mean_pre_win_prob is not None else 'N/A'} "
            f"stddev_ΔW={pop.stddev_delta_w:.4f if pop.stddev_delta_w is not None else 'N/A'}"
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
