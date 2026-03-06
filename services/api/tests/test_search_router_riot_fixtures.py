from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from app.api.routers import search
from tests.fixtures.riot_payloads import load_account_info, load_match_ids, load_summoner_info


class _FakeRiotApiClient:
    def __init__(
        self,
        account_info: dict[str, object],
        summoner_info: dict[str, object],
        match_ids: list[str],
    ) -> None:
        self.account_info = account_info
        self.summoner_info = summoner_info
        self.match_ids = match_ids
        self.account_calls: list[tuple[str, str]] = []
        self.summoner_calls: list[str] = []
        self.match_ids_calls: list[tuple[str, int, int]] = []

    async def __aenter__(self) -> _FakeRiotApiClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def fetch_account_by_riot_id(self, game_name: str, tag_line: str) -> dict[str, object]:
        self.account_calls.append((game_name, tag_line))
        return self.account_info

    async def fetch_summoner_by_puuid(self, puuid: str) -> dict[str, object]:
        self.summoner_calls.append(puuid)
        return self.summoner_info

    async def fetch_match_ids_by_puuid(self, puuid: str, start: int, count: int) -> list[str]:
        self.match_ids_calls.append((puuid, start, count))
        return self.match_ids[:count]


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.refresh_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def refresh(self, obj: object) -> None:
        self.refresh_calls += 1


@pytest.mark.asyncio
async def test_search_matches_page1_uses_captured_riot_payload_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_info = load_account_info()
    summoner_info = load_summoner_info()
    match_ids = load_match_ids()
    fake_client = _FakeRiotApiClient(account_info, summoner_info, match_ids)
    session = _FakeSession()
    riot_account = SimpleNamespace(id=uuid4())
    background_tasks = BackgroundTasks()

    upsert_calls: list[tuple[object, object, list[str]]] = []
    backfill_calls: list[tuple[object, list[str], int]] = []
    list_calls: list[tuple[object, object, int, int]] = []

    async def _fake_find_or_create_riot_account(
        db_session: object,
        riot_id: str,
        puuid: str,
        summoner_info: dict[str, object],
    ) -> SimpleNamespace:
        assert riot_id == "damanjr#NA1"
        assert puuid == account_info["puuid"]
        assert summoner_info == load_summoner_info()
        return riot_account

    async def _fake_upsert_matches(
        db_session: object,
        riot_account_id: object,
        incoming_match_ids: list[str],
    ) -> None:
        upsert_calls.append((db_session, riot_account_id, incoming_match_ids))

    async def _fake_backfill(
        db_session: object,
        incoming_match_ids: list[str],
        max_fetch: int = 20,
    ) -> int:
        backfill_calls.append((db_session, incoming_match_ids, max_fetch))
        return len(incoming_match_ids)

    async def _fake_list_matches(
        db_session: object,
        riot_account_id: object,
        page: int,
        limit: int,
    ) -> tuple[list[object], int]:
        list_calls.append((db_session, riot_account_id, page, limit))
        return [], 0

    monkeypatch.setattr(search, "RiotApiClient", lambda: fake_client)
    monkeypatch.setattr(search, "find_or_create_riot_account", _fake_find_or_create_riot_account)
    monkeypatch.setattr(search, "upsert_matches_for_riot_account", _fake_upsert_matches)
    monkeypatch.setattr(search, "backfill_match_details_by_game_ids", _fake_backfill)
    monkeypatch.setattr(search, "list_matches_for_riot_account", _fake_list_matches)

    response = await search.search_riot_account_matches(
        riot_id="damanjr#NA1",
        background_tasks=background_tasks,
        page=1,
        limit=5,
        session=session,  # type: ignore[arg-type]
    )

    assert response.meta.page == 1
    assert response.meta.limit == 5
    assert response.meta.total == 0
    assert response.data == []

    assert fake_client.account_calls == [("damanjr", "NA1")]
    assert fake_client.summoner_calls == [str(account_info["puuid"])]
    assert fake_client.match_ids_calls == [(str(account_info["puuid"]), 0, 5)]

    assert session.commit_calls == 1
    assert session.refresh_calls == 1
    assert len(upsert_calls) == 1
    assert len(backfill_calls) == 1
    assert len(list_calls) == 1
    assert upsert_calls[0][2] == match_ids[:5]
    assert backfill_calls[0][1] == match_ids[:5]
    assert backfill_calls[0][2] == 5
    assert list_calls[0][2:] == (1, 5)

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is search.enqueue_missing_timeline_jobs
    assert task.args == (match_ids[:5],)
