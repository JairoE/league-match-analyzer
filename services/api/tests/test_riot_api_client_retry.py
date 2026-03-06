from __future__ import annotations

import logging

import httpx
import pytest

from app.services.riot_api_client import RiotApiClient, RiotRequestError
from tests.fixtures.fake_riot_helpers import (
    FakeRateLimiter,
    ScriptedClient,
    error_response,
    ok_response,
)
from tests.fixtures.riot_payloads import fixture_meta, load_match_detail


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    scripted: ScriptedClient,
    *,
    max_retries: int | None = None,
) -> RiotApiClient:
    """Return a RiotApiClient wired to *scripted* with a dummy API key."""
    sleeps: list[float] = []
    metric_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def _fake_metric(*args: object, **kwargs: object) -> None:
        metric_calls.append((args, kwargs))

    client = RiotApiClient(rate_limiter=FakeRateLimiter())
    client._settings = client._settings.model_copy(deep=True)
    client._settings.riot_api_key = "test-key"
    if max_retries is not None:
        client.MAX_RETRIES = max_retries

    async def _fake_get_client(timeout: httpx.Timeout) -> ScriptedClient:
        return scripted

    monkeypatch.setattr(client, "_get_client", _fake_get_client)
    monkeypatch.setattr("app.services.riot_api_client.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("app.services.riot_api_client.increment_metric_safe", _fake_metric)

    client._test_sleeps = sleeps  # type: ignore[attr-defined]
    client._test_metric_calls = metric_calls  # type: ignore[attr-defined]
    return client


@pytest.mark.asyncio
async def test_riot_client_retries_5xx_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    match_id = str(fixture_meta()["primary_match_id"])
    url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}"
    match_payload = load_match_detail()
    scripted = ScriptedClient(
        [
            error_response(500, url, match_payload),
            ok_response(url, match_payload),
        ]
    )

    client = _make_client(monkeypatch, scripted)

    payload = await client.fetch_match_by_id(match_id)

    assert payload["metadata"]["matchId"] == match_id
    assert scripted.calls == 2
    assert len(client._test_sleeps) == 1  # type: ignore[attr-defined]
    assert any(
        kwargs.get("tags", {}).get("type") == "5xx"
        for _, kwargs in client._test_metric_calls  # type: ignore[attr-defined]
        if isinstance(kwargs.get("tags"), dict)
    )
    assert any(record.message == "riot_request_start" for record in caplog.records)


@pytest.mark.asyncio
async def test_riot_client_retries_network_then_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    match_id = str(fixture_meta()["primary_match_id"])
    url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}"
    request = httpx.Request("GET", url)
    scripted = ScriptedClient(
        [
            httpx.RequestError("socket timeout", request=request),
            httpx.RequestError("socket timeout", request=request),
        ]
    )

    client = _make_client(monkeypatch, scripted, max_retries=1)

    with pytest.raises(RiotRequestError) as exc_info:
        await client.fetch_match_by_id(match_id)

    assert exc_info.value.status == 502
    assert scripted.calls == 2
    assert len(client._test_sleeps) == 1  # type: ignore[attr-defined]
    assert any(
        kwargs.get("tags", {}).get("type") == "network"
        for _, kwargs in client._test_metric_calls  # type: ignore[attr-defined]
        if isinstance(kwargs.get("tags"), dict)
    )
    assert any(
        record.message == "riot_request_network_retry" for record in caplog.records
    )
