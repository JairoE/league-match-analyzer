"""Tests for action aggregation service (pipeline step 5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.action_aggregation import (
    MIN_PERSONAL_SAMPLE_SIZE,
    OPPONENT_DAMAGE_BUCKET_V1,
    _build_query,
    _to_float,
    aggregate_action_stats_for_player,
)


class TestToFloat:
    def test_converts_numeric(self) -> None:
        assert _to_float(0.02) == 0.02

    def test_none_returns_none(self) -> None:
        assert _to_float(None) is None

    def test_converts_decimal(self) -> None:
        from decimal import Decimal

        assert _to_float(Decimal("0.55")) == 0.55


class TestBuildQuery:
    def test_no_filters(self) -> None:
        sql, params = _build_query(None, None)
        assert "personal_agg" in sql
        assert "population_agg" in sql
        assert params == {}

    def test_champion_filter(self) -> None:
        sql, params = _build_query("157", None)
        assert "champion_id = :champion" in sql
        assert params == {"champion": "157"}

    def test_rank_tier_filter(self) -> None:
        sql, params = _build_query(None, "GOLD")
        assert "rank_tier = :rank_tier" in sql
        assert params == {"rank_tier": "GOLD"}

    def test_both_filters(self) -> None:
        sql, params = _build_query("157", "GOLD")
        assert "champion_id = :champion" in sql
        assert "rank_tier = :rank_tier" in sql
        assert params == {"champion": "157", "rank_tier": "GOLD"}

    def test_population_uses_subquery_not_bind_params(self) -> None:
        sql, _ = _build_query(None, None)
        # Population CTE filters via subquery from personal_agg, not IN (:cr_c0, :cr_r0)
        assert "SELECT DISTINCT champion_id, rank_tier FROM personal_agg" in sql
        assert ":cr_c0" not in sql


class TestAggregateActionStatsForPlayer:
    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        return AsyncMock()

    async def test_empty_result_returns_empty_list(
        self,
        mock_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result)

        out = await aggregate_action_stats_for_player(mock_session, uuid4())
        assert out == []
        assert mock_session.execute.await_count == 1

    async def test_insufficient_personal_sample_flag(
        self,
        mock_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {
                "champion_id": "157",
                "rank_tier": "GOLD",
                "action_type": "ITEM_PURCHASE",
                "action_key": "3089",
                "personal_k": 30,  # below MIN_PERSONAL_SAMPLE_SIZE
                "personal_mean_delta_w": 0.01,
                "personal_mean_pre_win_prob": 0.52,
                "personal_stddev_delta_w": 0.02,
                "pop_k": 500,
                "pop_mean_delta_w": 0.015,
                "pop_mean_pre_win_prob": 0.51,
                "pop_stddev_delta_w": 0.018,
            },
        ]
        mock_session.execute = AsyncMock(return_value=result)

        out = await aggregate_action_stats_for_player(mock_session, uuid4())

        assert len(out) == 1
        agg = out[0]
        assert agg.group_key.champion_id == "157"
        assert agg.group_key.rank_tier == "GOLD"
        assert agg.group_key.action_type == "ITEM_PURCHASE"
        assert agg.group_key.action_key == "3089"
        assert agg.group_key.opponent_damage_bucket == OPPONENT_DAMAGE_BUCKET_V1
        assert agg.personal_stats.count == 30
        assert agg.personal_stats.mean_delta_w == 0.01
        assert agg.insufficient_personal_sample is True
        assert agg.population_stats.count == 500
        assert agg.population_stats.mean_delta_w == 0.015
        assert mock_session.execute.await_count == 1

    async def test_sufficient_personal_clears_flag(
        self,
        mock_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {
                "champion_id": "200",
                "rank_tier": "PLATINUM",
                "action_type": "OBJECTIVE_KILL",
                "action_key": "DRAGON",
                "personal_k": MIN_PERSONAL_SAMPLE_SIZE + 10,
                "personal_mean_delta_w": -0.01,
                "personal_mean_pre_win_prob": 0.48,
                "personal_stddev_delta_w": 0.03,
                "pop_k": 1000,
                "pop_mean_delta_w": -0.005,
                "pop_mean_pre_win_prob": 0.49,
                "pop_stddev_delta_w": 0.025,
            },
        ]
        mock_session.execute = AsyncMock(return_value=result)

        out = await aggregate_action_stats_for_player(mock_session, uuid4())

        assert len(out) == 1
        assert out[0].insufficient_personal_sample is False
        assert out[0].personal_stats.count == MIN_PERSONAL_SAMPLE_SIZE + 10
        assert out[0].population_stats.count == 1000

    async def test_null_population_stats_default_to_zero(
        self,
        mock_session: AsyncMock,
    ) -> None:
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {
                "champion_id": "157",
                "rank_tier": "GOLD",
                "action_type": "ITEM_PURCHASE",
                "action_key": "3089",
                "personal_k": 5,
                "personal_mean_delta_w": 0.01,
                "personal_mean_pre_win_prob": 0.52,
                "personal_stddev_delta_w": None,
                "pop_k": 0,
                "pop_mean_delta_w": None,
                "pop_mean_pre_win_prob": None,
                "pop_stddev_delta_w": None,
            },
        ]
        mock_session.execute = AsyncMock(return_value=result)

        out = await aggregate_action_stats_for_player(mock_session, uuid4())

        assert len(out) == 1
        assert out[0].population_stats.count == 0
        assert out[0].population_stats.mean_delta_w is None
        assert out[0].personal_stats.stddev_delta_w is None
