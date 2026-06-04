"""Seed the RAG corpus by running LLM analysis for multiple accounts + champions.

Calls the full llm_analysis_job pipeline (steps 5→8 + embedding) for each
RIOT_ID:CHAMPION_ID pair. Use this to build the few-shot corpus before RAG
meaningfully activates (~5+ records per champion, ~50 per champion/rank bucket).

Usage:
    # Single pair
    python scripts/seed_rag_corpus.py --entry "name#NA1:157"

    # Multiple pairs
    python scripts/seed_rag_corpus.py --entry "name#NA1:157" --entry "other#NA1:238"

    # From file (one RIOT_ID:CHAMPION_ID per line, # lines are comments)
    python scripts/seed_rag_corpus.py --from-file seeding_list.txt

    # Dry-run (shows which accounts would be processed, no LLM calls)
    python scripts/seed_rag_corpus.py --from-file seeding_list.txt --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_api_root = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(_api_root))

load_dotenv(_api_root / ".env")


@dataclass
class SeedEntry:
    riot_id: str
    champion_id: str
    rank_tier: str | None = None


@dataclass
class SeedResult:
    riot_id: str
    champion_id: str
    status: str
    detail: str = ""
    analysis_id: str | None = None
    champion_name: str | None = None
    recommendations_count: int = 0
    token_input: int = 0
    token_output: int = 0


def _parse_entries(raw: list[str]) -> list[SeedEntry]:
    """Parse RIOT_ID:CHAMPION_ID[:RANK_TIER] entries."""
    entries: list[SeedEntry] = []
    for item in raw:
        parts = item.strip().split(":")
        if len(parts) < 2:
            print(f"  SKIP malformed entry (expected RIOT_ID:CHAMPION_ID): {item!r}")
            continue
        riot_id = ":".join(parts[:-1]) if len(parts) == 3 else parts[0]
        champion_id = parts[-1] if len(parts) == 2 else parts[1]
        rank_tier = parts[2] if len(parts) == 3 else None
        entries.append(SeedEntry(riot_id=riot_id.strip(), champion_id=champion_id.strip(), rank_tier=rank_tier))
    return entries


def _load_from_file(path: str) -> list[SeedEntry]:
    """Load entries from a text file (one RIOT_ID:CHAMPION_ID per line)."""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)
    lines = [line.strip() for line in p.read_text().splitlines()]
    raw = [line for line in lines if line and not line.startswith("#")]
    return _parse_entries(raw)


async def _resolve_account_id(session: Any, riot_id: str) -> str | None:
    from sqlmodel import select
    from app.models.riot_account import RiotAccount

    result = await session.execute(
        select(RiotAccount).where(RiotAccount.riot_id == riot_id)
    )
    account = result.scalar_one_or_none()
    return str(account.id) if account else None


async def _run_entry(entry: SeedEntry, dry_run: bool) -> SeedResult:
    from app.db.session import async_session_factory
    from app.jobs.llm_analysis import llm_analysis_job

    async with async_session_factory() as session:
        account_id = await _resolve_account_id(session, entry.riot_id)

    if account_id is None:
        return SeedResult(
            riot_id=entry.riot_id,
            champion_id=entry.champion_id,
            status="skipped",
            detail=f"No riot_account in DB for {entry.riot_id!r} — search the account first via the API",
        )

    if dry_run:
        return SeedResult(
            riot_id=entry.riot_id,
            champion_id=entry.champion_id,
            status="dry_run",
            detail=f"account_id={account_id}",
        )

    try:
        result = await llm_analysis_job(
            {},  # ARQ ctx is unused in this job
            riot_account_id=account_id,
            champion=entry.champion_id,
            rank_tier=entry.rank_tier,
        )
    except Exception as exc:
        return SeedResult(
            riot_id=entry.riot_id,
            champion_id=entry.champion_id,
            status="error",
            detail=str(exc),
        )

    return SeedResult(
        riot_id=entry.riot_id,
        champion_id=entry.champion_id,
        status=result.get("status", "unknown"),
        analysis_id=result.get("analysis_id"),
        champion_name=result.get("champion_name"),
        recommendations_count=result.get("recommendations_count", 0),
        token_input=result.get("token_input", 0),
        token_output=result.get("token_output", 0),
        detail=result.get("reason", ""),
    )


async def _run(entries: list[SeedEntry], dry_run: bool) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    if not dry_run and not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set in services/api/.env")
        sys.exit(1)

    if not entries:
        print("No entries to process. Use --entry or --from-file.")
        sys.exit(1)

    print(f"Seeding RAG corpus — {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}")
    if dry_run:
        print("(dry run — no LLM calls, no DB writes)\n")
    else:
        print(f"  model:     {settings.llm_model_name}")
        print(f"  embedding: {settings.rag_embedding_model}")
        print(f"  rag_enabled: {settings.rag_enabled}\n")

    results: list[SeedResult] = []

    for i, entry in enumerate(entries, 1):
        label = f"[{i}/{len(entries)}] {entry.riot_id} champion={entry.champion_id}"
        if entry.rank_tier:
            label += f" rank={entry.rank_tier}"
        print(f"{label} ...")

        result = await _run_entry(entry, dry_run)
        results.append(result)

        if result.status in ("ok", "dry_run"):
            suffix = f"analysis_id={result.analysis_id}" if result.analysis_id else "dry_run"
            recs = f" recs={result.recommendations_count}" if result.analysis_id else ""
            tokens = f" tokens={result.token_input}+{result.token_output}" if result.token_input else ""
            print(f"  OK  {result.champion_name or entry.champion_id}{recs}{tokens} [{suffix}]")
        elif result.status == "parse_error":
            print(f"  WARN parse_error — analysis persisted but recommendations may be empty. analysis_id={result.analysis_id}")
        elif result.status in ("no_data", "no_comparison", "skipped"):
            print(f"  SKIP {result.status}: {result.detail}")
        else:
            print(f"  FAIL {result.status}: {result.detail}")

    # Summary
    print()
    ok = [r for r in results if r.status in ("ok", "parse_error")]
    skipped = [r for r in results if r.status in ("no_data", "no_comparison", "skipped", "dry_run")]
    failed = [r for r in results if r.status in ("error", "llm_error")]
    total_tokens = sum(r.token_input + r.token_output for r in ok)

    print("=" * 56)
    print(f"  Processed : {len(entries)}")
    print(f"  Succeeded : {len(ok)}")
    print(f"  Skipped   : {len(skipped)}")
    print(f"  Failed    : {len(failed)}")
    if total_tokens:
        print(f"  Tokens    : {total_tokens:,} (input + output)")
    print("=" * 56)

    if ok:
        print("\nTo check corpus size by champion:")
        print("  docker exec league_postgres psql -U league -d league -c \\")
        print('    "SELECT champion_name, COUNT(*) FROM llm_analysis WHERE embedding IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"')

    if skipped:
        print(f"\nNote: {len(skipped)} entr{'y' if len(skipped) == 1 else 'ies'} skipped — account may not be in DB yet.")
        print("  Search the account via the frontend or API first to populate riot_account.")

    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the RAG corpus by running LLM analysis for multiple accounts",
    )
    parser.add_argument(
        "--entry",
        action="append",
        default=[],
        metavar="RIOT_ID:CHAMPION_ID",
        help="Account+champion pair to analyse (can be repeated). "
             "Format: RIOT_ID:CHAMPION_ID or RIOT_ID:CHAMPION_ID:RANK_TIER",
    )
    parser.add_argument(
        "--from-file",
        metavar="FILE",
        help="Text file with one RIOT_ID:CHAMPION_ID per line (# lines are comments)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve accounts and print plan without calling the LLM or storing data",
    )
    args = parser.parse_args()

    entries: list[SeedEntry] = []
    if args.from_file:
        entries.extend(_load_from_file(args.from_file))
    if args.entry:
        entries.extend(_parse_entries(args.entry))

    asyncio.run(_run(entries, args.dry_run))


if __name__ == "__main__":
    main()
