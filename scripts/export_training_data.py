"""Export training data for the V1 win probability model.

Joins match_state_vector features with match outcomes (from match.game_info)
and writes a CSV. Each row is one game state observation with a binary win label.

Per the thesis, we sample one random state per 5-min interval per match to
reduce overfitting from correlated successive states.

Usage:
    python scripts/export_training_data.py --output data/training.csv
    python scripts/export_training_data.py --output data/training.csv --sample-interval 5
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import sys
from pathlib import Path

import asyncpg


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://league:league@localhost:5432/league",
)

PLAYER_FEATURE_KEYS = [
    "position_x",
    "position_y",
    "level",
    "total_gold",
    "damage_dealt",
    "damage_taken",
    "kills",
    "deaths",
    "assists",
]

TEAM_FEATURE_KEYS = [
    "voidgrubs",
    "dragons",
    "barons",
    "turrets",
    "inhibitors",
]

PARTICIPANT_IDS = list(range(1, 11))
TEAM_IDS = [100, 200]


def _build_csv_header() -> list[str]:
    """Build deterministic column ordering for the CSV."""
    cols = ["match_id", "game_id", "minute", "timestamp_ms"]
    for pid in PARTICIPANT_IDS:
        for key in PLAYER_FEATURE_KEYS:
            cols.append(f"p{pid}_{key}")
    for tid in TEAM_IDS:
        for key in TEAM_FEATURE_KEYS:
            cols.append(f"t{tid}_{key}")
    cols.append("average_rank")
    cols.append("win")
    return cols


def _extract_team_wins(game_info: dict) -> dict[int, bool]:
    """Extract win outcome per team from game_info payload.

    Args:
        game_info: Riot match detail payload (match.game_info).

    Returns:
        Dict mapping team_id (100/200) to win bool.
    """
    info = game_info.get("info") or {}
    teams = info.get("teams") or []
    team_wins: dict[int, bool] = {}
    for team in teams:
        team_id = team.get("teamId")
        won = team.get("win", False)
        if team_id is not None:
            team_wins[team_id] = won
    return team_wins


def _sample_minutes(
    minutes: list[int],
    interval: int,
) -> list[int]:
    """Sample one minute per interval window (thesis anti-overfitting strategy).

    Args:
        minutes: Sorted list of available minutes.
        interval: Window size in minutes (default 5).

    Returns:
        Sampled minute indices.
    """
    if not minutes or interval <= 0:
        return list(minutes)

    max_minute = max(minutes)
    sampled: list[int] = []

    window_start = 0
    while window_start <= max_minute:
        window_end = window_start + interval
        candidates = [m for m in minutes if window_start <= m < window_end]
        if candidates:
            sampled.append(random.choice(candidates))
        window_start = window_end

    return sampled


async def _export(output_path: Path, sample_interval: int) -> None:
    """Query DB and write training CSV."""
    conn = await asyncpg.connect(DATABASE_URL)
    print("Connected to database. Querying state vectors + match outcomes...")

    try:
        rows = await conn.fetch("""
            SELECT
                sv.match_id,
                sv.game_id,
                sv.minute,
                sv.timestamp_ms,
                sv.features,
                m.game_info
            FROM match_state_vector sv
            JOIN match m ON m.id = sv.match_id
            WHERE m.game_info IS NOT NULL
            ORDER BY sv.game_id, sv.minute
        """)
    finally:
        await conn.close()

    if not rows:
        print("No state vectors found. Run extract_match_timeline_job first.")
        sys.exit(1)

    print(f"Fetched {len(rows)} state vector rows across matches.")

    # Group rows by game_id for per-match sampling
    by_game: dict[str, list[asyncpg.Record]] = {}
    for row in rows:
        by_game.setdefault(row["game_id"], []).append(row)

    header = _build_csv_header()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped_no_outcome = 0

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()

        for game_id, game_rows in by_game.items():
            game_info = game_rows[0]["game_info"]
            if not game_info:
                skipped_no_outcome += 1
                continue

            team_wins = _extract_team_wins(game_info)
            if not team_wins:
                skipped_no_outcome += 1
                continue

            # Team 100 win label (model predicts from blue-side perspective)
            win = 1 if team_wins.get(100, False) else 0

            all_minutes = sorted(r["minute"] for r in game_rows)
            sampled_minutes = set(_sample_minutes(all_minutes, sample_interval))

            minute_index = {r["minute"]: r for r in game_rows}

            for minute in sorted(sampled_minutes):
                row = minute_index.get(minute)
                if row is None:
                    continue

                features = row["features"] or {}
                csv_row: dict = {
                    "match_id": str(row["match_id"]),
                    "game_id": game_id,
                    "minute": minute,
                    "timestamp_ms": row["timestamp_ms"],
                }

                for pid in PARTICIPANT_IDS:
                    prefix = f"p{pid}"
                    for key in PLAYER_FEATURE_KEYS:
                        csv_row[f"{prefix}_{key}"] = features.get(f"{prefix}_{key}", 0)

                for tid in TEAM_IDS:
                    prefix = f"t{tid}"
                    for key in TEAM_FEATURE_KEYS:
                        csv_row[f"{prefix}_{key}"] = features.get(f"{prefix}_{key}", 0)

                csv_row["average_rank"] = features.get("average_rank", "")
                csv_row["win"] = win

                writer.writerow(csv_row)
                written += 1

    print(f"Wrote {written} rows from {len(by_game)} matches to {output_path}")
    if skipped_no_outcome:
        print(f"Skipped {skipped_no_outcome} matches with missing outcome data.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export training data for win probability model")
    parser.add_argument(
        "--output",
        type=str,
        default="data/training.csv",
        help="Output CSV path (default: data/training.csv)",
    )
    parser.add_argument(
        "--sample-interval",
        type=int,
        default=5,
        help="Sample one state per N-minute interval to reduce correlation (default: 5)",
    )
    args = parser.parse_args()

    random.seed(42)
    asyncio.run(_export(Path(args.output), args.sample_interval))


if __name__ == "__main__":
    main()
