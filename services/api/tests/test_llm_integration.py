"""Integration test that sends a real prompt to OpenAI and validates the response.

Skipped automatically when OPENAI_API_KEY is not set.
Run with: OPENAI_API_KEY=sk-... pytest services/api/tests/test_llm_integration.py -s -v
"""

from __future__ import annotations

import os

import pytest

from app.services.action_aggregation import ActionAggregate, AggregateRow, GroupKey
from app.services.action_comparison import compare_action_stats
from app.services.llm_client import OpenAIClient
from app.services.llm_prompt import build_system_prompt, build_user_prompt
from app.services.llm_response_schema import LLMAnalysisResponse

_SEPARATOR = "─" * 60

_SKIP_REASON = "OPENAI_API_KEY not set — set it to run real LLM integration tests"


def _make_agg(
    *,
    champion_id: str = "202",
    rank_tier: str = "SILVER",
    action_type: str = "ITEM_PURCHASE",
    action_key: str,
    personal_dw: float,
    personal_count: int = 60,
    pop_dw: float = 0.025,
    pop_count: int = 500,
    pre_win_prob: float = 0.50,
    insufficient: bool = False,
) -> ActionAggregate:
    return ActionAggregate(
        group_key=GroupKey(
            champion_id=champion_id,
            rank_tier=rank_tier,
            action_type=action_type,
            action_key=action_key,
            opponent_damage_bucket="mixed",
        ),
        personal_stats=AggregateRow(
            count=personal_count,
            mean_delta_w=personal_dw,
            mean_pre_win_prob=pre_win_prob,
            stddev_delta_w=0.01,
        ),
        population_stats=AggregateRow(
            count=pop_count,
            mean_delta_w=pop_dw,
            mean_pre_win_prob=0.51,
            stddev_delta_w=0.01,
        ),
        insufficient_personal_sample=insufficient,
    )


def _build_realistic_aggregates() -> list[ActionAggregate]:
    """Build Jhin SILVER aggregates that produce meaningful comparison output."""
    return [
        # Core ADC item — summoner performs well
        _make_agg(action_key="3031", personal_dw=0.032, personal_count=90,
                  pop_dw=0.028),
        # Underperforming pick — summoner buys often but low impact
        _make_agg(action_key="3094", personal_dw=-0.008, personal_count=75,
                  pop_dw=0.018),
        # Win-more item — high pre-win-prob, negligible delta_w
        _make_agg(action_key="3046", personal_dw=0.003, personal_count=50,
                  pop_dw=0.012, pre_win_prob=0.61),
        # Rarely built situational item
        _make_agg(action_key="3036", personal_dw=0.025, personal_count=12,
                  pop_dw=0.026, insufficient=True),
    ]


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason=_SKIP_REASON)
class TestRealLLMResponse:
    """Integration tests that call OpenAI for real."""

    async def test_prompt_produces_valid_schema_response(self) -> None:
        """Build real prompts from synthetic data, call OpenAI, validate response."""
        api_key = os.environ["OPENAI_API_KEY"]

        # -- Step 5 substitute: synthetic aggregates --
        aggregates = _build_realistic_aggregates()
        item_names = {
            "3031": "Infinity Edge",
            "3094": "Rapid Firecannon",
            "3046": "Phantom Dancer",
            "3036": "Lord Dominik's Regards",
        }

        # -- Step 6: compare --
        comparison = compare_action_stats(aggregates, item_names=item_names)
        assert comparison is not None, "compare_action_stats returned None"
        comparison_dict = comparison.to_dict()

        # -- Step 7: build prompts --
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(comparison_dict, "Jhin", "SILVER")

        print(f"\n{_SEPARATOR}")
        print("REAL LLM INTEGRATION TEST")
        print(_SEPARATOR)
        print(f"\n  System prompt ({len(system_prompt)} chars):")
        print(f"    {system_prompt[:120]}...")
        print(f"\n  User prompt ({len(user_prompt)} chars):")
        for line in user_prompt.split("\n")[:15]:
            print(f"    {line}")
        print("    ...")

        # -- Step 7: call OpenAI --
        client = OpenAIClient(api_key=api_key, model="gpt-4o-mini")
        response = await client.complete(system_prompt, user_prompt)

        print(f"\n  Model: {response.model_name}")
        print(f"  Tokens: {response.token_count_input} in / {response.token_count_output} out")
        print(f"\n  Raw response:\n{response.content}")

        # -- Validate: response parses against our Pydantic schema --
        parsed = LLMAnalysisResponse.model_validate_json(response.content)

        print(f"\n  Parsed successfully: {len(parsed.recommendations)} recommendation(s)")
        for rec in parsed.recommendations:
            print(f"    #{rec.rank} [{rec.category}] {rec.title}")
            print(f"       {rec.current_choice} → {rec.recommended_choice} "
                  f"(gap={rec.delta_w_gap:+.4f})")
            print(f"       {rec.explanation}")
        print(f"\n  Selection bias summary: {parsed.selection_bias_summary}")
        print(f"  Overall assessment: {parsed.overall_assessment}")
        print(_SEPARATOR)

        # Structural assertions
        assert 1 <= len(parsed.recommendations) <= 3
        for rec in parsed.recommendations:
            assert rec.category in ("item_purchase", "objective_kill", "selection_bias")
            assert rec.title
            assert rec.explanation
        assert parsed.overall_assessment
