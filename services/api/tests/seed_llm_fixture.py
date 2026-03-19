"""One-time script to seed the LLM pipeline fixture from a real DB.

Queries the DB for damanjr#NA1, runs steps 5-6 (aggregate + compare), and
writes the result to tests/fixtures/damanjr_comparison.json.  Commit that
file so test_llm_pipeline_real_data.py never needs a live DB again.

Usage:
    DATABASE_URL=postgresql+asyncpg://user:pass@localhost/league_db \\
        python services/api/tests/seed_llm_fixture.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure the api package is importable when run directly.
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlmodel import select  # noqa: E402 (after sys.path patch)

from app.db.session import async_session_factory  # noqa: E402
from app.jobs.llm_analysis import (  # noqa: E402
    OBJECTIVE_LABELS,
    _resolve_champion_name,
    load_item_name_map,
)
from app.models.riot_account import RiotAccount  # noqa: E402
from app.services.action_aggregation import (  # noqa: E402
    ActionAggregate,
    aggregate_action_stats_for_player,
)
from app.services.action_comparison import compare_action_stats  # noqa: E402

_RIOT_ID = "damanjr#NA1"
_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "damanjr_comparison.json"


def _pick_top_champion(aggregates: list[ActionAggregate]) -> str:
    """Return the champion_id with the highest total personal action count."""
    totals: dict[str, int] = {}
    for agg in aggregates:
        cid = agg.group_key.champion_id
        totals[cid] = totals.get(cid, 0) + agg.personal_stats.count
    return max(totals, key=lambda k: totals[k])


async def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        sys.exit("ERROR: DATABASE_URL env var is required")

    print(f"Looking up {_RIOT_ID!r} in DB...")
    async with async_session_factory() as session:
        result = await session.execute(
            select(RiotAccount).where(RiotAccount.riot_id == _RIOT_ID)
        )
        account = result.scalar_one_or_none()
        if account is None:
            sys.exit(
                f"ERROR: No RiotAccount found for {_RIOT_ID!r}. "
                "Hit GET /search/damanjr%23NA1/matches first."
            )

        print(f"Found account: id={account.id}, rank={account.rank_tier}")

        # Step 5: aggregate
        print("Running step 5 (aggregate)...")
        all_aggregates = await aggregate_action_stats_for_player(
            session, account.id, champion=None, rank_tier=None
        )
        if not all_aggregates:
            sys.exit(
                "ERROR: No scored match_action rows found. "
                "Ensure steps 1-4 (ingestion + scoring) have completed."
            )

        champion_id_override = os.environ.get("CHAMPION_ID")
        if champion_id_override:
            top_champion_id = champion_id_override
            print(f"Using CHAMPION_ID override: {top_champion_id}")
        else:
            top_champion_id = _pick_top_champion(all_aggregates)
        aggregates = [
            agg for agg in all_aggregates
            if agg.group_key.champion_id == top_champion_id
        ]
        if not aggregates:
            sys.exit(f"ERROR: No aggregates found for champion_id={top_champion_id!r}.")
        print(f"Top champion id={top_champion_id}, groups={len(aggregates)}")

        champion_name = await _resolve_champion_name(session, top_champion_id)

    print(f"Champion name: {champion_name}")

    # Fetch item names
    print("Fetching item names from DDragon...")
    item_names = await load_item_name_map()

    # Step 6: compare
    print("Running step 6 (compare)...")
    comparison = compare_action_stats(
        aggregates,
        item_names=item_names,
        objective_names=OBJECTIVE_LABELS,
    )
    if comparison is None:
        sys.exit("ERROR: compare_action_stats returned None — not enough data.")

    effective_rank = (
        comparison.groups[0].rank_tier if comparison.groups else account.rank_tier
    )

    fixture = {
        "riot_id": _RIOT_ID,
        "champion_name": champion_name,
        "champion_id": top_champion_id,
        "rank_tier": effective_rank,
        "comparison": comparison.to_dict(),
    }

    _FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE_PATH.write_text(json.dumps(fixture, indent=2))
    print(f"\nFixture written to: {_FIXTURE_PATH}")
    print(f"  champion : {champion_name} ({top_champion_id})")
    print(f"  rank     : {effective_rank}")
    print(f"  groups   : {len(aggregates)}")
    print("\nCommit fixtures/damanjr_comparison.json and run the test with:")
    print("  OPENAI_API_KEY=sk-... pytest services/api/tests/test_llm_pipeline_real_data.py -s -v")


if __name__ == "__main__":
    asyncio.run(main())
