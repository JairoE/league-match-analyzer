"""Tests for action comparison service (pipeline step 6)."""

from __future__ import annotations

import json

from app.services.action_aggregation import (
    ActionAggregate,
    AggregateRow,
    GroupKey,
)
from app.services.action_comparison import (
    SELECTION_BIAS_W_THRESHOLD,
    compare_action_stats,
)


def _make_agg(
    *,
    champion_id: str = "157",
    rank_tier: str = "GOLD",
    action_type: str = "ITEM_PURCHASE",
    action_key: str = "3089",
    personal_count: int = 60,
    personal_dw: float | None = 0.03,
    personal_wpre: float | None = 0.50,
    pop_count: int = 500,
    pop_dw: float | None = 0.025,
    pop_wpre: float | None = 0.51,
    insufficient: bool = False,
) -> ActionAggregate:
    """Build an ActionAggregate fixture with sensible defaults."""
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
            mean_pre_win_prob=personal_wpre,
            stddev_delta_w=0.01,
        ),
        population_stats=AggregateRow(
            count=pop_count,
            mean_delta_w=pop_dw,
            mean_pre_win_prob=pop_wpre,
            stddev_delta_w=0.01,
        ),
        insufficient_personal_sample=insufficient,
    )


class TestCompareActionStats:
    def test_empty_aggregates_returns_none(self) -> None:
        assert compare_action_stats([]) is None

    def test_single_action_no_gaps(self) -> None:
        aggs = [_make_agg(action_key="3089", personal_dw=0.05)]
        result = compare_action_stats(aggs)
        assert result is not None
        assert len(result.groups) == 1
        group = result.groups[0]
        assert len(group.ranked_actions) == 1
        assert group.ranked_actions[0].rank == 1
        assert group.improvement_gaps == []
        assert result.top_improvement_opportunities == []

    def test_ranks_descending_by_delta_w(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=0.05),
            _make_agg(action_key="3157", personal_dw=0.03),
            _make_agg(action_key="6655", personal_dw=0.08),
        ]
        result = compare_action_stats(aggs)
        assert result is not None
        ranked = result.groups[0].ranked_actions
        assert ranked[0].action_key == "6655"
        assert ranked[0].rank == 1
        assert ranked[1].action_key == "3089"
        assert ranked[1].rank == 2
        assert ranked[2].action_key == "3157"
        assert ranked[2].rank == 3

    def test_population_fallback_when_insufficient(self) -> None:
        aggs = [
            _make_agg(
                action_key="3089",
                personal_count=10,
                personal_dw=0.01,
                pop_dw=0.04,
                insufficient=True,
            ),
        ]
        result = compare_action_stats(aggs)
        assert result is not None
        action = result.groups[0].ranked_actions[0]
        assert action.effective_delta_w == 0.04
        assert action.used_population_fallback is True
        assert action.personal_delta_w == 0.01

    def test_improvement_gap_calculation(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=0.08, personal_count=80),
            _make_agg(action_key="3157", personal_dw=0.03, personal_count=100),
        ]
        result = compare_action_stats(aggs)
        assert result is not None
        group = result.groups[0]
        # Summoner's most-used is 3157 (count=100) but 3089 is rank-1 (ΔW=0.08)
        assert len(group.improvement_gaps) == 1
        gap = group.improvement_gaps[0]
        assert gap.summoner_action.action_key == "3157"
        assert gap.better_alternative.action_key == "3089"
        assert abs(gap.delta_w_gap - 0.05) < 1e-9

    def test_top_3_gaps_across_groups(self) -> None:
        aggs = [
            # Group 1: ITEM_PURCHASE — gap of 0.05
            _make_agg(
                action_type="ITEM_PURCHASE",
                action_key="3089",
                personal_dw=0.08,
                personal_count=50,
            ),
            _make_agg(
                action_type="ITEM_PURCHASE",
                action_key="3157",
                personal_dw=0.03,
                personal_count=90,
            ),
            # Group 2: OBJECTIVE_KILL — gap of 0.10
            _make_agg(
                action_type="OBJECTIVE_KILL",
                action_key="DRAGON",
                personal_dw=0.12,
                personal_count=60,
            ),
            _make_agg(
                action_type="OBJECTIVE_KILL",
                action_key="BARON_NASHOR",
                personal_dw=0.02,
                personal_count=80,
            ),
        ]
        result = compare_action_stats(aggs, top_n_improvement_gaps=3)
        assert result is not None
        top = result.top_improvement_opportunities
        assert len(top) == 2
        # Largest gap first (OBJECTIVE_KILL: 0.12 - 0.02 = 0.10)
        assert abs(top[0].delta_w_gap - 0.10) < 1e-9
        assert abs(top[1].delta_w_gap - 0.05) < 1e-9

    def test_summoner_top_by_count(self) -> None:
        aggs = [
            _make_agg(action_key="A", personal_count=100, personal_dw=0.01),
            _make_agg(action_key="B", personal_count=200, personal_dw=0.02),
            _make_agg(action_key="C", personal_count=50, personal_dw=0.03),
        ]
        result = compare_action_stats(aggs, top_n_summoner_actions=2)
        assert result is not None
        top = result.groups[0].summoner_top_actions
        assert len(top) == 2
        assert top[0].action_key == "B"
        assert top[1].action_key == "A"

    def test_selection_bias_flagged(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=0.08, personal_wpre=0.50),
            _make_agg(action_key="3157", personal_dw=0.02, personal_wpre=0.60),
            _make_agg(action_key="6655", personal_dw=0.05, personal_wpre=0.48),
        ]
        result = compare_action_stats(
            aggs,
            selection_bias_w_threshold=SELECTION_BIAS_W_THRESHOLD,
        )
        assert result is not None
        flags = result.groups[0].selection_bias_flags
        # 3157 has W(x)=0.60 >= 0.55 and ΔW=0.02 < median(0.08, 0.05, 0.02)=0.05
        assert len(flags) == 1
        assert flags[0].action_key == "3157"
        assert flags[0].mean_pre_win_prob == 0.60

    def test_selection_bias_not_flagged_low_w(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=0.08, personal_wpre=0.50),
            _make_agg(action_key="3157", personal_dw=0.02, personal_wpre=0.52),
        ]
        result = compare_action_stats(aggs)
        assert result is not None
        # W(x)=0.52 is below 0.55 threshold — no flags
        assert result.groups[0].selection_bias_flags == []

    def test_selection_bias_not_flagged_high_delta_w(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=0.05, personal_wpre=0.60),
            _make_agg(action_key="3157", personal_dw=0.08, personal_wpre=0.60),
        ]
        result = compare_action_stats(aggs)
        assert result is not None
        flags = result.groups[0].selection_bias_flags
        # 3089 has high W(x) but ΔW=0.05 < median=0.065, so flagged
        # 3157 has high W(x) but ΔW=0.08 > median=0.065, not flagged
        assert len(flags) == 1
        assert flags[0].action_key == "3089"

    def test_action_names_resolved(self) -> None:
        aggs = [_make_agg(action_key="3089", personal_dw=0.05)]
        result = compare_action_stats(
            aggs,
            item_names={"3089": "Rabadon's Deathcap"},
        )
        assert result is not None
        assert result.groups[0].ranked_actions[0].action_name == "Rabadon's Deathcap"

    def test_none_delta_w_excluded(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=0.05),
            _make_agg(
                action_key="3157",
                personal_dw=None,
                pop_dw=None,
                insufficient=True,
            ),
        ]
        result = compare_action_stats(aggs)
        assert result is not None
        # 3157 has no effective ΔW, should be excluded
        assert len(result.groups[0].ranked_actions) == 1
        assert result.groups[0].ranked_actions[0].action_key == "3089"

    def test_to_dict_serializable(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=0.05),
            _make_agg(action_key="3157", personal_dw=0.03, personal_count=100),
        ]
        result = compare_action_stats(aggs)
        assert result is not None
        d = result.to_dict()
        # Should be JSON-serializable
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["schema_version"] == 1

    def test_all_none_delta_w_returns_none(self) -> None:
        aggs = [
            _make_agg(action_key="3089", personal_dw=None, pop_dw=None, insufficient=True),
            _make_agg(action_key="3157", personal_dw=None, pop_dw=None, insufficient=True),
        ]
        result = compare_action_stats(aggs)
        # All actions excluded → no groups → None
        assert result is None
