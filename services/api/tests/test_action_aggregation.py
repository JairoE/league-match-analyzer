"""Tests for action aggregation service (pipeline step 5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.action_aggregation import (
    MIN_PERSONAL_SAMPLE_SIZE,
    OPPONENT_DAMAGE_BUCKET_V1,
    _build_personal_sql,
    _build_population_sql,
    _row_to_aggregate_row,
    aggregate_action_stats_for_player,
)


class TestRowToAggregateRow:
    def test_builds_from_full_values(self) -> None:
        row = _row_to_aggregate_row(100, 0.02, 0.55, 0.01)
        assert row.count == 100
        assert row.mean_delta_w == 0.02
        assert row.mean_pre_win_prob == 0.55
        assert row.stddev_delta_w == 0.01

    def test_handles_none_and_zero_count(self) -> None:
        row = _row_to_aggregate_row(0, None, None, None)
        assert row.count == 0
        assert row.mean_delta_w is None
        assert row.mean_pre_win_prob is None
        assert row.stddev_delta_w is None


class TestBuildPersonalSql:
    def test_no_filters_returns_base_cte(self) -> None:
        sql, params = _build_personal_sql(None, None)
        assert "player_actions" in sql
        assert "riot_account_id" in sql
        assert params == {}

    def test_champion_filter_adds_where(self) -> None:
        sql, params = _build_personal_sql("157", None)
        assert "champion_id = :champion" in sql
        assert params == {"champion": "157"}

    def test_rank_tier_filter_adds_where(self) -> None:
        sql, params = _build_personal_sql(None, "GOLD")
        assert "rank_tier = :rank_tier" in sql
        assert params == {"rank_tier": "GOLD"}

    def test_both_filters(self) -> None:
        sql, params = _build_personal_sql("157", "GOLD")
        assert "champion_id = :champion" in sql
        assert "rank_tier = :rank_tier" in sql
        assert params == {"champion": "157", "rank_tier": "GOLD"}


class TestBuildPopulationSql:
    def test_empty_pairs_returns_empty_sql(self) -> None:
        sql, params = _build_population_sql([])
        assert sql == ""
        assert params == {}

    def test_one_pair_expands_placeholders(self) -> None:
        sql, params = _build_population_sql([("157", "GOLD")])
        assert "(:cr_c0, :cr_r0)" in sql
        assert params == {"cr_c0": "157", "cr_r0": "GOLD"}

    def test_two_pairs_expands_both(self) -> None:
        sql, params = _build_population_sql([("157", "GOLD"), ("200", "PLATINUM")])
        assert "(:cr_c0, :cr_r0)" in sql
        assert "(:cr_c1, :cr_r1)" in sql
        assert params == {
            "cr_c0": "157",
            "cr_r0": "GOLD",
            "cr_c1": "200",
            "cr_r1": "PLATINUM",
        }


class TestAggregateActionStatsForPlayer:
    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        session = AsyncMock()
        return session

    async def test_empty_personal_returns_empty_list(
        self,
        mock_session: AsyncMock,
    ) -> None:
        # First execute (personal) returns no rows
        personal_result = MagicMock()
        personal_result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=personal_result)

        out = await aggregate_action_stats_for_player(
            mock_session,
            uuid4(),
        )
        assert out == []
        assert mock_session.execute.await_count == 1

    async def test_personal_and_population_merged_insufficient_flag(
        self,
        mock_session: AsyncMock,
    ) -> None:
        account_id = uuid4()
        personal_result = MagicMock()
        personal_result.mappings.return_value.all.return_value = [
            {
                "champion_id": "157",
                "rank_tier": "GOLD",
                "action_type": "ITEM_PURCHASE",
                "action_key": "3089",
                "k": 30,  # below MIN_PERSONAL_SAMPLE_SIZE
                "mean_delta_w": 0.01,
                "mean_pre_win_prob": 0.52,
                "stddev_delta_w": 0.02,
            },
        ]
        pop_result = MagicMock()
        pop_result.mappings.return_value.all.return_value = [
            {
                "champion_id": "157",
                "rank_tier": "GOLD",
                "action_type": "ITEM_PURCHASE",
                "action_key": "3089",
                "k": 500,
                "mean_delta_w": 0.015,
                "mean_pre_win_prob": 0.51,
                "stddev_delta_w": 0.018,
            },
        ]
        call_count = 0

        async def execute_side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return personal_result
            return pop_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        out = await aggregate_action_stats_for_player(mock_session, account_id)

        assert len(out) == 1
        agg = out[0]
        assert agg.group_key.champion_id == "157"
        assert agg.group_key.rank_tier == "GOLD"
        assert agg.group_key.action_type == "ITEM_PURCHASE"
        assert agg.group_key.action_key == "3089"
        assert agg.group_key.opponent_damage_bucket == OPPONENT_DAMAGE_BUCKET_V1
        assert agg.personal_stats.count == 30
        assert agg.personal_stats.mean_delta_w == 0.01
        assert agg.insufficient_personal_sample is True  # 30 < 50
        assert agg.population_stats.count == 500
        assert agg.population_stats.mean_delta_w == 0.015
        assert mock_session.execute.await_count == 2

    async def test_sufficient_personal_clears_insufficient_flag(
        self,
        mock_session: AsyncMock,
    ) -> None:
        personal_result = MagicMock()
        personal_result.mappings.return_value.all.return_value = [
            {
                "champion_id": "200",
                "rank_tier": "PLATINUM",
                "action_type": "OBJECTIVE_KILL",
                "action_key": "DRAGON",
                "k": MIN_PERSONAL_SAMPLE_SIZE + 10,
                "mean_delta_w": -0.01,
                "mean_pre_win_prob": 0.48,
                "stddev_delta_w": 0.03,
            },
        ]
        pop_result = MagicMock()
        pop_result.mappings.return_value.all.return_value = [
            {
                "champion_id": "200",
                "rank_tier": "PLATINUM",
                "action_type": "OBJECTIVE_KILL",
                "action_key": "DRAGON",
                "k": 1000,
                "mean_delta_w": -0.005,
                "mean_pre_win_prob": 0.49,
                "stddev_delta_w": 0.025,
            },
        ]
        call_count = 0

        async def execute_side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            nonlocal call_count
            call_count += 1
            return personal_result if call_count == 1 else pop_result

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        out = await aggregate_action_stats_for_player(mock_session, uuid4())

        assert len(out) == 1
        assert out[0].insufficient_personal_sample is False
        assert out[0].personal_stats.count == MIN_PERSONAL_SAMPLE_SIZE + 10
