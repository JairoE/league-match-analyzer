"""Run LLM analysis for a riot account's champion (pipeline steps 5→8 debug).

Calls aggregation (step 5), comparison (step 6), prompt construction (step 7),
and optionally calls the LLM and persists results (step 8).

Usage:
    python scripts/llm_analysis_debug.py --riot-id "name#NA1" --champion 157
    python scripts/llm_analysis_debug.py --riot-account-id <UUID> --champion 157 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

_api_root = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(_api_root))

# Load env before importing app (database_url, openai_api_key, etc.)
load_dotenv(_api_root / ".env")


_OBJECTIVE_LABELS: dict[str, str] = {
    "DRAGON": "Dragon",
    "RIFTHERALD": "Rift Herald",
    "BARON_NASHOR": "Baron Nashor",
}


async def _load_item_name_map() -> dict[str, str]:
    """Fetch item_id → name mapping from Data Dragon."""
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


async def _run(
    riot_account_id: str | None,
    riot_id: str | None,
    champion: str,
    rank_tier: str | None,
    dry_run: bool,
) -> None:
    from uuid import UUID

    from sqlmodel import select

    from app.core.config import get_settings
    from app.db.session import async_session_factory
    from app.models.champion import Champion
    from app.models.llm_analysis import LLMAnalysis
    from app.models.riot_account import RiotAccount
    from app.services.action_aggregation import aggregate_action_stats_for_player
    from app.services.action_comparison import compare_action_stats
    from app.services.llm_client import OpenAIClient
    from app.services.llm_prompt import build_system_prompt, build_user_prompt
    from app.services.llm_response_schema import LLMAnalysisResponse

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

        # Step 5: Aggregate
        print("Running step 5 (aggregate)...")
        aggregates = await aggregate_action_stats_for_player(
            session,
            UUID(account_id),
            champion=champion,
            rank_tier=rank_tier,
        )

        if not aggregates:
            print("No action aggregates (no scored actions for this account/filters).")
            return

        print(f"  {len(aggregates)} aggregate rows\n")

        # Resolve champion name
        try:
            champ_id_int = int(champion)
            champ_result = await session.execute(
                select(Champion).where(Champion.champ_id == champ_id_int)
            )
            champ = champ_result.scalar_one_or_none()
            champion_name = champ.name if champ else champion
        except (ValueError, TypeError):
            champion_name = champion

    # Load item names
    item_names = await _load_item_name_map()

    # Step 6: Compare
    print("Running step 6 (compare)...")
    comparison = compare_action_stats(
        aggregates,
        item_names=item_names,
        objective_names=_OBJECTIVE_LABELS,
    )

    if comparison is None:
        print("No comparison results (all actions had no effective ΔW).")
        return

    comparison_dict = comparison.to_dict()
    print(f"  {len(comparison.groups)} comparison groups\n")

    # Determine effective rank
    effective_rank = rank_tier
    if effective_rank is None and comparison.groups:
        effective_rank = comparison.groups[0].rank_tier

    # Step 7: Build prompt
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(comparison_dict, champion_name, effective_rank)

    if dry_run:
        print("=== SYSTEM PROMPT ===")
        print(system_prompt)
        print()
        print("=== USER PROMPT ===")
        print(user_prompt)
        print()
        print("(dry run — LLM not called)")
        return

    # Call LLM
    settings = get_settings()
    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY not set in .env")
        return

    print("Running step 7 (LLM call)...")
    client = OpenAIClient(
        api_key=settings.openai_api_key,
        model=settings.llm_model_name,
    )

    try:
        llm_response = await client.complete(system_prompt, user_prompt)
    except Exception as exc:
        print(f"LLM call failed: {exc}")
        return

    print(f"  Model: {llm_response.model_name}")
    print(f"  Tokens: {llm_response.token_count_input} in / {llm_response.token_count_output} out")
    print()

    print("=== RAW LLM RESPONSE ===")
    try:
        formatted = json.dumps(json.loads(llm_response.content), indent=2)
        print(formatted)
    except (json.JSONDecodeError, TypeError):
        print(llm_response.content)
    print()

    # Parse response
    recommendations_list: list[dict[str, Any]] = []
    output_payload: dict[str, Any] = {}

    try:
        parsed = LLMAnalysisResponse.model_validate_json(llm_response.content)
        recommendations_list = [r.model_dump() for r in parsed.recommendations]
        output_payload = parsed.model_dump()
        print("=== PARSED RECOMMENDATIONS ===")
        for rec in parsed.recommendations:
            print(f"  #{rec.rank} [{rec.category}] {rec.title}")
            print(f"     {rec.current_choice} → {rec.recommended_choice} (gap: {rec.delta_w_gap:+.4f})")
            print(f"     {rec.explanation}")
            print()
        if parsed.overall_assessment:
            print(f"Overall: {parsed.overall_assessment}")
            print()
    except Exception as exc:
        print(f"Parse error: {exc}")
        try:
            output_payload = json.loads(llm_response.content)
        except (json.JSONDecodeError, TypeError):
            output_payload = {"raw": llm_response.content}

    # Step 8: Persist
    print("Running step 8 (persist)...")
    async with async_session_factory() as session:
        from app.jobs.llm_analysis import _get_scored_match_ids

        match_ids = await _get_scored_match_ids(
            session, UUID(account_id), champion, rank_tier
        )

        analysis = LLMAnalysis(
            riot_account_id=UUID(account_id),
            champion_name=champion_name,
            rank_tier=effective_rank,
            match_ids=match_ids,
            schema_version=comparison.schema_version,
            input_payload=comparison_dict,
            output_payload=output_payload,
            recommendations=recommendations_list,
            model_name=llm_response.model_name,
            token_count_input=llm_response.token_count_input,
            token_count_output=llm_response.token_count_output,
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)
        print(f"  Persisted LLMAnalysis id={analysis.id}")
        print(f"  Match count: {len(match_ids)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run LLM analysis for a riot account's champion (debug)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--riot-account-id", type=str, help="Riot account UUID")
    group.add_argument(
        "--riot-id",
        type=str,
        help='Riot ID (e.g. "name#NA1") to resolve to account',
    )
    parser.add_argument(
        "--champion", type=str, required=True, help="Champion ID (e.g. 157)"
    )
    parser.add_argument("--rank-tier", type=str, default=None, help="Filter by rank tier")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show prompt without calling LLM",
    )
    args = parser.parse_args()
    asyncio.run(
        _run(
            args.riot_account_id,
            args.riot_id,
            args.champion,
            args.rank_tier,
            args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
