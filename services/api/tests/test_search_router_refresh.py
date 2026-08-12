"""Tests for the /search/{riot_id}/matches refresh ingest path.

Focus: `_refresh_matches_if_requested` is the ingest site reached when an
account already exists in the DB and the caller passes refresh=true (or
after > 0, the "see more" pagination path). The riot-account page that hosts
the AI Coach card builds its refresh URL through exactly this branch
(league-web/src/app/riot-account/[riotId]/page.tsx), so a regression here
silently breaks "Refresh" on that page.

Mirrors the honest style of test_matches_router_refresh.py: it does NOT
patch the enqueue helpers themselves. It asserts identity on the queued
task funcs (`background_tasks.tasks[i].func is search.enqueue_missing_*`),
so deleting the production `background_tasks.add_task(...)` call fails
these tests instead of silently passing.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from app.api.routers import search


class _FakeRiotApiClient:
    def __init__(self, match_ids: list[str]) -> None:
        self.match_ids = match_ids
        self.calls: list[tuple[str, int, int]] = []

    async def __aenter__(self) -> _FakeRiotApiClient:
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def fetch_match_ids_by_puuid(
        self, puuid: str, start: int, count: int
    ) -> list[str]:
        self.calls.append((puuid, start, count))
        return self.match_ids[:count]


class _FakeSession:
    async def commit(self) -> None:  # pragma: no cover - unused on refresh path
        pass

    async def refresh(self, obj: object) -> None:  # pragma: no cover - unused
        pass


@pytest.mark.asyncio
async def test_refresh_schedules_timeline_and_extraction_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh=true (page 1, existing account) enqueues both ingest jobs, in order."""
    match_ids = ["NA1_1", "NA1_2"]
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-abc")
    fake_client = _FakeRiotApiClient(match_ids)
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    async def _fake_get_account(db_session: object, riot_id: str) -> SimpleNamespace:
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

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get_account)
    monkeypatch.setattr(search, "RiotApiClient", lambda: fake_client)
    monkeypatch.setattr(search, "upsert_matches_for_riot_account", _fake_upsert)
    monkeypatch.setattr(search, "backfill_match_details_by_game_ids", _fake_backfill)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list_matches)

    await search.search_riot_account_matches(
        riot_id="damanjr#NA1",
        background_tasks=background_tasks,
        page=1,
        limit=20,
        after=0,
        year=None,
        refresh=True,
        session=session,  # type: ignore[arg-type]
    )

    assert fake_client.calls == [("puuid-abc", 0, 20)]
    assert len(background_tasks.tasks) == 2
    timeline_task, extraction_task = background_tasks.tasks
    assert timeline_task.func is search.enqueue_missing_timeline_jobs
    assert timeline_task.args == (match_ids,)
    assert extraction_task.func is search.enqueue_missing_extraction_jobs
    assert extraction_task.args == (match_ids,)


@pytest.mark.asyncio
async def test_see_more_after_offset_schedules_timeline_and_extraction_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """after > 0 ("see more") also fetches fresh IDs and enqueues both ingest jobs."""
    match_ids = ["NA1_3", "NA1_4", "NA1_5"]
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-xyz")
    fake_client = _FakeRiotApiClient(match_ids)
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    async def _fake_get_account(db_session: object, riot_id: str) -> SimpleNamespace:
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

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get_account)
    monkeypatch.setattr(search, "RiotApiClient", lambda: fake_client)
    monkeypatch.setattr(search, "upsert_matches_for_riot_account", _fake_upsert)
    monkeypatch.setattr(search, "backfill_match_details_by_game_ids", _fake_backfill)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list_matches)

    await search.search_riot_account_matches(
        riot_id="damanjr#NA1",
        background_tasks=background_tasks,
        page=1,
        limit=20,
        after=5,
        year=None,
        refresh=False,
        session=session,  # type: ignore[arg-type]
    )

    assert fake_client.calls == [("puuid-xyz", 5, 20)]
    assert len(background_tasks.tasks) == 2
    timeline_task, extraction_task = background_tasks.tasks
    assert timeline_task.func is search.enqueue_missing_timeline_jobs
    assert timeline_task.args == (match_ids,)
    assert extraction_task.func is search.enqueue_missing_extraction_jobs
    assert extraction_task.args == (match_ids,)


@pytest.mark.asyncio
async def test_refresh_with_no_new_ids_schedules_no_ingest_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """refresh=true but Riot returns no new match IDs: no tasks are queued at all."""
    riot_account = SimpleNamespace(id=uuid4(), puuid="puuid-empty")
    fake_client = _FakeRiotApiClient([])
    session = _FakeSession()
    background_tasks = BackgroundTasks()

    async def _fake_get_account(db_session: object, riot_id: str) -> SimpleNamespace:
        return riot_account

    async def _fake_list_matches(
        db_session: object,
        riot_account_id: object,
        page: int,
        limit: int,
        **kwargs: object,
    ) -> tuple[list[object], int]:
        return [], 0

    monkeypatch.setattr(search, "get_riot_account_by_riot_id", _fake_get_account)
    monkeypatch.setattr(search, "RiotApiClient", lambda: fake_client)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list_matches)

    await search.search_riot_account_matches(
        riot_id="damanjr#NA1",
        background_tasks=background_tasks,
        page=1,
        limit=20,
        after=0,
        year=None,
        refresh=True,
        session=session,  # type: ignore[arg-type]
    )

    assert fake_client.calls == [("puuid-empty", 0, 20)]
    assert len(background_tasks.tasks) == 0
