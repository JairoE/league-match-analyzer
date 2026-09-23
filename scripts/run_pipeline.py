"""Bring one account fully up to date: fetch → details → extract → score → AI Coach.

Idempotent: only missing work is enqueued, and it reuses the deterministic ARQ
job ids the API and worker use, so anything a background run already finished
or has in flight is skipped. Requires Postgres, Redis, and the ARQ worker to be
running (``make up`` starts all of them and then calls this script).

Usage:
    python scripts/run_pipeline.py --riot-id "name#NA1"
    python scripts/run_pipeline.py --riot-id "name#NA1" --count 40 --skip-llm
    python scripts/run_pipeline.py --riot-id "name#NA1" --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

_api_root = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(_api_root))

load_dotenv(_api_root / ".env")


def _print_report(report: object) -> None:
    from app.services.account_pipeline import PipelineReport

    assert isinstance(report, PipelineReport)
    print()
    print("=" * 64)
    print(f"  Account     : {report.riot_id} ({report.riot_account_id or 'not in DB'})")
    if report.counts_after or report.counts_before:
        counts = report.counts_after or report.counts_before
        assert counts is not None
        print(
            f"  Matches     : {counts.linked} linked, {counts.with_details} with details, "
            f"{counts.extracted} extracted, {counts.scored} scored"
        )
    print(
        f"  Enqueued    : {report.enqueued_details} detail, {report.enqueued_extraction} "
        f"extraction, {report.enqueued_scoring} scoring"
    )
    print(f"  Processing  : {report.drain_outcome}")
    if report.llm_skipped_reason:
        print(f"  AI Coach    : skipped ({report.llm_skipped_reason})")
    elif not report.champions:
        print("  AI Coach    : no eligible champions (need scored matches)")
    else:
        print("  AI Coach    :")
        for outcome in report.champions:
            tokens = (
                f" tokens={outcome.token_input}+{outcome.token_output}"
                if outcome.token_input
                else ""
            )
            detail = f" ({outcome.detail})" if outcome.detail else ""
            print(f"    {outcome.champion_name:<14} {outcome.status}{detail}{tokens}")
        total = sum(o.token_input + o.token_output for o in report.champions)
        if total:
            print(f"  Tokens      : {total:,}")
    if report.missing_embeddings:
        print(
            f"  Embeddings  : {report.missing_embeddings} analyses lack one "
            "— run `make backfill-rag-embeddings`"
        )
    for warning in report.warnings:
        print(f"  WARN        : {warning}")
    print("=" * 64)


FAILED_CHAMPION_STATUSES = {"error", "llm_error", "timeout"}


async def _run(args: argparse.Namespace) -> int:
    from app.services.account_pipeline import PipelineConfigError, run_account_pipeline
    from app.services.riot_api_client import RiotRequestError

    try:
        report = await run_account_pipeline(
            args.riot_id,
            count=args.count,
            timeout_s=args.timeout,
            skip_llm=args.skip_llm,
            dry_run=args.dry_run,
            emit=lambda message: print(message, flush=True),
        )
    except PipelineConfigError as exc:
        print(f"ERROR: {exc}")
        return 1
    except RiotRequestError as exc:
        print(f"ERROR: Riot API request failed ({exc.status}): {exc.message}")
        return 1

    _print_report(report)
    failed = [o for o in report.champions if o.status in FAILED_CHAMPION_STATUSES]
    return 1 if failed or report.drain_outcome == "timeout" else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full ingest → score → AI Coach pipeline for one account",
    )
    parser.add_argument("--riot-id", required=True, help='Riot ID, e.g. "name#NA1"')
    parser.add_argument(
        "--count", type=int, default=20, help="Latest match ids to fetch (default: 20)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="Max seconds to wait for each stage (default: 900)",
    )
    parser.add_argument("--skip-llm", action="store_true", help="Skip AI Coach analysis")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report gaps and planned work without calling Riot or enqueueing jobs",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
