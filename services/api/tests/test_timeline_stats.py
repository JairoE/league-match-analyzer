"""Tests for fetch_timeline_stats in riot_sync.py.

Covers: happy-path CS/gold diffs, cache hit path, missing opponent,
short-game (no frame 15), and Riot API error handling.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.riot_api_client import RiotRequestError
from app.services.riot_sync import fetch_timeline_stats
from tests.fixtures.riot_payloads import load_match_detail, load_match_timeline


def _make_match(game_id: str, game_info: dict | None) -> SimpleNamespace:
    return SimpleNamespace(game_id=game_id, game_info=game_info)


class _FakeRedis:
    """In-memory Redis stand-in with get/set."""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self._store: dict[str, str] = store or {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *args: object, **kwargs: object) -> None:
        self._store[key] = value


class _FakeRiotClient:
    def __init__(self, timeline: dict) -> None:
        self.timeline = timeline
        self.calls: list[str] = []

    async def __aenter__(self) -> _FakeRiotClient:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def fetch_match_timeline(self, match_id: str) -> dict:
        self.calls.append(match_id)
        return self.timeline


class _ErrorRiotClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aenter__(self) -> _ErrorRiotClient:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def fetch_match_timeline(self, match_id: str) -> dict:
        raise self._exc


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeline_stats_computes_diffs_from_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Using real fixture data: MissFortune (pid 9) vs Twitch (pid 4) at BOTTOM."""
    detail = load_match_detail()
    timeline = load_match_timeline()

    match_obj = _make_match("NA1_5506397559", detail)
    fake_redis = _FakeRedis()
    fake_client = _FakeRiotClient(timeline)

    session = AsyncMock()
    monkeypatch.setattr(
        "app.services.riot_sync.get_match_by_identifier",
        AsyncMock(return_value=match_obj),
    )
    monkeypatch.setattr("app.services.riot_match_id.normalize_match_id", lambda mid: (mid, False))
    monkeypatch.setattr("app.services.cache.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.services.riot_sync.RiotApiClient", lambda: fake_client)

    result = await fetch_timeline_stats(session, "NA1_5506397559", target_participant_id=9)

    assert result is not None
    assert result["cs_diff_at_10"] == (46 - 66)  # MF - Twitch
    assert result["gold_diff_at_10"] == (2775 - 3640)
    assert result["cs_diff_at_15"] == (85 - 100)
    assert result["gold_diff_at_15"] == (4962 - 5608)
    assert result["lane_opponent_champion"] == "Twitch"
    assert result["lane_opponent_name"] is not None

    assert "timeline:NA1_5506397559" in fake_redis._store
    assert len(fake_client.calls) == 1


# ── Cache hit ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeline_stats_uses_cached_timeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Redis already has the timeline, Riot API should not be called."""
    detail = load_match_detail()
    timeline = load_match_timeline()

    match_obj = _make_match("NA1_5506397559", detail)
    fake_redis = _FakeRedis({"timeline:NA1_5506397559": json.dumps(timeline)})

    session = AsyncMock()
    monkeypatch.setattr(
        "app.services.riot_sync.get_match_by_identifier",
        AsyncMock(return_value=match_obj),
    )
    monkeypatch.setattr("app.services.riot_match_id.normalize_match_id", lambda mid: (mid, False))
    monkeypatch.setattr("app.services.cache.get_redis", lambda: fake_redis)

    riot_called = False

    class _NoCallClient:
        async def __aenter__(self) -> _NoCallClient:
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def fetch_match_timeline(self, mid: str) -> dict:
            nonlocal riot_called
            riot_called = True
            return {}

    monkeypatch.setattr("app.services.riot_sync.RiotApiClient", lambda: _NoCallClient())

    result = await fetch_timeline_stats(session, "NA1_5506397559", target_participant_id=9)

    assert result is not None
    assert "cs_diff_at_10" in result
    assert not riot_called


# ── No match in DB (match is None) ────────────────────────────────────


@pytest.mark.asyncio
async def test_timeline_stats_no_match_in_db_returns_none_on_empty_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no DB match exists and timeline has no frames, returns None."""
    empty_timeline: dict = {"info": {"frames": []}}
    fake_redis = _FakeRedis()
    fake_client = _FakeRiotClient(empty_timeline)

    session = AsyncMock()
    monkeypatch.setattr(
        "app.services.riot_sync.get_match_by_identifier",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("app.services.riot_match_id.normalize_match_id", lambda mid: (mid, False))
    monkeypatch.setattr("app.services.cache.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.services.riot_sync.RiotApiClient", lambda: fake_client)

    result = await fetch_timeline_stats(session, "NA1_0000000000", target_participant_id=1)
    assert result is None


# ── No lane opponent (e.g. JUNGLE vs no mirror) ──────────────────────


@pytest.mark.asyncio
async def test_timeline_stats_no_opponent_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no lane opponent exists (unique position), result is None — no diffs to compute."""
    timeline = load_match_timeline()
    # Build a game_info where no one shares positions (all same team)
    participants = [
        {
            "participantId": i,
            "teamId": 100,
            "individualPosition": f"POS{i}",
            "championName": f"C{i}",
        }
        for i in range(1, 11)
    ]
    game_info = {"info": {"participants": participants}}
    match_obj = _make_match("NA1_5506397559", game_info)
    fake_redis = _FakeRedis({"timeline:NA1_5506397559": json.dumps(timeline)})

    session = AsyncMock()
    monkeypatch.setattr(
        "app.services.riot_sync.get_match_by_identifier",
        AsyncMock(return_value=match_obj),
    )
    monkeypatch.setattr("app.services.riot_match_id.normalize_match_id", lambda mid: (mid, False))
    monkeypatch.setattr("app.services.cache.get_redis", lambda: fake_redis)

    result = await fetch_timeline_stats(session, "NA1_5506397559", target_participant_id=1)
    assert result is None


# ── Riot API error returns None ───────────────────────────────────────


@pytest.mark.asyncio
async def test_timeline_stats_riot_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """RiotRequestError during fetch returns None instead of crashing."""
    match_obj = _make_match("NA1_5506397559", None)
    fake_redis = _FakeRedis()
    error_client = _ErrorRiotClient(RiotRequestError("riot_api_failed", status=404))

    session = AsyncMock()
    monkeypatch.setattr(
        "app.services.riot_sync.get_match_by_identifier",
        AsyncMock(return_value=match_obj),
    )
    monkeypatch.setattr("app.services.riot_match_id.normalize_match_id", lambda mid: (mid, False))
    monkeypatch.setattr("app.services.cache.get_redis", lambda: fake_redis)
    monkeypatch.setattr("app.services.riot_sync.RiotApiClient", lambda: error_client)

    result = await fetch_timeline_stats(session, "NA1_5506397559", target_participant_id=9)
    assert result is None


# ── Short game (< 15 min frames) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_timeline_stats_short_game_only_10min_diffs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Game with only 11 frames (0-10 min) produces cs_diff_at_10 but not cs_diff_at_15."""
    timeline = load_match_timeline()
    timeline["info"]["frames"] = timeline["info"]["frames"][:11]

    detail = load_match_detail()
    match_obj = _make_match("NA1_5506397559", detail)
    fake_redis = _FakeRedis({"timeline:NA1_5506397559": json.dumps(timeline)})

    session = AsyncMock()
    monkeypatch.setattr(
        "app.services.riot_sync.get_match_by_identifier",
        AsyncMock(return_value=match_obj),
    )
    monkeypatch.setattr("app.services.riot_match_id.normalize_match_id", lambda mid: (mid, False))
    monkeypatch.setattr("app.services.cache.get_redis", lambda: fake_redis)

    result = await fetch_timeline_stats(session, "NA1_5506397559", target_participant_id=9)
    assert result is not None
    assert "cs_diff_at_10" in result
    assert "cs_diff_at_15" not in result
