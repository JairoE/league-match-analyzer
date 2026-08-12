"""Tests for the /riot-accounts/{id}/matches refresh ingest path.

Focus: a refresh (fresh match IDs) must schedule BOTH timeline caching and
timeline extraction+scoring, so recently-played champions become eligible for
AI Coach (their match_action rows get delta_w populated) instead of only
having their timeline warmed in Redis.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from app.api.routers import matches


class _FakeRiotApiClient:
    def __init__(self, match_ids: list[str]) -> None:
        self.match_ids = match_ids

    async def __aenter__(self) -> _FakeRiotApiClient:
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def fetch_match_ids_by_puuid(
        self, puuid: str, start: int, count: int
    ) -> list[str]:
        return self.match_ids[:count]


class _FakeSession:
    async def commit(self) -> None:  # pragma: no cover - unused here
        pass

    async def refresh(self, obj: object) -> None:  # pragma: no cover - unused here
        pass


class _FakeRateLimiter:
    async def is_globally_backing_off(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_refresh_schedules_timeline_and_extraction_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh=true (page 1) enqueues both timeline and extraction background tasks."""
    match_ids = ["NA1_1", "NA1_2", "NA1_3"]
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-abc")
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    async def _fake_resolve(db_session: object, identifier: str) -> SimpleNamespace:
        return riot_account

    async def _fake_upsert(
        db_session: object, riot_account_id: object, incoming: list[str]
    ) -> None:
        return None

    async def _fake_backfill(
        db_session: object, incoming: list[str], max_fetch: int = 20
    ) -> int:
        return len(incoming)

    async def _fake_list_matches(
        db_session: object,
        riot_account_id: object,
        page: int,
        limit: int,
        **kwargs: object,
    ) -> tuple[list[object], int]:
        return [], 0

    monkeypatch.setattr(matches, "resolve_riot_account_identifier", _fake_resolve)
    monkeypatch.setattr(matches, "RiotApiClient", lambda: _FakeRiotApiClient(match_ids))
    monkeypatch.setattr(matches, "upsert_matches_for_riot_account", _fake_upsert)
    monkeypatch.setattr(matches, "backfill_match_details_by_game_ids", _fake_backfill)
    monkeypatch.setattr(matches, "list_matches_for_riot_account", _fake_list_matches)
    monkeypatch.setattr(matches, "get_rate_limiter", lambda: _FakeRateLimiter())

    await matches.list_riot_account_matches(
        riot_account_id=str(riot_account.id),
        background_tasks=background_tasks,
        page=1,
        limit=20,
        after=0,
        year=None,
        refresh=True,
        session=session,  # type: ignore[arg-type]
    )

    assert len(background_tasks.tasks) == 2
    timeline_task, extraction_task = background_tasks.tasks
    assert timeline_task.func is matches.enqueue_missing_timeline_jobs
    assert timeline_task.args == (match_ids,)
    assert extraction_task.func is matches.enqueue_missing_extraction_jobs
    assert extraction_task.args == (match_ids,)


@pytest.mark.asyncio
async def test_no_refresh_schedules_no_ingest_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without refresh (page 1, no see-more) no fresh IDs are fetched, so no tasks."""
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-abc")
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    async def _fake_resolve(db_session: object, identifier: str) -> SimpleNamespace:
        return riot_account

    async def _fake_list_matches(
        db_session: object,
        riot_account_id: object,
        page: int,
        limit: int,
        **kwargs: object,
    ) -> tuple[list[object], int]:
        return [], 0

    monkeypatch.setattr(matches, "resolve_riot_account_identifier", _fake_resolve)
    monkeypatch.setattr(matches, "list_matches_for_riot_account", _fake_list_matches)
    monkeypatch.setattr(matches, "get_rate_limiter", lambda: _FakeRateLimiter())

    await matches.list_riot_account_matches(
        riot_account_id=str(riot_account.id),
        background_tasks=background_tasks,
        page=1,
        limit=20,
        after=0,
        year=None,
        refresh=False,
        session=session,  # type: ignore[arg-type]
    )

    assert len(background_tasks.tasks) == 0
