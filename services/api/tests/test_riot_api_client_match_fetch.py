"""Tests for RiotApiClient.fetch_match_by_id and fetch_match_timeline.

Verifies that:
- fetch_match_by_id hits /lol/match/v5/matches/{matchId} and returns the payload.
- fetch_match_timeline hits /lol/match/v5/matches/{matchId}/timeline and returns the payload.
- Both methods derive the URL from the same matchId, so the timeline URL is exactly
  the match detail URL with '/timeline' appended.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.services.riot_api_client import RiotApiClient, RiotRequestError


# ---------------------------------------------------------------------------
# Test helpers (mirrors the pattern in test_riot_api_client_retry.py)
# ---------------------------------------------------------------------------


class _FakeRateLimiter:
    async def wait_if_needed(self, bucket: str) -> None:
        return None

    def update_from_headers(self, bucket: str, headers: dict[str, str]) -> None:
        return None

    def set_retry_after(self, seconds: float) -> None:
        return None


class _ScriptedClient:
    """Fake httpx client that replays scripted responses and records calls."""

    def __init__(self, scripted_responses: list[httpx.Response | Exception]) -> None:
        self._scripted = list(scripted_responses)
        self.calls: int = 0
        self.last_url: str | None = None

    async def get(self, url: str, headers: dict[str, str]) -> httpx.Response:
        self.calls += 1
        self.last_url = url
        item = self._scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(url: str, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", url))


def _make_client(monkeypatch: pytest.MonkeyPatch, scripted: _ScriptedClient) -> RiotApiClient:
    """Return a RiotApiClient wired to *scripted* with a dummy API key."""
    client = RiotApiClient(rate_limiter=_FakeRateLimiter())
    client._settings = client._settings.model_copy(deep=True)
    client._settings.riot_api_key = "test-key"

    async def _fake_get_client(timeout: httpx.Timeout) -> _ScriptedClient:
        return scripted

    monkeypatch.setattr(client, "_get_client", _fake_get_client)
    monkeypatch.setattr("app.services.riot_api_client.increment_metric_safe", _noop_metric)
    return client


async def _noop_metric(*args: object, **kwargs: object) -> None:
    pass


# ---------------------------------------------------------------------------
# fetch_match_by_id
# ---------------------------------------------------------------------------

MATCH_ID = "NA1_5089485769"
MATCH_DETAIL_URL = f"https://americas.api.riotgames.com/lol/match/v5/matches/{MATCH_ID}"
MATCH_TIMELINE_URL = f"https://americas.api.riotgames.com/lol/match/v5/matches/{MATCH_ID}/timeline"

MATCH_PAYLOAD: dict[str, Any] = {
    "metadata": {"matchId": MATCH_ID, "participants": ["puuid-1", "puuid-2"]},
    "info": {
        "gameDuration": 1800,
        "gameMode": "CLASSIC",
        "participants": [
            {
                "participantId": 1,
                "championName": "Ahri",
                "teamId": 100,
                "individualPosition": "MIDDLE",
                "riotIdGameName": "Player1",
            }
        ],
    },
}

TIMELINE_PAYLOAD: dict[str, Any] = {
    "metadata": {"matchId": MATCH_ID},
    "info": {
        "frameInterval": 60000,
        "frames": [],
        # Timeline participants only carry participantId + puuid (no position/team)
        "participants": [
            {"participantId": 1, "puuid": "puuid-1"},
        ],
    },
}


@pytest.mark.asyncio
async def test_fetch_match_by_id_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_match_by_id returns the full match payload from a 200 response."""
    scripted = _ScriptedClient([_ok(MATCH_DETAIL_URL, MATCH_PAYLOAD)])
    client = _make_client(monkeypatch, scripted)

    result = await client.fetch_match_by_id(MATCH_ID)

    assert result == MATCH_PAYLOAD
    assert scripted.calls == 1


@pytest.mark.asyncio
async def test_fetch_match_by_id_calls_correct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_match_by_id calls /lol/match/v5/matches/{matchId} (no /timeline suffix)."""
    scripted = _ScriptedClient([_ok(MATCH_DETAIL_URL, MATCH_PAYLOAD)])
    client = _make_client(monkeypatch, scripted)

    await client.fetch_match_by_id(MATCH_ID)

    assert scripted.last_url == MATCH_DETAIL_URL
    assert "/timeline" not in (scripted.last_url or "")


@pytest.mark.asyncio
async def test_fetch_match_timeline_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_match_timeline returns the full timeline payload from a 200 response."""
    scripted = _ScriptedClient([_ok(MATCH_TIMELINE_URL, TIMELINE_PAYLOAD)])
    client = _make_client(monkeypatch, scripted)

    result = await client.fetch_match_timeline(MATCH_ID)

    assert result == TIMELINE_PAYLOAD
    assert scripted.calls == 1


@pytest.mark.asyncio
async def test_fetch_match_timeline_calls_correct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_match_timeline calls /lol/match/v5/matches/{matchId}/timeline."""
    scripted = _ScriptedClient([_ok(MATCH_TIMELINE_URL, TIMELINE_PAYLOAD)])
    client = _make_client(monkeypatch, scripted)

    await client.fetch_match_timeline(MATCH_ID)

    assert scripted.last_url == MATCH_TIMELINE_URL
    assert scripted.last_url is not None and scripted.last_url.endswith("/timeline")


@pytest.mark.asyncio
async def test_match_detail_and_timeline_share_same_match_id_in_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The timeline URL is exactly the match detail URL with '/timeline' appended.

    This guarantees both endpoints are querying the same Riot match, so the
    timeline-stats route and the /matches/{matchId} route are always in sync.
    """
    detail_scripted = _ScriptedClient([_ok(MATCH_DETAIL_URL, MATCH_PAYLOAD)])
    timeline_scripted = _ScriptedClient([_ok(MATCH_TIMELINE_URL, TIMELINE_PAYLOAD)])

    detail_client = _make_client(monkeypatch, detail_scripted)
    # monkeypatch is per-test so we patch the second client independently
    timeline_client = RiotApiClient(rate_limiter=_FakeRateLimiter())
    timeline_client._settings = timeline_client._settings.model_copy(deep=True)
    timeline_client._settings.riot_api_key = "test-key"

    async def _fake_get_timeline_client(timeout: httpx.Timeout) -> _ScriptedClient:
        return timeline_scripted

    monkeypatch.setattr(timeline_client, "_get_client", _fake_get_timeline_client)

    await detail_client.fetch_match_by_id(MATCH_ID)
    await timeline_client.fetch_match_timeline(MATCH_ID)

    assert detail_scripted.last_url is not None
    assert timeline_scripted.last_url is not None
    # The timeline URL must be the detail URL + /timeline — same matchId, no UUID drift.
    assert timeline_scripted.last_url == detail_scripted.last_url + "/timeline"
