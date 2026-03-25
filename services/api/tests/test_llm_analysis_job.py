"""Tests for LLM analysis ARQ job (pipeline steps 5→8)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.action_aggregation import ActionAggregate, AggregateRow, GroupKey
from app.services.llm_client import LLMResponse

_SEPARATOR = "─" * 60


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

        print(f"\n{_SEPARATOR}")
        print("PIPELINE: Guard — no OpenAI API key configured")
        print(_SEPARATOR)

        print("  Settings: openai_api_key = '' (empty)")

        with patch(
            "app.jobs.llm_analysis.get_settings",
            return_value=_mock_settings(api_key=""),
        ):
            result = await llm_analysis_job({}, str(uuid4()), "157")

        print(f"  Result:   {result}")
        print("  Pipeline halted before Step 5 (aggregation never called)")
        print(_SEPARATOR)

        assert result["status"] == "skipped"
        assert result["reason"] == "no_api_key"

    async def test_no_data_when_aggregates_empty(self) -> None:
        """Job should return no_data when aggregation returns nothing."""
        from app.jobs.llm_analysis import llm_analysis_job

        print(f"\n{_SEPARATOR}")
        print("PIPELINE: Step 5 (Aggregate) — no action stats found")
        print(_SEPARATOR)

        mock_session = AsyncMock()
        mock_aggregate = AsyncMock(return_value=[])

        print("  Step 5 input:  champion_id='157', rank_tier=None")
        print("  Step 5 output: [] (no aggregates)")

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

        print(f"  Result: {result}")
        print("  Pipeline halted at Step 5 — nothing to compare")
        print(_SEPARATOR)

        assert result["status"] == "no_data"

    async def test_no_comparison_when_all_none_dw(self) -> None:
        """Job should return no_comparison when compare_action_stats returns None."""
        from app.jobs.llm_analysis import llm_analysis_job

        print(f"\n{_SEPARATOR}")
        print("PIPELINE: Step 6 (Compare) — all delta_w values are None")
        print(_SEPARATOR)

        agg_with_none = _make_agg(personal_dw=None)
        agg_with_none.personal_stats = AggregateRow(
            count=0, mean_delta_w=None, mean_pre_win_prob=None, stddev_delta_w=None,
        )
        agg_with_none.population_stats = AggregateRow(
            count=0, mean_delta_w=None, mean_pre_win_prob=None, stddev_delta_w=None,
        )
        agg_with_none.insufficient_personal_sample = True

        ak = agg_with_none.group_key.action_key
        ps = agg_with_none.personal_stats
        pop = agg_with_none.population_stats
        print(f"  Step 5 output: 1 aggregate (action_key='{ak}')")
        print(f"    personal  mean_delta_w={ps.mean_delta_w}  count={ps.count}")
        print(f"    population mean_delta_w={pop.mean_delta_w}  count={pop.count}")
        insuf = agg_with_none.insufficient_personal_sample
        print(f"    insufficient_personal_sample={insuf}")

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

        print("  Step 6 output: None (no scoreable actions)")
        print(f"  Result: {result}")
        print("  Pipeline halted at Step 6 — insufficient signal for comparison")
        print(_SEPARATOR)

        assert result["status"] == "no_comparison"

    async def test_llm_error_on_api_failure(self) -> None:
        """Job should return llm_error when LLM client raises."""
        from app.jobs.llm_analysis import llm_analysis_job

        print(f"\n{_SEPARATOR}")
        print("PIPELINE: Step 7 (LLM Call) — API raises RuntimeError")
        print(_SEPARATOR)

        aggregates = [
            _make_agg(action_key="3089", personal_dw=0.03),
            _make_agg(action_key="3031", personal_dw=-0.01),
        ]

        print(f"  Step 5 output: {len(aggregates)} aggregates")
        for agg in aggregates:
            ak = agg.group_key.action_key
            p_dw = agg.personal_stats.mean_delta_w
            pop_dw = agg.population_stats.mean_delta_w
            print(f"    {ak}: personal dw={p_dw:+.4f}  pop dw={pop_dw:+.4f}")

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

        print("  Step 6 output: comparison produced")
        print("  Champion resolved: 157 → Yasuo")
        print("  Step 7 input:  sending prompts to gpt-4o-mini...")
        print("  Step 7 output: RuntimeError('API down')")

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

        print(f"  Result: {result}")
        print("  Pipeline halted at Step 7 — LLM call failed, nothing persisted")
        print(_SEPARATOR)

        assert result["status"] == "llm_error"

    async def test_parse_error_stores_raw_response(self) -> None:
        """Job should store raw response on parse failure and return parse_error."""
        from app.jobs.llm_analysis import llm_analysis_job

        print(f"\n{_SEPARATOR}")
        print("PIPELINE: Step 7→8 — LLM returns invalid schema, raw response persisted")
        print(_SEPARATOR)

        aggregates = [
            _make_agg(action_key="3089", personal_dw=0.03),
            _make_agg(action_key="3031", personal_dw=-0.01),
        ]

        print(f"  Step 5 output: {len(aggregates)} aggregates")
        print("  Step 6 output: comparison produced")

        mock_champ = SimpleNamespace(name="Yasuo")
        mock_champ_result = MagicMock()
        mock_champ_result.scalar_one_or_none.return_value = mock_champ

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_champ_result)

        # LLM returns invalid JSON structure
        bad_content = '{"invalid": "not matching schema"}'
        bad_llm_response = LLMResponse(
            content=bad_content,
            model_name="gpt-4o-mini",
            token_count_input=100,
            token_count_output=50,
        )

        print("  Champion resolved: 157 → Yasuo")
        print(f"  Step 7 LLM raw response: {bad_content}")
        print("  Step 7 parse: FAILED — missing required fields")

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

            print("  Step 8 persist: raw response saved as output_payload")
            analysis = persisted_analyses[0]
            print(f"    champion_name:  {analysis.champion_name}")
            print(f"    recommendations: {analysis.recommendations}")
            print(f"    output_payload:  {analysis.output_payload}")
            print(f"  Result: {result}")
            print(_SEPARATOR)

            assert result["status"] == "parse_error"

            # Verify raw response was stored
            assert len(persisted_analyses) == 1
            assert analysis.recommendations == []
            assert analysis.output_payload == {"invalid": "not matching schema"}
            assert analysis.champion_name == "Yasuo"

    async def test_successful_flow(self) -> None:
        """Full success path: aggregate → compare → LLM → persist."""
        from app.jobs.llm_analysis import llm_analysis_job

        print(f"\n{_SEPARATOR}")
        print("PIPELINE: Full success — Steps 5 → 6 → 7 → 8")
        print(_SEPARATOR)

        aggregates = [
            _make_agg(action_key="3089", personal_dw=0.03),
            _make_agg(action_key="3031", personal_dw=-0.01, personal_count=70),
        ]
        item_names = {"3089": "Rabadon's Deathcap", "3031": "IE"}

        print(f"  Step 5 (Aggregate): {len(aggregates)} action aggregates")
        for agg in aggregates:
            name = item_names.get(agg.group_key.action_key, agg.group_key.action_key)
            print(
                f"    {name} ({agg.group_key.action_key}): "
                f"personal dw={agg.personal_stats.mean_delta_w:+.4f} "
                f"(n={agg.personal_stats.count})  "
                f"pop dw={agg.population_stats.mean_delta_w:+.4f} "
                f"(n={agg.population_stats.count})"
            )

        mock_champ = SimpleNamespace(name="Yasuo")
        mock_champ_result = MagicMock()
        mock_champ_result.scalar_one_or_none.return_value = mock_champ

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_champ_result)

        valid_json = _valid_llm_json()
        valid_response = LLMResponse(
            content=valid_json,
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

        match_ids = ["NA1_111", "NA1_222"]

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
                AsyncMock(return_value=item_names),
            ),
            patch(
                "app.jobs.llm_analysis._get_scored_match_ids",
                AsyncMock(return_value=match_ids),
            ),
            patch(
                "app.jobs.llm_analysis.OpenAIClient",
                return_value=mock_client_instance,
            ),
        ):
            # Capture prompts sent to LLM
            n = len(aggregates)
            print(f"\n  Step 6 (Compare): {n} aggregates")
            print(f"    item_names mapped: {item_names}")

            print("\n  Champion resolved: 157 → Yasuo")
            print(f"  Scored matches: {match_ids}")

            result = await llm_analysis_job({}, str(uuid4()), "157", "GOLD")

            # Show what was sent to LLM
            ca = mock_client_instance.complete.call_args
            sys_p = ca.args[0] if ca.args else ""
            usr_p = ca.args[1] if len(ca.args) > 1 else ""

            print("\n  Step 7 (LLM Prompt):")
            print(f"    System prompt ({len(sys_p)} chars):")
            print(f"      {sys_p[:100]}...")
            print(f"    User prompt ({len(usr_p)} chars):")
            print(f"      {usr_p[:160]}...")
            print("\n  Step 7 (LLM Response):")
            print(f"    model: {valid_response.model_name}")
            tok_in = valid_response.token_count_input
            tok_out = valid_response.token_count_output
            print(f"    tokens: {tok_in} in / {tok_out} out")
            parsed_output = json.loads(valid_json)
            recs = parsed_output["recommendations"]
            print(f"    recommendations: {len(recs)}")
            for rec in recs:
                r = rec["rank"]
                cat = rec["category"]
                print(f"      #{r} [{cat}] {rec['title']}")
                cur = rec["current_choice"]
                nxt = rec["recommended_choice"]
                gap = rec["delta_w_gap"]
                print(f"         {cur} → {nxt} (gap={gap:+.4f})")
            assessment = parsed_output["overall_assessment"]
            print(f"    overall_assessment: {assessment}")

            analysis = persisted_analyses[0]
            print("\n  Step 8 (Persist):")
            print(f"    champion_name:    {analysis.champion_name}")
            print(f"    rank_tier:        {analysis.rank_tier}")
            print(f"    match_ids:        {analysis.match_ids}")
            print(f"    model_name:       {analysis.model_name}")
            a_in = analysis.token_count_input
            a_out = analysis.token_count_output
            print(f"    tokens:           {a_in} in / {a_out} out")
            n_recs = len(analysis.recommendations)
            print(f"    recommendations:  {n_recs}")
            print(f"      {analysis.recommendations[0]['title']}")

            print(f"\n  Final result: {result}")
            print(_SEPARATOR)

            assert result["status"] == "ok"
            assert result["champion_name"] == "Yasuo"
            assert result["rank_tier"] == "GOLD"
            assert result["match_count"] == 2
            assert result["recommendations_count"] == 1
            assert result["token_input"] == 200
            assert result["token_output"] == 100

            # Verify persisted analysis
            assert len(persisted_analyses) == 1
            assert analysis.champion_name == "Yasuo"
            assert analysis.rank_tier == "GOLD"
            assert analysis.match_ids == ["NA1_111", "NA1_222"]
            assert analysis.model_name == "gpt-4o-mini-2024-07-18"
            assert analysis.token_count_input == 200
            assert analysis.token_count_output == 100
            assert len(analysis.recommendations) == 1
            assert analysis.recommendations[0]["title"] == "Switch to Kraken Slayer"
