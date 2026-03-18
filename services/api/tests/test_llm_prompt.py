"""Tests for LLM prompt construction (pipeline step 7)."""

from __future__ import annotations

from app.services.action_aggregation import ActionAggregate, AggregateRow, GroupKey
from app.services.action_comparison import compare_action_stats
from app.services.llm_prompt import build_system_prompt, build_user_prompt


def _make_agg(
    *,
    action_key: str = "3089",
    personal_dw: float = 0.03,
    personal_wpre: float = 0.50,
    personal_count: int = 60,
    pop_dw: float = 0.025,
    pop_count: int = 500,
    insufficient: bool = False,
) -> ActionAggregate:
    return ActionAggregate(
        group_key=GroupKey(
            champion_id="157",
            rank_tier="GOLD",
            action_type="ITEM_PURCHASE",
            action_key=action_key,
            opponent_damage_bucket="mixed",
        ),
        personal_stats=AggregateRow(
            count=personal_count,
            mean_delta_w=personal_dw,
            mean_pre_win_prob=personal_wpre,
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


def _build_comparison_dict() -> dict:
    """Build a ComparisonResult dict from test aggregates."""
    aggregates = [
        _make_agg(action_key="3089", personal_dw=0.03),
        _make_agg(action_key="3031", personal_dw=-0.01, personal_count=70),
    ]
    item_names = {"3089": "Rabadon's Deathcap", "3031": "Infinity Edge"}
    comparison = compare_action_stats(aggregates, item_names=item_names)
    assert comparison is not None
    return comparison.to_dict()


class TestBuildSystemPrompt:
    def test_contains_json_schema(self) -> None:
        prompt = build_system_prompt()
        assert "recommendations" in prompt
        assert "overall_assessment" in prompt

    def test_contains_coaching_instructions(self) -> None:
        prompt = build_system_prompt()
        assert "League of Legends" in prompt
        assert "ΔW" in prompt or "delta" in prompt.lower()

    def test_instructs_json_response(self) -> None:
        prompt = build_system_prompt()
        assert "JSON" in prompt


class TestBuildUserPrompt:
    def test_contains_champion_and_rank(self) -> None:
        comp = _build_comparison_dict()
        prompt = build_user_prompt(comp, "Yasuo", "GOLD")
        assert "Yasuo" in prompt
        assert "GOLD" in prompt

    def test_contains_delta_w_values(self) -> None:
        comp = _build_comparison_dict()
        prompt = build_user_prompt(comp, "Yasuo", "GOLD")
        # Should contain formatted ΔW values
        assert "ΔW" in prompt or "delta" in prompt.lower()

    def test_contains_item_names(self) -> None:
        comp = _build_comparison_dict()
        prompt = build_user_prompt(comp, "Yasuo", "GOLD")
        assert "Rabadon's Deathcap" in prompt or "3089" in prompt

    def test_no_puuids_or_summoner_names(self) -> None:
        comp = _build_comparison_dict()
        prompt = build_user_prompt(comp, "Yasuo", "GOLD")
        assert "puuid" not in prompt.lower()
        assert "summoner_name" not in prompt.lower()
        assert "riot_account" not in prompt.lower()

    def test_unknown_rank_when_none(self) -> None:
        comp = _build_comparison_dict()
        prompt = build_user_prompt(comp, "Yasuo", None)
        assert "Unknown" in prompt

    def test_empty_opportunities(self) -> None:
        comp = _build_comparison_dict()
        comp["top_improvement_opportunities"] = []
        prompt = build_user_prompt(comp, "Yasuo", "GOLD")
        assert "No improvement opportunities" in prompt

    def test_empty_bias_flags(self) -> None:
        comp = _build_comparison_dict()
        comp["top_selection_bias_flags"] = []
        prompt = build_user_prompt(comp, "Yasuo", "GOLD")
        assert "No selection bias" in prompt

    def test_empty_groups(self) -> None:
        comp = _build_comparison_dict()
        comp["groups"] = []
        prompt = build_user_prompt(comp, "Yasuo", "GOLD")
        # Should still produce a valid prompt
        assert "Yasuo" in prompt
