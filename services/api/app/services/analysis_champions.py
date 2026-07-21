"""Account-specific champion eligibility for AI Coach analysis."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger("league_api.services.analysis_champions")


@dataclass(frozen=True)
class AnalyzableChampion:
    """A champion with player-specific scored actions for one account."""

    champion_id: int
    champion_name: str
    scored_match_count: int
    scored_action_count: int
    corpus_example_count: int


async def list_analyzable_champions(
    session: AsyncSession,
    riot_account_id: UUID,
) -> list[AnalyzableChampion]:
    """List champions supported by an account's full scored match history.

    Args:
        session: Async database session.
        riot_account_id: Account UUID.

    Returns:
        Eligible champions ordered by scored match count, then name.
    """
    logger.info(
        "list_analyzable_champions_start",
        extra={"riot_account_id": str(riot_account_id)},
    )
    query = text("""
        WITH player_matches AS (
          SELECT
            m.id AS match_id,
            (player.elem->>'participantId')::int AS player_participant_id,
            (player.elem->>'championId')::int AS champion_id
          FROM riot_account ra
          JOIN riot_account_match ram ON ram.riot_account_id = ra.id
          JOIN match m ON m.id = ram.match_id
          CROSS JOIN LATERAL (
            SELECT participant.elem
            FROM jsonb_array_elements(
              m.game_info->'info'->'participants'
            ) AS participant(elem)
            WHERE participant.elem->>'puuid' = ra.puuid
            LIMIT 1
          ) AS player
          WHERE ra.id = :riot_account_id
        ),
        scored_champions AS (
          SELECT
            pm.champion_id,
            COUNT(DISTINCT pm.match_id)::int AS scored_match_count,
            COUNT(*)::int AS scored_action_count
          FROM player_matches pm
          JOIN match_action ma
            ON ma.match_id = pm.match_id
           AND ma.participant_id = player_participant_id
          WHERE ma.delta_w IS NOT NULL
          GROUP BY pm.champion_id
        ),
        embedded_corpus AS (
          SELECT
            analysis.champion_name,
            COUNT(*) FILTER (
              WHERE analysis.embedding IS NOT NULL
            )::int AS corpus_example_count
          FROM llm_analysis AS analysis
          GROUP BY analysis.champion_name
        )
        SELECT
          champion.champ_id AS champion_id,
          champion.name AS champion_name,
          scored.scored_match_count,
          scored.scored_action_count,
          COALESCE(corpus.corpus_example_count, 0)::int AS corpus_example_count
        FROM scored_champions scored
        JOIN champion ON champion.champ_id = scored.champion_id
        LEFT JOIN embedded_corpus corpus
          ON corpus.champion_name = champion.name
        ORDER BY scored_match_count DESC, champion_name ASC
    """)
    result = await session.execute(
        query,
        {"riot_account_id": str(riot_account_id)},
    )
    champions = [
        AnalyzableChampion(
            champion_id=row["champion_id"],
            champion_name=row["champion_name"],
            scored_match_count=row["scored_match_count"],
            scored_action_count=row["scored_action_count"],
            corpus_example_count=row["corpus_example_count"],
        )
        for row in result.mappings().all()
    ]
    logger.info(
        "list_analyzable_champions_done",
        extra={
            "riot_account_id": str(riot_account_id),
            "champion_count": len(champions),
        },
    )
    return champions
