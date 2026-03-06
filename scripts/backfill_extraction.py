"""Backfill timeline extraction for existing matches.

Finds matches that have game_info (match detail payload) but no rows in
match_state_vector, then enqueues extract_match_timeline_job for each via ARQ.

Requires the ARQ worker to be running (make worker-dev) to process the jobs.

Usage:
    python scripts/backfill_extraction.py
    python scripts/backfill_extraction.py --batch-size 100
    python scripts/backfill_extraction.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os

import asyncpg
from arq.connections import ArqRedis, RedisSettings, create_pool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://league:league@localhost:5432/league",
)

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

BATCH_SIZE_DEFAULT = 50


async def _find_missing(conn: asyncpg.Connection) -> list[str]:
    """Find matches with game_info but no state vectors."""
    rows = await conn.fetch("""
        SELECT m.game_id
        FROM match m
        WHERE m.game_info IS NOT NULL
          AND m.game_id NOT IN (
              SELECT DISTINCT game_id FROM match_state_vector
          )
        ORDER BY m.game_id
    """)
    return [row["game_id"] for row in rows]


async def _enqueue_batch(
    pool: ArqRedis,
    batch: list[str],
) -> int:
    """Enqueue extraction jobs for a batch of match IDs.

    Args:
        pool: ARQ Redis pool.
        batch: Match IDs to enqueue.

    Returns:
        Number of jobs successfully enqueued.
    """
    enqueued = 0
    for match_id in batch:
        job_id = f"timeline-extract:{match_id}"
        try:
            await pool.enqueue_job(
                "extract_match_timeline_job",
                match_id,
                _job_id=job_id,
            )
            enqueued += 1
        except Exception as exc:
            print(f"  WARN: failed to enqueue {match_id}: {exc}")
    return enqueued


async def _run(batch_size: int, dry_run: bool) -> None:
    """Main backfill logic."""
    conn = await asyncpg.connect(DATABASE_URL)
    print("Connected to database. Finding matches needing extraction...")

    try:
        missing = await _find_missing(conn)
    finally:
        await conn.close()

    if not missing:
        print("All matches already have state vectors. Nothing to do.")
        return

    print(f"Found {len(missing)} matches needing extraction.")

    if dry_run:
        print("DRY RUN — would enqueue the following match IDs:")
        for mid in missing:
            print(f"  {mid}")
        return

    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    pool = await create_pool(redis_settings)
    print(f"Connected to Redis. Enqueueing in batches of {batch_size}...")

    total_enqueued = 0
    for i in range(0, len(missing), batch_size):
        batch = missing[i : i + batch_size]
        enqueued = await _enqueue_batch(pool, batch)
        total_enqueued += enqueued
        batch_num = i // batch_size + 1
        total_batches = (len(missing) + batch_size - 1) // batch_size
        print(f"  Batch {batch_num}/{total_batches}: enqueued {enqueued}/{len(batch)}")

    await pool.aclose()
    print(f"Done. Enqueued {total_enqueued}/{len(missing)} extraction jobs.")
    print("Jobs will be processed by the ARQ worker (make worker-dev).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill timeline extraction for existing matches",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_DEFAULT,
        help=f"Number of jobs to enqueue per batch (default: {BATCH_SIZE_DEFAULT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matches that would be enqueued without actually enqueueing",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.batch_size, args.dry_run))


if __name__ == "__main__":
    main()
