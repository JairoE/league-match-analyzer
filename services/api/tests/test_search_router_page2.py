"""Tests for search router page-2+ path and RiotRequestError HTTP mapping.

Covers: page 2 DB-only path, 404 when account missing, and
RiotRequestError → proper HTTP status conversion on page 1.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.routers import search
from app.services.riot_api_client import RiotRequestError

# ── Helpers ───────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def refresh(self, obj: object) -> None:
        pass


# ── Page 2+ tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_page2_skips_riot_api_and_queries_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Page 2 should resolve account from DB — no Riot API calls."""
    riot_account = SimpleNamespace(id=uuid4())
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    riot_api_called = False

    class _NoCallClient:
        async def __aenter__(self) -> _NoCallClient:
            return self

        async def __aexit__(self, *a: object) -> bool:
            return False

        async def fetch_account_by_riot_id(self, *a: object) -> dict:
            nonlocal riot_api_called
            riot_api_called = True
            return {}

    list_calls: list[tuple[int, int]] = []

    async def _fake_get_riot_account(session: object, riot_id: str) -> SimpleNamespace:
        return riot_account

    async def _fake_list_matches(
        session: object,
        riot_account_id: object,
        page: int,
        limit: int,
        **kwargs: object,
    ) -> tuple[list[object], int]:
        list_calls.append((page, limit))
        return [], 40

    monkeypatch.setattr(search, "RiotApiClient", lambda: _NoCallClient())
    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get_riot_account)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list_matches)

    response = await search.search_riot_account_matches(
        riot_id="damanjr#NA1",
        background_tasks=background_tasks,
        page=2,
        limit=20,
        after=0,
        session=session,  # type: ignore[arg-type]
    )

    assert not riot_api_called
    assert response.meta.page == 2
    assert response.meta.total == 40
    assert list_calls == [(2, 20)]
    assert session.commit_calls == 0
    assert len(background_tasks.tasks) == 0


@pytest.mark.asyncio
async def test_search_page3_returns_correct_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Page 3 with limit=10 should reflect correct pagination metadata."""
    riot_account = SimpleNamespace(id=uuid4())
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    async def _fake_get(session: object, riot_id: str) -> SimpleNamespace:
        return riot_account

    async def _fake_list(
        session: object, rid: object, page: int, limit: int, **kwargs: object
    ) -> tuple[list[object], int]:
        return [], 50

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list)

    response = await search.search_riot_account_matches(
        riot_id="damanjr#NA1",
        background_tasks=background_tasks,
        page=3,
        limit=10,
        after=0,
        session=session,  # type: ignore[arg-type]
    )

    assert response.meta.page == 3
    assert response.meta.limit == 10
    assert response.meta.total == 50
    assert response.meta.last_page == 5


@pytest.mark.asyncio
async def test_search_page2_404_when_account_not_in_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Page 2+ with no DB account should raise 404."""
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    async def _fake_get(session: object, riot_id: str) -> None:
        return None

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get)

    with pytest.raises(HTTPException) as exc_info:
        await search.search_riot_account_matches(
            riot_id="nobody#NA1",
            background_tasks=background_tasks,
            page=2,
            limit=20,
            after=0,
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Riot account not found"


# ── RiotRequestError HTTP mapping tests ──────────────────────────────


class _ErrorRiotClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aenter__(self) -> _ErrorRiotClient:
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def fetch_account_by_riot_id(self, *a: object) -> dict:
        raise self._exc


@pytest.mark.asyncio
async def test_search_page1_riot_404_maps_to_http_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Riot 404 should become HTTP 404."""
    session = _FakeSession()
    background_tasks = BackgroundTasks()
    exc = RiotRequestError("riot_api_failed", status=404)

    monkeypatch.setattr(search, "RiotApiClient", lambda: _ErrorRiotClient(exc))

    with pytest.raises(HTTPException) as exc_info:
        await search.search_riot_account_matches(
            riot_id="notfound#NA1",
            background_tasks=background_tasks,
            page=1,
            limit=20,
            after=0,
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_search_page1_riot_429_maps_to_http_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Riot 429 (rate limited) should become HTTP 429."""
    session = _FakeSession()
    background_tasks = BackgroundTasks()
    exc = RiotRequestError("riot_api_failed", status=429)

    monkeypatch.setattr(search, "RiotApiClient", lambda: _ErrorRiotClient(exc))

    with pytest.raises(HTTPException) as exc_info:
        await search.search_riot_account_matches(
            riot_id="ratelimited#NA1",
            background_tasks=background_tasks,
            page=1,
            limit=20,
            after=0,
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_search_page1_riot_500_maps_to_http_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Riot 5xx should become HTTP 502 (bad gateway)."""
    session = _FakeSession()
    background_tasks = BackgroundTasks()
    exc = RiotRequestError("riot_api_failed", status=500)

    monkeypatch.setattr(search, "RiotApiClient", lambda: _ErrorRiotClient(exc))

    with pytest.raises(HTTPException) as exc_info:
        await search.search_riot_account_matches(
            riot_id="servererr#NA1",
            background_tasks=background_tasks,
            page=1,
            limit=20,
            after=0,
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_search_account_riot_401_maps_to_http_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Riot 401 on /account endpoint should become HTTP 401."""
    session = _FakeSession()
    exc = RiotRequestError("missing_riot_api_key", status=401)

    monkeypatch.setattr(search, "RiotApiClient", lambda: _ErrorRiotClient(exc))

    with pytest.raises(HTTPException) as exc_info:
        await search.search_riot_account(
            riot_id="nokey#NA1",
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "missing_riot_api_key"
