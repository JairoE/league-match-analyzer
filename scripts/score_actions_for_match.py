"""Enqueue score_actions_job for a single match.

Scores all actions for the given Riot match ID (game_id) using the
win probability model and persists ΔW fields on match_action rows.

Requires:
- ARQ worker running (make worker-dev)
- WIN_PROB_MODEL_PATH configured so the worker can load the model

Usage:
    python scripts/score_actions_for_match.py --match-id NA1_1234567890
"""

from __future__ import annotations

import argparse
import asyncio
import os

from arq.connections import RedisSettings, create_pool


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SCORE_ACTIONS_JOB_VERSION = os.getenv("SCORE_ACTIONS_JOB_VERSION", "v0")

async def _run(match_id: str) -> None:
    """Enqueue score_actions_job for the given match_id."""
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    pool = await create_pool(redis_settings)
    try:
        job_id = f"score-actions:{SCORE_ACTIONS_JOB_VERSION}:{match_id}"
        await pool.enqueue_job(
            "score_actions_job",
            match_id,
            _job_id=job_id,
        )
        print(f"Enqueued score_actions_job for {match_id} (job_id={job_id})")
        print("Job will be processed by the ARQ worker (make worker-dev).")
    finally:
        await pool.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enqueue score_actions_job for a single match",
    )
    parser.add_argument(
        "--match-id",
        type=str,
        required=True,
        help="Riot match ID (e.g. NA1_1234567890)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.match_id))


if __name__ == "__main__":
    main()

