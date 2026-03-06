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
    """Fake session mirroring the real query: game_id IN (game_ids) AND game_info IS NULL."""

    def __init__(self, matches: list[Match], game_ids: list[str] | None = None) -> None:
        self._matches = matches
        self._game_ids: set[str] | None = set(game_ids) if game_ids is not None else None
        self.execute_calls = 0
        self.commit_calls = 0

    async def execute(self, statement: object) -> _ScalarResult:
        self.execute_calls += 1
        missing = [
            m
            for m in self._matches
            if not m.game_info
            and (self._game_ids is None or m.game_id in self._game_ids)
        ]
        return _ScalarResult(missing)

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
    session = _FakeSession(matches, game_ids=game_ids)
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
    session = _FakeSession(matches, game_ids=game_ids)
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


@pytest.mark.asyncio
async def test_backfill_by_game_ids_skips_already_backfilled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matches that already have game_info should not be re-fetched."""
    real_match_ids = load_match_ids()
    matches = [Match(game_id=game_id) for game_id in real_match_ids[:5]]
    # Pre-fill first 2 matches so the fake session filters them out
    for m in matches[:2]:
        m.game_info = {"info": {"gameStartTimestamp": 1}}
        m.game_start_timestamp = 1
    game_ids = [match.game_id for match in matches]
    session = _FakeSession(matches, game_ids=game_ids)
    fake_client = _FakeRiotApiClient(load_match_detail())

    monkeypatch.setattr(riot_sync, "RiotApiClient", lambda: fake_client)

    fetched = await riot_sync.backfill_match_details_by_game_ids(
        session, game_ids=game_ids, max_fetch=10
    )

    assert fetched == 3  # only the 3 matches without game_info
    assert len(fake_client.calls) == 3


@pytest.mark.asyncio
async def test_backfill_by_game_ids_ignores_matches_outside_requested_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """game_id IN (...) filter must exclude matches not in the requested set."""
    real_match_ids = load_match_ids()
    # Create 8 matches; only the first 5 are in the requested game_ids.
    # The remaining 3 are present in the session but must NOT be backfilled.
    all_matches = [Match(game_id=game_id) for game_id in real_match_ids[:8]]
    requested_game_ids = [m.game_id for m in all_matches[:5]]

    # Session holds all 8 rows (simulates a DB that has extra unrelated rows)
    session = _FakeSession(all_matches, game_ids=requested_game_ids)
    fake_client = _FakeRiotApiClient(load_match_detail())

    monkeypatch.setattr(riot_sync, "RiotApiClient", lambda: fake_client)

    fetched = await riot_sync.backfill_match_details_by_game_ids(
        session, game_ids=requested_game_ids, max_fetch=10
    )

    # Only the 5 requested matches should be backfilled
    assert fetched == 5
    assert len(fake_client.calls) == 5
    assert set(fake_client.calls) == set(requested_game_ids)

    for match in all_matches[:5]:
        assert match.game_info is not None, f"{match.game_id} should have been backfilled"

    for match in all_matches[5:]:
        assert match.game_info is None, f"{match.game_id} outside game_ids should be untouched"
