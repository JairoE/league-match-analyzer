"""Shared fakes for Riot API client tests.

Provides reusable _FakeRateLimiter and _ScriptedClient so test modules
don't duplicate these helpers.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx


class FakeRateLimiter:
    """No-op rate limiter for unit tests."""

    async def wait_if_needed(self, bucket: str) -> None:
        return None

    def update_from_headers(self, bucket: str, headers: dict[str, str]) -> None:
        return None

    async def set_retry_after(self, seconds: float) -> None:
        return None


class ScriptedClient:
    """Fake httpx client that replays scripted responses and records calls."""

    def __init__(self, scripted_responses: Sequence[httpx.Response | Exception]) -> None:
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


def ok_response(url: str, payload: dict[str, Any]) -> httpx.Response:
    """Build a 200 httpx.Response with *payload* as JSON body."""
    return httpx.Response(200, json=payload, request=httpx.Request("GET", url))


def error_response(
    status_code: int,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build an httpx.Response with the given status code."""
    return httpx.Response(
        status_code, json=payload, headers=headers, request=httpx.Request("GET", url)
    )


async def noop_metric(*args: object, **kwargs: object) -> None:
    pass
