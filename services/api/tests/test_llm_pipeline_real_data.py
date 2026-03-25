"""Integration test that runs LLM pipeline step 7 using a pre-seeded fixture.

The fixture (fixtures/damanjr_comparison.json) contains the real comparison
output for damanjr#NA1, captured once via seed_llm_fixture.py.  No DB or
Riot API access is needed at test time.

Skip conditions:
  - OPENAI_API_KEY not set
  - fixtures/damanjr_comparison.json does not exist

Run with:
  OPENAI_API_KEY=sk-... pytest services/api/tests/test_llm_pipeline_real_data.py -s -v

To regenerate the fixture:
  DATABASE_URL=postgresql+asyncpg://... python services/api/tests/seed_llm_fixture.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.llm_client import OpenAIClient
from app.services.llm_prompt import build_system_prompt, build_user_prompt
from app.services.llm_response_schema import LLMAnalysisResponse

_SEPARATOR = "─" * 60

# _FIXTURE_PATH = Path(__file__).parent / "fixtures" / "damanjr_comparison.json"
_RIOT_ID = os.environ.get("RIOT_ID", "damanjr#NA1")
_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / f"{_RIOT_ID.replace('#', '_')}_comparison.json"
)
_SKIP_REASON = (
    "OPENAI_API_KEY not set or fixtures/damanjr_comparison.json missing — "
    "set the key and run seed_llm_fixture.py to generate the fixture"
)


def _fixture_exists() -> bool:
    return _FIXTURE_PATH.exists()


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY") or not _fixture_exists(),
    reason=_SKIP_REASON,
)
class TestRealDataLLMPipeline:
    """Runs step 7 of the LLM pipeline using real data captured from damanjr#NA1."""

    async def test_full_pipeline_from_fixture(self) -> None:
        """Load real comparison data from fixture, call OpenAI, validate response."""
        api_key = os.environ["OPENAI_API_KEY"]

        fixture = json.loads(_FIXTURE_PATH.read_text())
        champion_name: str = fixture["champion_name"]
        rank_tier: str | None = fixture.get("rank_tier")
        comparison_dict: dict = fixture["comparison"]

        # Step 7: build prompts
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(comparison_dict, champion_name, rank_tier)

        print(f"\n{_SEPARATOR}")
        print("REAL-DATA LLM PIPELINE INTEGRATION TEST")
        print(_SEPARATOR)
        print(f"\n  Account  : {fixture['riot_id']}")
        print(f"  Champion : {champion_name} (id={fixture.get('champion_id')})")
        print(f"  Rank     : {rank_tier}")
        print(f"\n  System prompt ({len(system_prompt)} chars):")
        print(f"    {system_prompt[:120]}...")
        print(f"\n  User prompt ({len(user_prompt)} chars):")
        for line in user_prompt.split("\n")[:15]:
            print(f"    {line}")
        print("    ...")

        # Step 7: call OpenAI
        client = OpenAIClient(api_key=api_key, model="gpt-4o-mini")
        response = await client.complete(system_prompt, user_prompt)

        print(f"\n  Model  : {response.model_name}")
        print(f"  Tokens : {response.token_count_input} in / {response.token_count_output} out")
        print(f"\n  Raw response:\n{response.content}")

        # Validate against schema
        parsed = LLMAnalysisResponse.model_validate_json(response.content)

        print(f"\n  Parsed successfully: {len(parsed.recommendations)} recommendation(s)")
        for rec in parsed.recommendations:
            print(f"    #{rec.rank} [{rec.category}] {rec.title}")
            print(
                f"       {rec.current_choice} → {rec.recommended_choice} "
                f"(gap={rec.delta_w_gap:+.4f})"
            )
            print(f"       {rec.explanation}")
        print(f"\n  Selection bias summary: {parsed.selection_bias_summary}")
        print(f"  Overall assessment    : {parsed.overall_assessment}")
        print(_SEPARATOR)

        # Structural assertions
        assert 1 <= len(parsed.recommendations) <= 3
        for rec in parsed.recommendations:
            assert rec.category in ("item_purchase", "objective_kill", "selection_bias")
            assert rec.title
            assert rec.explanation
        assert parsed.overall_assessment
