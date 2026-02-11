from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from app.services.riot_api_client import RiotApiClient, RiotRequestError


class _FakeRateLimiter:
    async def wait_if_needed(self, bucket: str) -> None:
        return None

    def update_from_headers(self, bucket: str, headers: dict[str, str]) -> None:
        return None

    def set_retry_after(self, seconds: float) -> None:
        return None


class _ScriptedClient:
    def __init__(self, scripted_responses: Sequence[httpx.Response | Exception]) -> None:
        self._scripted = list(scripted_responses)
        self.calls = 0

    async def get(self, url: str, headers: dict[str, str]) -> httpx.Response:
        self.calls += 1
        next_item = self._scripted.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


def _response(status_code: int, payload: dict[str, Any], url: str) -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, json=payload, request=request)


@pytest.mark.asyncio
async def test_riot_client_retries_5xx_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    url = "https://americas.api.riotgames.com/lol/match/v5/matches/NA1_1"
    scripted = _ScriptedClient(
        [
            _response(500, {"status": "error"}, url),
            _response(200, {"matchId": "NA1_1"}, url),
        ]
    )

    sleeps: list[float] = []
    metric_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def _fake_metric(*args: object, **kwargs: object) -> None:
        metric_calls.append((args, kwargs))

    client = RiotApiClient(rate_limiter=_FakeRateLimiter())
    client._settings = client._settings.model_copy(deep=True)
    client._settings.riot_api_key = "test-key"

    async def _fake_get_client(timeout: httpx.Timeout) -> _ScriptedClient:
        return scripted

    monkeypatch.setattr(client, "_get_client", _fake_get_client)
    monkeypatch.setattr("app.services.riot_api_client.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("app.services.riot_api_client.increment_metric_safe", _fake_metric)

    payload = await client.fetch_match_by_id("NA1_1")

    assert payload["matchId"] == "NA1_1"
    assert scripted.calls == 2
    assert len(sleeps) == 1
    assert any(
        kwargs.get("tags", {}).get("type") == "5xx"
        for _, kwargs in metric_calls
        if isinstance(kwargs.get("tags"), dict)
    )
    assert any(record.message == "riot_request_start" for record in caplog.records)


@pytest.mark.asyncio
async def test_riot_client_retries_network_then_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    url = "https://americas.api.riotgames.com/lol/match/v5/matches/NA1_2"
    request = httpx.Request("GET", url)
    scripted = _ScriptedClient(
        [
            httpx.RequestError("socket timeout", request=request),
            httpx.RequestError("socket timeout", request=request),
        ]
    )

    sleeps: list[float] = []
    metric_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def _fake_metric(*args: object, **kwargs: object) -> None:
        metric_calls.append((args, kwargs))

    client = RiotApiClient(rate_limiter=_FakeRateLimiter())
    client._settings = client._settings.model_copy(deep=True)
    client._settings.riot_api_key = "test-key"
    client.MAX_RETRIES = 1

    async def _fake_get_client(timeout: httpx.Timeout) -> _ScriptedClient:
        return scripted

    monkeypatch.setattr(client, "_get_client", _fake_get_client)
    monkeypatch.setattr("app.services.riot_api_client.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("app.services.riot_api_client.increment_metric_safe", _fake_metric)

    with pytest.raises(RiotRequestError) as exc_info:
        await client.fetch_match_by_id("NA1_2")

    assert exc_info.value.status == 502
    assert scripted.calls == 2
    assert len(sleeps) == 1
    assert any(
        kwargs.get("tags", {}).get("type") == "network"
        for _, kwargs in metric_calls
        if isinstance(kwargs.get("tags"), dict)
    )
    assert any(
        record.message == "riot_request_network_retry" for record in caplog.records
    )
