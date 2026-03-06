from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.riot_account import RiotAccount
from app.services.riot_account_upsert import upsert_riot_account
from tests.fixtures.riot_payloads import load_summoner_info


class _ScalarResult:
    def __init__(self, value: RiotAccount | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> RiotAccount | None:
        return self._value


class _NestedTx:
    async def __aenter__(self) -> _NestedTx:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False


class _FakeSession:
    def __init__(self, retry_account: RiotAccount) -> None:
        self.retry_account = retry_account
        self.execute_calls = 0
        self.flush_calls = 0
        self.add_calls = 0

    async def execute(self, statement):  # type: ignore[no-untyped-def]
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _ScalarResult(None)
        return _ScalarResult(self.retry_account)

    def add(self, obj):  # type: ignore[no-untyped-def]
        self.add_calls += 1

    def begin_nested(self) -> _NestedTx:
        return _NestedTx()

    async def flush(self) -> None:
        self.flush_calls += 1
        if self.flush_calls == 1:
            raise IntegrityError(
                "INSERT INTO riot_account ...",
                params={},
                orig=Exception("duplicate key value violates unique constraint"),
            )


@pytest.mark.asyncio
async def test_upsert_riot_account_recovers_from_insert_race() -> None:
    summoner_info = load_summoner_info()
    existing = RiotAccount(
        riot_id="Teemo#NA1",
        puuid="puuid-123",
        summoner_name="OldName",
        profile_icon_id=1,
        summoner_level=10,
    )
    session = _FakeSession(retry_account=existing)

    account = await upsert_riot_account(
        session,
        riot_id="Teemo#NA1",
        puuid="puuid-123",
        summoner_info={
            "profileIconId": summoner_info["profileIconId"],
            "summonerLevel": summoner_info["summonerLevel"],
        },
    )

    assert account is existing
    assert account.summoner_name == "Teemo"
    assert account.profile_icon_id == summoner_info["profileIconId"]
    assert account.summoner_level == summoner_info["summonerLevel"]
    # First flush fails during insert race, second flush persists updates.
    assert session.flush_calls == 2
