from __future__ import annotations

from tests.fixtures.riot_payloads import (
    fixture_meta,
    load_account_info,
    load_match_detail,
    load_match_ids,
    load_match_timeline,
    load_summoner_info,
)


def test_riot_fixture_contract_core_keys_present() -> None:
    meta = fixture_meta()
    account_info = load_account_info()
    summoner_info = load_summoner_info()
    match_ids = load_match_ids()
    match_detail = load_match_detail()
    match_timeline = load_match_timeline()

    assert "puuid" in account_info
    assert "gameName" in account_info
    assert "tagLine" in account_info
    assert account_info["puuid"] == meta["puuid"]

    assert "puuid" in summoner_info
    assert "profileIconId" in summoner_info
    assert "summonerLevel" in summoner_info
    assert summoner_info["puuid"] == meta["puuid"]

    assert isinstance(match_ids, list)
    assert len(match_ids) > 0
    assert meta["primary_match_id"] in match_ids

    assert "metadata" in match_detail
    assert "matchId" in match_detail["metadata"]
    assert match_detail["metadata"]["matchId"] == meta["primary_match_id"]

    assert "metadata" in match_timeline
    assert "matchId" in match_timeline["metadata"]
    assert match_timeline["metadata"]["matchId"] == meta["primary_match_id"]
