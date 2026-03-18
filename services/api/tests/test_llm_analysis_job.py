"""Tests for LLM analysis ARQ job (pipeline steps 5→8)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.action_aggregation import ActionAggregate, AggregateRow, GroupKey
from app.services.llm_client import LLMResponse


def _make_agg(
    *,
    action_key: str = "3089",
    personal_dw: float = 0.03,
    personal_count: int = 60,
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
            mean_pre_win_prob=0.50,
            stddev_delta_w=0.01,
        ),
        population_stats=AggregateRow(
            count=500,
            mean_delta_w=0.025,
            mean_pre_win_prob=0.51,
            stddev_delta_w=0.01,
        ),
        insufficient_personal_sample=insufficient,
    )


def _valid_llm_json() -> str:
    return json.dumps({
        "recommendations": [
            {
                "rank": 1,
                "title": "Switch to Kraken Slayer",
                "current_choice": "Infinity Edge",
                "recommended_choice": "Kraken Slayer",
                "delta_w_gap": 0.02,
                "explanation": "Better win rate impact.",
                "category": "item_purchase",
            }
        ],
        "selection_bias_summary": None,
        "overall_assessment": "Focus on itemization.",
    })


def _mock_settings(api_key: str = "test-key") -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key=api_key,
        llm_model_name="gpt-4o-mini",
    )


class TestLLMAnalysisJob:
    """Tests for llm_analysis_job orchestration."""

    async def test_skipped_when_no_api_key(self) -> None:
        """Job should return skipped status when API key is empty."""
        from app.jobs.llm_analysis import llm_analysis_job

        with patch(
            "app.jobs.llm_analysis.get_settings",
            return_value=_mock_settings(api_key=""),
        ):
            result = await llm_analysis_job({}, str(uuid4()), "157")
            assert result["status"] == "skipped"
            assert result["reason"] == "no_api_key"

    async def test_no_data_when_aggregates_empty(self) -> None:
        """Job should return no_data when aggregation returns nothing."""
        from app.jobs.llm_analysis import llm_analysis_job

        mock_session = AsyncMock()
        mock_aggregate = AsyncMock(return_value=[])

        with (
            patch("app.jobs.llm_analysis.get_settings", return_value=_mock_settings()),
            patch(
                "app.jobs.llm_analysis.async_session_factory",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch(
                "app.jobs.llm_analysis.aggregate_action_stats_for_player",
                mock_aggregate,
            ),
        ):
            result = await llm_analysis_job({}, str(uuid4()), "157")
            assert result["status"] == "no_data"

    async def test_no_comparison_when_all_none_dw(self) -> None:
        """Job should return no_comparison when compare_action_stats returns None."""
        from app.jobs.llm_analysis import llm_analysis_job

        agg_with_none = _make_agg(personal_dw=None)
        agg_with_none.personal_stats = AggregateRow(
            count=0, mean_delta_w=None, mean_pre_win_prob=None, stddev_delta_w=None,
        )
        agg_with_none.population_stats = AggregateRow(
            count=0, mean_delta_w=None, mean_pre_win_prob=None, stddev_delta_w=None,
        )
        agg_with_none.insufficient_personal_sample = True

        mock_session = AsyncMock()

        with (
            patch("app.jobs.llm_analysis.get_settings", return_value=_mock_settings()),
            patch(
                "app.jobs.llm_analysis.async_session_factory",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch(
                "app.jobs.llm_analysis.aggregate_action_stats_for_player",
                AsyncMock(return_value=[agg_with_none]),
            ),
            patch(
                "app.jobs.llm_analysis.load_item_name_map",
                AsyncMock(return_value={}),
            ),
        ):
            result = await llm_analysis_job({}, str(uuid4()), "157")
            assert result["status"] == "no_comparison"

    async def test_llm_error_on_api_failure(self) -> None:
        """Job should return llm_error when LLM client raises."""
        from app.jobs.llm_analysis import llm_analysis_job

        aggregates = [
            _make_agg(action_key="3089", personal_dw=0.03),
            _make_agg(action_key="3031", personal_dw=-0.01),
        ]

        # Mock champion resolution
        mock_champ = SimpleNamespace(name="Yasuo")
        mock_champ_result = MagicMock()
        mock_champ_result.scalar_one_or_none.return_value = mock_champ

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_champ_result)

        mock_client_instance = AsyncMock()
        mock_client_instance.complete = AsyncMock(
            side_effect=RuntimeError("API down")
        )

        with (
            patch("app.jobs.llm_analysis.get_settings", return_value=_mock_settings()),
            patch(
                "app.jobs.llm_analysis.async_session_factory",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
            patch(
                "app.jobs.llm_analysis.aggregate_action_stats_for_player",
                AsyncMock(return_value=aggregates),
            ),
            patch(
                "app.jobs.llm_analysis.load_item_name_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.jobs.llm_analysis._get_scored_match_ids",
                AsyncMock(return_value=["NA1_123"]),
            ),
            patch(
                "app.jobs.llm_analysis.OpenAIClient",
                return_value=mock_client_instance,
            ),
        ):
            result = await llm_analysis_job({}, str(uuid4()), "157")
            assert result["status"] == "llm_error"

    async def test_parse_error_stores_raw_response(self) -> None:
        """Job should store raw response on parse failure and return parse_error."""
        from app.jobs.llm_analysis import llm_analysis_job

        aggregates = [
            _make_agg(action_key="3089", personal_dw=0.03),
            _make_agg(action_key="3031", personal_dw=-0.01),
        ]

        mock_champ = SimpleNamespace(name="Yasuo")
        mock_champ_result = MagicMock()
        mock_champ_result.scalar_one_or_none.return_value = mock_champ

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_champ_result)

        # LLM returns invalid JSON structure
        bad_llm_response = LLMResponse(
            content='{"invalid": "not matching schema"}',
            model_name="gpt-4o-mini",
            token_count_input=100,
            token_count_output=50,
        )

        mock_client_instance = AsyncMock()
        mock_client_instance.complete = AsyncMock(return_value=bad_llm_response)

        # Track what gets persisted (session.add is sync)
        persisted_analyses: list = []

        persist_session = AsyncMock()
        persist_session.add = lambda obj: persisted_analyses.append(obj)
        persist_session.commit = AsyncMock()
        persist_session.refresh = AsyncMock()

        call_count = 0

        def fake_session_factory() -> AsyncMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                )
            return AsyncMock(
                __aenter__=AsyncMock(return_value=persist_session),
                __aexit__=AsyncMock(return_value=False),
            )

        with (
            patch("app.jobs.llm_analysis.get_settings", return_value=_mock_settings()),
            patch(
                "app.jobs.llm_analysis.async_session_factory",
                side_effect=fake_session_factory,
            ),
            patch(
                "app.jobs.llm_analysis.aggregate_action_stats_for_player",
                AsyncMock(return_value=aggregates),
            ),
            patch(
                "app.jobs.llm_analysis.load_item_name_map",
                AsyncMock(return_value={}),
            ),
            patch(
                "app.jobs.llm_analysis._get_scored_match_ids",
                AsyncMock(return_value=["NA1_123"]),
            ),
            patch(
                "app.jobs.llm_analysis.OpenAIClient",
                return_value=mock_client_instance,
            ),
        ):
            result = await llm_analysis_job({}, str(uuid4()), "157")
            assert result["status"] == "parse_error"

            # Verify raw response was stored
            assert len(persisted_analyses) == 1
            analysis = persisted_analyses[0]
            assert analysis.recommendations == []
            assert analysis.output_payload == {"invalid": "not matching schema"}
            assert analysis.champion_name == "Yasuo"

    async def test_successful_flow(self) -> None:
        """Full success path: aggregate → compare → LLM → persist."""
        from app.jobs.llm_analysis import llm_analysis_job

        aggregates = [
            _make_agg(action_key="3089", personal_dw=0.03),
            _make_agg(action_key="3031", personal_dw=-0.01, personal_count=70),
        ]

        mock_champ = SimpleNamespace(name="Yasuo")
        mock_champ_result = MagicMock()
        mock_champ_result.scalar_one_or_none.return_value = mock_champ

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_champ_result)

        valid_response = LLMResponse(
            content=_valid_llm_json(),
            model_name="gpt-4o-mini-2024-07-18",
            token_count_input=200,
            token_count_output=100,
        )

        mock_client_instance = AsyncMock()
        mock_client_instance.complete = AsyncMock(return_value=valid_response)

        persisted_analyses: list = []
        persist_session = AsyncMock()
        persist_session.add = lambda obj: persisted_analyses.append(obj)
        persist_session.commit = AsyncMock()
        persist_session.refresh = AsyncMock()

        call_count = 0

        def fake_session_factory() -> AsyncMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AsyncMock(
                    __aenter__=AsyncMock(return_value=mock_session),
                    __aexit__=AsyncMock(return_value=False),
                )
            return AsyncMock(
                __aenter__=AsyncMock(return_value=persist_session),
                __aexit__=AsyncMock(return_value=False),
            )

        with (
            patch("app.jobs.llm_analysis.get_settings", return_value=_mock_settings()),
            patch(
                "app.jobs.llm_analysis.async_session_factory",
                side_effect=fake_session_factory,
            ),
            patch(
                "app.jobs.llm_analysis.aggregate_action_stats_for_player",
                AsyncMock(return_value=aggregates),
            ),
            patch(
                "app.jobs.llm_analysis.load_item_name_map",
                AsyncMock(return_value={"3089": "Rabadon's Deathcap", "3031": "IE"}),
            ),
            patch(
                "app.jobs.llm_analysis._get_scored_match_ids",
                AsyncMock(return_value=["NA1_111", "NA1_222"]),
            ),
            patch(
                "app.jobs.llm_analysis.OpenAIClient",
                return_value=mock_client_instance,
            ),
        ):
            result = await llm_analysis_job({}, str(uuid4()), "157", "GOLD")

            assert result["status"] == "ok"
            assert result["champion_name"] == "Yasuo"
            assert result["rank_tier"] == "GOLD"
            assert result["match_count"] == 2
            assert result["recommendations_count"] == 1
            assert result["token_input"] == 200
            assert result["token_output"] == 100

            # Verify persisted analysis
            assert len(persisted_analyses) == 1
            analysis = persisted_analyses[0]
            assert analysis.champion_name == "Yasuo"
            assert analysis.rank_tier == "GOLD"
            assert analysis.match_ids == ["NA1_111", "NA1_222"]
            assert analysis.model_name == "gpt-4o-mini-2024-07-18"
            assert analysis.token_count_input == 200
            assert analysis.token_count_output == 100
            assert len(analysis.recommendations) == 1
            assert analysis.recommendations[0]["title"] == "Switch to Kraken Slayer"
