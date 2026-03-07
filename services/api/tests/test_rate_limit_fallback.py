"""Tests for 429 rate-limit graceful degradation: return cached data with stale signal."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.routers import matches, search
from app.services.riot_api_client import RiotRequestError

# ── Helpers ─────────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def refresh(self, obj: object) -> None:
        pass


def _make_match_like(game_id: str = "NA1_1") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        game_id=game_id,
        game_start_timestamp=12345,
        game_info=None,
    )


# ── matches.py: 429 + cached matches → 200, meta.stale ────────────────────


class _MatchesRiotClient429:
    """Riot client that raises 429 on fetch_match_ids_by_puuid (used when refresh=true)."""

    async def __aenter__(self) -> _MatchesRiotClient429:
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def fetch_match_ids_by_puuid(self, *a: object, **kw: object) -> list:
        raise RiotRequestError("rate_limited", status=429)


@pytest.mark.asyncio
async def test_matches_429_with_cached_matches_returns_200_and_stale_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On 429 during refresh, fall back to DB; return 200 and meta.stale when cached."""
    account_id = str(uuid4())
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-1")
    cached = [_make_match_like("NA1_1"), _make_match_like("NA1_2")]

    async def _resolve_account(session: object, rid: str) -> SimpleNamespace | None:
        return riot_account

    async def _list_matches(
        session: object,
        rid: object,
        page: int,
        limit: int,
        **kwargs: object,
    ) -> tuple[list, int]:
        return cached, 2

    monkeypatch.setattr(matches, "RiotApiClient", lambda: _MatchesRiotClient429())
    monkeypatch.setattr(matches, "resolve_riot_account_identifier", _resolve_account)
    monkeypatch.setattr(matches, "list_matches_for_riot_account", _list_matches)

    response = await matches.list_riot_account_matches(
        riot_account_id=account_id,
        background_tasks=BackgroundTasks(),
        page=1,
        limit=20,
        after=0,
        refresh=True,
        session=_FakeSession(),  # type: ignore[arg-type]
    )

    assert response.meta.stale is True
    assert response.meta.stale_reason == "rate_limited"
    assert len(response.data) == 2


@pytest.mark.asyncio
async def test_matches_429_with_no_cached_data_returns_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On 429 during refresh with no cached matches, return 429."""
    account_id = str(uuid4())
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-1")

    async def _resolve_account(session: object, rid: str) -> SimpleNamespace | None:
        return riot_account

    async def _list_matches(
        session: object,
        rid: object,
        page: int,
        limit: int,
        **kwargs: object,
    ) -> tuple[list, int]:
        return [], 0

    monkeypatch.setattr(matches, "RiotApiClient", lambda: _MatchesRiotClient429())
    monkeypatch.setattr(matches, "resolve_riot_account_identifier", _resolve_account)
    monkeypatch.setattr(matches, "list_matches_for_riot_account", _list_matches)

    with pytest.raises(HTTPException) as exc_info:
        await matches.list_riot_account_matches(
            riot_account_id=account_id,
            background_tasks=BackgroundTasks(),
            page=1,
            limit=20,
            after=0,
            refresh=True,
            session=_FakeSession(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "riot_api_max_retries_exceeded"


class _MatchesRiotClient404:
    """Riot client that raises 404 on fetch_match_ids_by_puuid."""

    async def __aenter__(self) -> _MatchesRiotClient404:
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def fetch_match_ids_by_puuid(self, *a: object, **kw: object) -> list:
        raise RiotRequestError("riot_api_failed", status=404)


@pytest.mark.asyncio
async def test_matches_non_429_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-429 RiotRequestError during refresh is not caught; propagates."""
    account_id = str(uuid4())
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-1")

    async def _resolve_account(session: object, rid: str) -> SimpleNamespace | None:
        return riot_account

    monkeypatch.setattr(matches, "RiotApiClient", lambda: _MatchesRiotClient404())
    monkeypatch.setattr(matches, "resolve_riot_account_identifier", _resolve_account)

    with pytest.raises(RiotRequestError):
        await matches.list_riot_account_matches(
            riot_account_id=account_id,
            background_tasks=BackgroundTasks(),
            page=1,
            limit=20,
            after=0,
            refresh=True,
            session=_FakeSession(),  # type: ignore[arg-type]
        )


# ── search.py: 429 + cached account+matches → 200, meta.stale ───────────


class _ErrorRiotClient:
    """Riot client that raises on account or match-ID fetch (for search 429 tests)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aenter__(self) -> _ErrorRiotClient:
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def fetch_account_by_riot_id(self, *a: object) -> dict:
        raise self._exc

    async def fetch_match_ids_by_puuid(self, *a: object, **kw: object) -> list:
        raise self._exc


def _client_429() -> _ErrorRiotClient:
    return _ErrorRiotClient(RiotRequestError("rate_limited", status=429))


@pytest.mark.asyncio
async def test_search_429_with_cached_account_and_matches_returns_200_and_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On 429 during refresh, use DB and return cached matches with meta.stale."""
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-1")
    cached = [_make_match_like("NA1_1"), _make_match_like("NA1_2")]

    monkeypatch.setattr(search, "RiotApiClient", _client_429)

    async def _fake_get_account(session: object, riot_id: str) -> SimpleNamespace | None:
        return riot_account

    async def _fake_list(
        session: object, rid: object, page: int, limit: int, **kwargs: object
    ) -> tuple[list, int]:
        return cached, 2

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get_account)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list)

    response = await search.search_riot_account_matches(
        riot_id="cached#NA1",
        background_tasks=BackgroundTasks(),
        page=1,
        limit=20,
        after=0,
        refresh=True,
        session=_FakeSession(),  # type: ignore[arg-type]
    )

    assert response.meta.stale is True
    assert response.meta.stale_reason == "rate_limited"
    assert len(response.data) == 2


@pytest.mark.asyncio
async def test_search_429_with_no_cached_account_returns_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On 429 with account not in DB (first-ever search), return 429."""
    monkeypatch.setattr(search, "RiotApiClient", _client_429)

    async def _fake_get_none(session: object, riot_id: str) -> None:
        return None

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get_none)

    with pytest.raises(HTTPException) as exc_info:
        await search.search_riot_account_matches(
            riot_id="newuser#NA1",
            background_tasks=BackgroundTasks(),
            page=1,
            limit=20,
            after=0,
            session=_FakeSession(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "riot_api_max_retries_exceeded"


@pytest.mark.asyncio
async def test_search_429_with_account_but_zero_matches_returns_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On 429 during refresh with account in DB but 0 matches cached, return 429."""
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-1")

    monkeypatch.setattr(search, "RiotApiClient", _client_429)

    async def _fake_get_account(session: object, riot_id: str) -> SimpleNamespace | None:
        return riot_account

    async def _fake_list_empty(
        session: object, rid: object, page: int, limit: int, **kwargs: object
    ) -> tuple[list, int]:
        return [], 0

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get_account)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list_empty)

    with pytest.raises(HTTPException) as exc_info:
        await search.search_riot_account_matches(
            riot_id="empty#NA1",
            background_tasks=BackgroundTasks(),
            page=1,
            limit=20,
            after=0,
            refresh=True,
            session=_FakeSession(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "riot_api_max_retries_exceeded"
