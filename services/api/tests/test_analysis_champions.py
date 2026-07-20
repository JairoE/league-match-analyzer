"""Tests for account-specific AI Coach champion eligibility."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.analysis_champions import list_analyzable_champions


async def test_list_analyzable_champions_returns_scored_full_history() -> None:
    account_id = uuid4()
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {
            "champion_id": 99,
            "champion_name": "Lux",
            "scored_match_count": 16,
            "scored_action_count": 40,
            "corpus_example_count": 6,
        },
        {
            "champion_id": 12,
            "champion_name": "Alistar",
            "scored_match_count": 12,
            "scored_action_count": 35,
            "corpus_example_count": 5,
        },
    ]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    champions = await list_analyzable_champions(session, account_id)

    assert [champion.champion_name for champion in champions] == ["Lux", "Alistar"]
    assert champions[0].scored_match_count == 16
    assert champions[0].scored_action_count == 40
    assert champions[1].corpus_example_count == 5

    statement, params = session.execute.await_args.args
    sql = str(statement)
    assert "ma.participant_id = player_participant_id" in sql
    assert "ma.delta_w IS NOT NULL" in sql
    assert "analysis.embedding IS NOT NULL" in sql
    assert "ORDER BY scored_match_count DESC, champion_name ASC" in sql
    assert params == {"riot_account_id": str(account_id)}
