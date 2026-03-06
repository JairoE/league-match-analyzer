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

from app.services.riot_api_client import RiotApiClient
from tests.fixtures.fake_riot_helpers import (
    FakeRateLimiter,
    ScriptedClient,
    noop_metric,
    ok_response,
)
from tests.fixtures.riot_payloads import (
    fixture_meta,
    load_match_detail,
    load_match_timeline,
)


def _make_client(monkeypatch: pytest.MonkeyPatch, scripted: ScriptedClient) -> RiotApiClient:
    """Return a RiotApiClient wired to *scripted* with a dummy API key."""
    client = RiotApiClient(rate_limiter=FakeRateLimiter())
    client._settings = client._settings.model_copy(deep=True)
    client._settings.riot_api_key = "test-key"

    async def _fake_get_client(timeout: httpx.Timeout) -> ScriptedClient:
        return scripted

    monkeypatch.setattr(client, "_get_client", _fake_get_client)
    monkeypatch.setattr("app.services.riot_api_client.increment_metric_safe", noop_metric)
    return client


@pytest.fixture()
def match_fixtures() -> dict[str, Any]:
    """Load fixture data lazily — only when a test actually needs it."""
    meta = fixture_meta()
    match_id = str(meta["primary_match_id"])
    return {
        "match_id": match_id,
        "detail_url": f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}",
        "timeline_url": (
            f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        ),
        "match_payload": load_match_detail(),
        "timeline_payload": load_match_timeline(),
    }


@pytest.mark.asyncio
async def test_fetch_match_by_id_returns_payload(
    monkeypatch: pytest.MonkeyPatch, match_fixtures: dict[str, Any]
) -> None:
    """fetch_match_by_id returns the full match payload from a 200 response."""
    fx = match_fixtures
    scripted = ScriptedClient([ok_response(fx["detail_url"], fx["match_payload"])])
    client = _make_client(monkeypatch, scripted)

    result = await client.fetch_match_by_id(fx["match_id"])

    assert result == fx["match_payload"]
    assert scripted.calls == 1
    print(
        f"[test_match_payload] match_id={MATCH_ID} -> "
        f"payload keys: {list(result.keys())} | HTTP calls: {scripted.calls}"
    )


@pytest.mark.asyncio
async def test_fetch_match_by_id_calls_correct_url(
    monkeypatch: pytest.MonkeyPatch, match_fixtures: dict[str, Any]
) -> None:
    """fetch_match_by_id calls /lol/match/v5/matches/{matchId} (no /timeline suffix)."""
    fx = match_fixtures
    scripted = ScriptedClient([ok_response(fx["detail_url"], fx["match_payload"])])
    client = _make_client(monkeypatch, scripted)

    await client.fetch_match_by_id(fx["match_id"])

    assert scripted.last_url == fx["detail_url"]
    assert "/timeline" not in (scripted.last_url or "")
    print(f"[test_match_url] Called: {scripted.last_url} (no /timeline suffix)")


@pytest.mark.asyncio
async def test_fetch_match_timeline_returns_payload(
    monkeypatch: pytest.MonkeyPatch, match_fixtures: dict[str, Any]
) -> None:
    """fetch_match_timeline returns the full timeline payload from a 200 response."""
    fx = match_fixtures
    scripted = ScriptedClient([ok_response(fx["timeline_url"], fx["timeline_payload"])])
    client = _make_client(monkeypatch, scripted)

    result = await client.fetch_match_timeline(fx["match_id"])

    assert result == fx["timeline_payload"]
    assert scripted.calls == 1
    print(
        f"[test_timeline_payload] match_id={MATCH_ID} -> "
        f"payload keys: {list(result.keys())} | HTTP calls: {scripted.calls}"
    )


@pytest.mark.asyncio
async def test_fetch_match_timeline_calls_correct_url(
    monkeypatch: pytest.MonkeyPatch, match_fixtures: dict[str, Any]
) -> None:
    """fetch_match_timeline calls /lol/match/v5/matches/{matchId}/timeline."""
    fx = match_fixtures
    scripted = ScriptedClient([ok_response(fx["timeline_url"], fx["timeline_payload"])])
    client = _make_client(monkeypatch, scripted)

    await client.fetch_match_timeline(fx["match_id"])

    assert scripted.last_url == fx["timeline_url"]
    assert scripted.last_url is not None and scripted.last_url.endswith("/timeline")
    print(f"[test_timeline_url] Called: {scripted.last_url} (ends with /timeline)")


@pytest.mark.asyncio
async def test_match_detail_and_timeline_share_same_match_id_in_url(
    monkeypatch: pytest.MonkeyPatch, match_fixtures: dict[str, Any]
) -> None:
    """The timeline URL is exactly the match detail URL with '/timeline' appended.

    This guarantees both endpoints are querying the same Riot match, so the
    timeline-stats route and the /matches/{matchId} route are always in sync.
    """
    fx = match_fixtures
    detail_scripted = ScriptedClient([ok_response(fx["detail_url"], fx["match_payload"])])
    timeline_scripted = ScriptedClient(
        [ok_response(fx["timeline_url"], fx["timeline_payload"])]
    )

    detail_client = _make_client(monkeypatch, detail_scripted)
    timeline_client = RiotApiClient(rate_limiter=FakeRateLimiter())
    timeline_client._settings = timeline_client._settings.model_copy(deep=True)
    timeline_client._settings.riot_api_key = "test-key"

    async def _fake_get_timeline_client(timeout: httpx.Timeout) -> ScriptedClient:
        return timeline_scripted

    monkeypatch.setattr(timeline_client, "_get_client", _fake_get_timeline_client)

    await detail_client.fetch_match_by_id(fx["match_id"])
    await timeline_client.fetch_match_timeline(fx["match_id"])

    assert detail_scripted.last_url is not None
    assert timeline_scripted.last_url is not None
    assert timeline_scripted.last_url == detail_scripted.last_url + "/timeline"
    print(
        f"[test_url_consistency] Detail:   {detail_scripted.last_url}\n"
        f"                       Timeline: {timeline_scripted.last_url}\n"
        f"                       timeline == detail + '/timeline': True"
    )
