"""Tests for the coach chat tool registry and executors."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.services.chat import tools
from app.services.chat.tools import (
    CHAT_TOOLS,
    ActionStatsArgs,
    LatestAnalysisArgs,
    PlayerProfileArgs,
    RecentMatchesArgs,
    cap_tool_result,
    openai_tool_schemas,
)

# ── Fakes ─────────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows: list | None = None, scalar: object | None = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def fetchall(self) -> list:
        return self._rows

    def scalars(self) -> _FakeResult:
        return self

    def first(self) -> object | None:
        return self._scalar


class _FakeSession:
    """Session returning queued _FakeResult objects per execute() call."""

    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = list(results)

    async def execute(self, statement: object) -> _FakeResult:
        return self._results.pop(0)


def _account() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        riot_id="TestUser#NA1",
        puuid="puuid-1",
        rank_tier="GOLD",
        summoner_level=150,
    )


# ── Schemas / registry ────────────────────────────────────────────────


def test_openai_tool_schemas_are_valid_function_specs() -> None:
    schemas = openai_tool_schemas()

    assert len(schemas) == 4
    for schema in schemas:
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] in CHAT_TOOLS
        assert function["description"]
        assert function["parameters"]["type"] == "object"
    # Round-trips through JSON (what the OpenAI SDK requires)
    json.dumps(schemas)


def test_cap_tool_result_passes_small_payloads() -> None:
    payload = {"a": 1, "b": "two"}

    assert cap_tool_result(payload) == '{"a":1,"b":"two"}'


def test_cap_tool_result_truncates_oversized_payloads() -> None:
    payload = {"blob": "x" * 10_000}

    capped = cap_tool_result(payload, max_chars=100)

    assert len(capped) <= 100 + len("…[truncated]")
    assert capped.endswith("…[truncated]")


# ── get_player_profile ────────────────────────────────────────────────


async def test_get_player_profile_lists_analyzed_champions() -> None:
    account = _account()
    session = _FakeSession([_FakeResult(rows=[("Jhin",), ("Yasuo",)])])

    result = await CHAT_TOOLS["get_player_profile"].executor(
        session, account, PlayerProfileArgs()
    )

    assert result == {
        "riot_id": "TestUser#NA1",
        "rank_tier": "GOLD",
        "summoner_level": 150,
        "analyzed_champions": ["Jhin", "Yasuo"],
    }
    assert "puuid" not in result
    json.dumps(result)


# ── get_latest_analysis ───────────────────────────────────────────────


async def test_get_latest_analysis_no_row_returns_message() -> None:
    session = _FakeSession([_FakeResult(scalar=None)])

    result = await CHAT_TOOLS["get_latest_analysis"].executor(
        session, _account(), LatestAnalysisArgs(champion_name="Jhin")
    )

    assert "message" in result
    assert "Jhin" in result["message"]


async def test_get_latest_analysis_shapes_row() -> None:
    row = SimpleNamespace(
        champion_name="Jhin",
        rank_tier="SILVER",
        created_at="2026-07-01 00:00:00+00:00",
        match_ids=["NA1_1", "NA1_2", "NA1_3"],
        recommendations=[{"rank": 1, "title": "Buy Collector"}],
        output_payload={
            "overall_assessment": "Good macro.",
            "selection_bias_summary": None,
        },
    )
    session = _FakeSession([_FakeResult(scalar=row)])

    result = await CHAT_TOOLS["get_latest_analysis"].executor(
        session, _account(), LatestAnalysisArgs()
    )

    assert result["champion_name"] == "Jhin"
    assert result["match_count"] == 3
    assert result["recommendations"] == [{"rank": 1, "title": "Buy Collector"}]
    assert result["overall_assessment"] == "Good macro."
    assert result["selection_bias_summary"] is None
    json.dumps(result)


# ── get_action_stats ──────────────────────────────────────────────────


async def test_get_action_stats_unknown_champion_returns_message() -> None:
    session = _FakeSession([_FakeResult(scalar=None)])

    result = await CHAT_TOOLS["get_action_stats"].executor(
        session, _account(), ActionStatsArgs(champion_name="NotAChampion")
    )

    assert result == {"message": "Unknown champion 'NotAChampion'."}


async def test_get_action_stats_no_aggregates_returns_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_aggregates(*args: object, **kwargs: object) -> list:
        return []

    monkeypatch.setattr(tools, "aggregate_action_stats_for_player", _no_aggregates)
    session = _FakeSession([])

    result = await CHAT_TOOLS["get_action_stats"].executor(
        session, _account(), ActionStatsArgs()
    )

    assert "message" in result
    assert "No scored match data" in result["message"]


async def test_get_action_stats_returns_trimmed_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _action(rank: int) -> dict[str, Any]:
        return {
            "action_key": f"item-{rank}",
            "action_name": f"Item {rank}",
            "effective_delta_w": 0.01 * rank,
            "personal_delta_w": None,
            "population_delta_w": 0.01,
            "personal_count": rank,
            "population_count": 100,
            "mean_pre_win_prob": 0.5,
            "used_population_fallback": True,
            "rank": rank,
        }

    def _gap() -> dict[str, Any]:
        return {
            "summoner_action": _action(3),
            "better_alternative": _action(1),
            "delta_w_gap": 0.02,
        }

    big_comparison = {
        "schema_version": 1,
        "groups": [
            {
                "champion_id": "202",
                "rank_tier": "GOLD",
                "action_type": f"type-{i}",
                "opponent_damage_bucket": "mixed",
                "ranked_actions": [_action(r) for r in range(1, 9)],
                "summoner_top_actions": [_action(1)],
                "improvement_gaps": [_gap() for _ in range(7)],
                "selection_bias_flags": [],
            }
            for i in range(6)
        ],
        "top_improvement_opportunities": [_gap() for _ in range(8)],
        "top_selection_bias_flags": [
            {
                "action_key": "item-9",
                "action_name": "Item 9",
                "mean_pre_win_prob": 0.6,
                "effective_delta_w": 0.001,
                "population_best_delta_w": 0.03,
            }
            for _ in range(5)
        ],
    }

    async def _aggregates(*args: object, **kwargs: object) -> list:
        return [object()]

    async def _item_names() -> dict[str, str]:
        return {}

    monkeypatch.setattr(tools, "aggregate_action_stats_for_player", _aggregates)
    monkeypatch.setattr(tools, "load_item_name_map", _item_names)
    monkeypatch.setattr(
        tools,
        "compare_action_stats",
        lambda *a, **kw: SimpleNamespace(to_dict=lambda: big_comparison),
    )
    session = _FakeSession([])

    result = await CHAT_TOOLS["get_action_stats"].executor(
        session, _account(), ActionStatsArgs()
    )

    assert len(result["groups"]) == 4
    assert len(result["groups"][0]["top_actions"]) == 5
    assert "improvement_gaps" not in result["groups"][0]
    assert len(result["top_improvement_gaps"]) == 5
    assert len(result["selection_bias_flags"]) == 3
    assert result["top_improvement_gaps"][0]["current"]["name"] == "Item 3"
    # Fits the tool-result cap after trimming
    assert len(cap_tool_result(result)) <= tools.MAX_TOOL_RESULT_CHARS
    json.dumps(result)


# ── list_recent_matches ───────────────────────────────────────────────


def _fake_match(champion: str, win: bool) -> SimpleNamespace:
    return SimpleNamespace(
        game_start_timestamp=1_700_000_000_000,
        game_info={
            "info": {
                "gameDuration": 1800,
                "queueId": 420,
                "participants": [
                    {
                        "puuid": "puuid-1",
                        "championName": champion,
                        "win": win,
                        "kills": 5,
                        "deaths": 2,
                        "assists": 9,
                        "totalMinionsKilled": 180,
                        "neutralMinionsKilled": 20,
                    },
                    {"puuid": "other", "championName": "Lux"},
                ],
            }
        },
    )


async def test_list_recent_matches_summarizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _list(*args: object, **kwargs: object) -> tuple[list, int]:
        return [_fake_match("Jhin", True), _fake_match("Yasuo", False)], 42

    monkeypatch.setattr(tools, "list_matches_for_riot_account", _list)
    session = _FakeSession([])

    result = await CHAT_TOOLS["list_recent_matches"].executor(
        session, _account(), RecentMatchesArgs(limit=5)
    )

    assert result["total_matches"] == 42
    assert [m["champion"] for m in result["matches"]] == ["Jhin", "Yasuo"]
    assert result["matches"][0]["cs"] == 200
    assert result["matches"][0]["win"] is True
    json.dumps(result)


async def test_list_recent_matches_no_details_returns_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _list(*args: object, **kwargs: object) -> tuple[list, int]:
        return [SimpleNamespace(game_info=None, game_start_timestamp=None)], 1

    monkeypatch.setattr(tools, "list_matches_for_riot_account", _list)
    session = _FakeSession([])

    result = await CHAT_TOOLS["list_recent_matches"].executor(
        session, _account(), RecentMatchesArgs()
    )

    assert "message" in result
