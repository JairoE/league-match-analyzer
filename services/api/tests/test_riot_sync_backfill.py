from __future__ import annotations

from copy import deepcopy

import pytest

from app.models.match import Match
from app.services import riot_sync
from tests.fixtures.riot_payloads import load_match_detail, load_match_ids


class _ScalarResult:
    def __init__(self, matches: list[Match]) -> None:
        self._matches = matches

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[Match]:
        return self._matches


class _FakeSession:
    def __init__(self, matches: list[Match]) -> None:
        self._matches = matches
        self.execute_calls = 0
        self.commit_calls = 0

    async def execute(self, statement: object) -> _ScalarResult:
        self.execute_calls += 1
        return _ScalarResult(self._matches)

    async def commit(self) -> None:
        self.commit_calls += 1


class _FakeRiotApiClient:
    def __init__(self, detail_template: dict[str, object]) -> None:
        self.calls: list[str] = []
        self._detail_template = detail_template

    async def __aenter__(self) -> _FakeRiotApiClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def fetch_match_by_id(self, match_id: str) -> dict[str, object]:
        self.calls.append(match_id)
        payload = deepcopy(self._detail_template)
        info = payload.get("info")
        if isinstance(info, dict):
            info["gameStartTimestamp"] = 1_700_000_000_000 + len(self.calls)
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata["matchId"] = match_id
        return payload


@pytest.mark.asyncio
async def test_backfill_by_game_ids_honors_max_fetch_above_default_20(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_match_ids = load_match_ids()
    matches = [Match(game_id=game_id) for game_id in real_match_ids[:30]]
    game_ids = [match.game_id for match in matches]
    session = _FakeSession(matches)
    fake_client = _FakeRiotApiClient(load_match_detail())

    monkeypatch.setattr(riot_sync, "RiotApiClient", lambda: fake_client)

    fetched = await riot_sync.backfill_match_details_by_game_ids(
        session,
        game_ids=game_ids,
        max_fetch=25,
    )

    assert fetched == 25
    assert session.execute_calls == 1
    assert session.commit_calls == 1
    assert len(fake_client.calls) == 25
    assert fake_client.calls == game_ids[:25]

    for match in matches[:25]:
        assert match.game_info is not None
        assert match.game_start_timestamp is not None

    for match in matches[25:]:
        assert match.game_info is None
        assert match.game_start_timestamp is None


@pytest.mark.asyncio
async def test_backfill_by_game_ids_can_fetch_all_when_max_fetch_exceeds_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_match_ids = load_match_ids()
    matches = [Match(game_id=game_id) for game_id in real_match_ids[:30]]
    game_ids = [match.game_id for match in matches]
    session = _FakeSession(matches)
    fake_client = _FakeRiotApiClient(load_match_detail())

    monkeypatch.setattr(riot_sync, "RiotApiClient", lambda: fake_client)

    fetched = await riot_sync.backfill_match_details_by_game_ids(
        session,
        game_ids=game_ids,
        max_fetch=50,
    )

    assert fetched == 30
    assert session.commit_calls == 1
    assert len(fake_client.calls) == 30
    assert fake_client.calls == game_ids

    for match in matches:
        assert match.game_info is not None
        assert match.game_start_timestamp is not None
