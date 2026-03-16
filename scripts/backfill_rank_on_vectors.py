"""Backfill average_rank on existing state vectors using riot_account.rank_tier.

Targeted backfill that updates the JSONB features column without re-running
full extraction. Uses DB-only lookups (no Redis, no Riot API calls).

Usage:
    python scripts/backfill_rank_on_vectors.py
    python scripts/backfill_rank_on_vectors.py --dry-run
    python scripts/backfill_rank_on_vectors.py --min-known 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from statistics import median_low

import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://league:league@localhost:5432/league",
)

RANK_ORDER = [
    "",
    "IRON",
    "BRONZE",
    "SILVER",
    "GOLD",
    "PLATINUM",
    "EMERALD",
    "DIAMOND",
    "MASTER",
    "GRANDMASTER",
    "CHALLENGER",
]

_TIER_TO_ORDINAL: dict[str, int] = {
    tier: i for i, tier in enumerate(RANK_ORDER) if tier
}


async def _find_matches_needing_rank(conn: asyncpg.Connection) -> list[dict]:
    """Find matches with state vectors where average_rank is null/empty."""
    rows = await conn.fetch("""
        SELECT DISTINCT m.id AS match_id, m.game_info
        FROM match m
        JOIN match_state_vector msv ON msv.match_id = m.id
        WHERE m.game_info IS NOT NULL
          AND (
              msv.features->>'average_rank' IS NULL
              OR msv.features->>'average_rank' = ''
          )
    """)
    return [{"match_id": row["match_id"], "game_info": row["game_info"]} for row in rows]


async def _resolve_rank_from_db(
    conn: asyncpg.Connection,
    puuids: list[str],
) -> list[int]:
    """Look up rank_tier ordinals for a list of PUUIDs from DB."""
    if not puuids:
        return []
    rows = await conn.fetch(
        "SELECT rank_tier FROM riot_account WHERE puuid = ANY($1) AND rank_tier IS NOT NULL",
        puuids,
    )
    ordinals = []
    for row in rows:
        tier = row["rank_tier"].strip().upper()
        if tier in _TIER_TO_ORDINAL:
            ordinals.append(_TIER_TO_ORDINAL[tier])
    return ordinals


async def _run(min_known: int, dry_run: bool) -> None:
    """Main backfill logic."""
    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(dsn)
    print("Connected to database. Finding matches needing rank backfill...")

    try:
        matches = await _find_matches_needing_rank(conn)
    except Exception:
        await conn.close()
        raise

    if not matches:
        print("All state vectors already have average_rank populated. Nothing to do.")
        await conn.close()
        return

    print(f"Found {len(matches)} matches needing rank backfill.")

    updated = 0
    skipped = 0

    for entry in matches:
        match_id = entry["match_id"]
        game_info = entry["game_info"]
        if isinstance(game_info, str):
            game_info = json.loads(game_info)

        participants = (game_info.get("info") or {}).get("participants") or []
        puuids = [p.get("puuid") for p in participants if p.get("puuid")]

        ordinals = await _resolve_rank_from_db(conn, puuids)

        if len(ordinals) < min_known:
            skipped += 1
            continue

        median_ordinal = median_low(ordinals)
        tier = RANK_ORDER[median_ordinal]

        if dry_run:
            print(f"  DRY RUN: {match_id} -> {tier} ({len(ordinals)}/{len(puuids)} known)")
            updated += 1
            continue

        await conn.execute(
            """
            UPDATE match_state_vector
            SET features = jsonb_set(features, '{average_rank}', $1::jsonb)
            WHERE match_id = $2
            """,
            json.dumps(tier),
            match_id,
        )
        updated += 1

    await conn.close()
    action = "Would update" if dry_run else "Updated"
    print(f"{action} {updated} matches, skipped {skipped} (insufficient rank data).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill average_rank on existing state vectors",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without making changes",
    )
    parser.add_argument(
        "--min-known",
        type=int,
        default=3,
        help="Minimum known ranks per match to compute average (default: 3)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.min_known, args.dry_run))


if __name__ == "__main__":
    main()
