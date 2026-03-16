"""Aggregate match action ΔW statistics for pipeline step 5.

Read-only SQL aggregations on match_action joined to match and riot_account_match.
Groups by champion, rank_tier, action_type, action_key, opponent_damage_bucket.
Enforces K ≥ 50 for personal stats and provides population fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger("league_api.services.action_aggregation")

# Minimum sample size for reliable personal stats (per thesis Section 4.2)
MIN_PERSONAL_SAMPLE_SIZE = 50

# V1: single bucket; derive physical/magic from opponent champs in a later iteration
OPPONENT_DAMAGE_BUCKET_V1 = "mixed"


@dataclass
class GroupKey:
    """Dimensions for aggregation grouping."""

    champion_id: str
    rank_tier: str
    action_type: str
    action_key: str
    opponent_damage_bucket: str


@dataclass
class AggregateRow:
    """Per-group aggregate statistics."""

    count: int
    mean_delta_w: float | None
    mean_pre_win_prob: float | None
    stddev_delta_w: float | None


@dataclass
class ActionAggregate:
    """Merged view: personal (if K≥50) + population fallback for same bucket.

    Attributes:
        group_key: Champion, rank, action type, action key, opponent bucket.
        personal_stats: This player's aggregate stats for this group.
        population_stats: All players' aggregate stats for same bucket (fallback).
        insufficient_personal_sample: True when personal count < 50; use population.
    """

    group_key: GroupKey
    personal_stats: AggregateRow
    population_stats: AggregateRow
    insufficient_personal_sample: bool


def _row_to_aggregate_row(
    count: int,
    mean_delta_w: float | None,
    mean_pre_win_prob: float | None,
    stddev_delta_w: float | None,
) -> AggregateRow:
    """Build AggregateRow from raw SQL result (stddev can be None for single row)."""
    return AggregateRow(
        count=count or 0,
        mean_delta_w=float(mean_delta_w) if mean_delta_w is not None else None,
        mean_pre_win_prob=(
            float(mean_pre_win_prob) if mean_pre_win_prob is not None else None
        ),
        stddev_delta_w=(
            float(stddev_delta_w) if stddev_delta_w is not None else None
        ),
    )


# CTE: this player's actions with derived dimensions (champion, rank, action_key).
# Filters to scored rows (delta_w IS NOT NULL) and participant = account's puuid.
_PERSONAL_CTE = """
WITH player_actions AS (
  SELECT
    ma.action_type,
    ma.delta_w,
    ma.pre_win_prob,
    (SELECT p.elem->>'championId'
     FROM jsonb_array_elements(m.game_info->'info'->'participants') AS p(elem)
     WHERE (p.elem->>'participantId')::int = ma.participant_id
     LIMIT 1) AS champion_id,
    (SELECT msv.features->>'average_rank'
     FROM match_state_vector msv
     WHERE msv.match_id = m.id
     ORDER BY msv.minute ASC
     LIMIT 1) AS rank_tier,
    CASE ma.action_type
      WHEN 'ITEM_PURCHASE' THEN ma.action_detail->>'item_id'
      WHEN 'OBJECTIVE_KILL' THEN ma.action_detail->>'monster_type'
      ELSE 'unknown'
    END AS action_key
  FROM match_action ma
  JOIN match m ON ma.match_id = m.id
  JOIN riot_account_match ram ON ram.match_id = m.id AND ram.riot_account_id = :riot_account_id
  JOIN riot_account ra ON ra.id = ram.riot_account_id
  WHERE m.game_info IS NOT NULL
    AND ma.delta_w IS NOT NULL
    AND ma.participant_id = (
      SELECT (p2.elem->>'participantId')::int
      FROM jsonb_array_elements(m.game_info->'info'->'participants') AS p2(elem)
      WHERE p2.elem->>'puuid' = ra.puuid
      LIMIT 1
    )
)
SELECT
  COALESCE(champion_id, '') AS champion_id,
  COALESCE(rank_tier, '') AS rank_tier,
  action_type,
  COALESCE(action_key, '') AS action_key,
  count(*) AS k,
  avg(delta_w) AS mean_delta_w,
  avg(pre_win_prob) AS mean_pre_win_prob,
  stddev_samp(delta_w) AS stddev_delta_w
FROM player_actions
WHERE champion_id IS NOT NULL AND champion_id != ''
GROUP BY champion_id, rank_tier, action_type, action_key
"""


def _build_personal_sql(champion: str | None, rank_tier: str | None) -> tuple[str, dict]:
    """Build personal aggregation SQL and params with optional filters."""
    sql = _PERSONAL_CTE.rstrip()
    extra_where: list[str] = []
    params: dict = {}
    if champion is not None:
        extra_where.append("champion_id = :champion")
        params["champion"] = champion
    if rank_tier is not None:
        extra_where.append("rank_tier = :rank_tier")
        params["rank_tier"] = rank_tier
    if extra_where:
        sql = sql.replace(
            "WHERE champion_id IS NOT NULL AND champion_id != ''\nGROUP BY",
            "WHERE champion_id IS NOT NULL AND champion_id != '' AND "
            + " AND ".join(extra_where)
            + "\nGROUP BY",
        )
    return sql, params

# Population: same dimensions but all participants (no riot_account filter).
# Restricted to (champion_id, rank_tier) pairs from the player's data.
# Placeholder: {champion_rank_in_clause} is replaced with expanded (c, r) IN ((:c0,:r0),...).
_POPULATION_CTE_TEMPLATE = """
WITH all_actions AS (
  SELECT
    ma.action_type,
    ma.delta_w,
    ma.pre_win_prob,
    (SELECT p.elem->>'championId'
     FROM jsonb_array_elements(m.game_info->'info'->'participants') AS p(elem)
     WHERE (p.elem->>'participantId')::int = ma.participant_id
     LIMIT 1) AS champion_id,
    (SELECT msv.features->>'average_rank'
     FROM match_state_vector msv
     WHERE msv.match_id = m.id
     ORDER BY msv.minute ASC
     LIMIT 1) AS rank_tier,
    CASE ma.action_type
      WHEN 'ITEM_PURCHASE' THEN ma.action_detail->>'item_id'
      WHEN 'OBJECTIVE_KILL' THEN ma.action_detail->>'monster_type'
      ELSE 'unknown'
    END AS action_key
  FROM match_action ma
  JOIN match m ON ma.match_id = m.id
  WHERE m.game_info IS NOT NULL
    AND ma.delta_w IS NOT NULL
)
SELECT
  COALESCE(champion_id, '') AS champion_id,
  COALESCE(rank_tier, '') AS rank_tier,
  action_type,
  COALESCE(action_key, '') AS action_key,
  count(*) AS k,
  avg(delta_w) AS mean_delta_w,
  avg(pre_win_prob) AS mean_pre_win_prob,
  stddev_samp(delta_w) AS stddev_delta_w
FROM all_actions
WHERE champion_id IS NOT NULL AND champion_id != ''
  AND (champion_id, rank_tier) IN ({champion_rank_in_clause})
GROUP BY champion_id, rank_tier, action_type, action_key
"""


def _build_population_sql(
    champion_rank_pairs: list[tuple[str, str]],
) -> tuple[str, dict]:
    """Build population SQL with expanded (champion_id, rank_tier) IN bind params."""
    if not champion_rank_pairs:
        return "", {}
    placeholders = [
        f"(:cr_c{i}, :cr_r{i})" for i in range(len(champion_rank_pairs))
    ]
    params = {}
    for i, (c, r) in enumerate(champion_rank_pairs):
        params[f"cr_c{i}"] = c
        params[f"cr_r{i}"] = r
    sql = _POPULATION_CTE_TEMPLATE.format(
        champion_rank_in_clause=", ".join(placeholders)
    )
    return sql, params


async def aggregate_action_stats_for_player(
    session: AsyncSession,
    riot_account_id: UUID,
    champion: str | None = None,
    rank_tier: str | None = None,
) -> list[ActionAggregate]:
    """Compute per-group action stats for a player with population fallback.

    Runs read-only SQL: (1) personal aggregates for this riot_account,
    (2) population aggregates for the same (champion, rank_tier) buckets.
    For each group, if personal count < 50, marks insufficient_personal_sample
    and relies on population_stats.

    Args:
        session: Async database session.
        riot_account_id: Riot account UUID.
        champion: Optional filter by champion_id (e.g. "157").
        rank_tier: Optional filter by rank tier (e.g. "GOLD").

    Returns:
        List of ActionAggregate with merged personal/population view.
    """
    logger.info(
        "aggregate_action_stats_start",
        extra={
            "riot_account_id": str(riot_account_id),
            "champion_filter": champion,
            "rank_tier_filter": rank_tier,
        },
    )

    params: dict = {"riot_account_id": str(riot_account_id)}
    personal_sql, filter_params = _build_personal_sql(champion, rank_tier)
    params.update(filter_params)

    result = await session.execute(text(personal_sql), params)
    personal_rows = result.mappings().all()

    # Build list of (champion_id, rank_tier) for population query
    champion_rank_pairs = list(
        {(r["champion_id"], r["rank_tier"]) for r in personal_rows}
    )
    if not champion_rank_pairs:
        logger.info(
            "aggregate_action_stats_no_personal_data",
            extra={"riot_account_id": str(riot_account_id)},
        )
        return []

    # Population query with expanded (champion_id, rank_tier) IN bind params
    pop_sql, pop_params = _build_population_sql(champion_rank_pairs)
    if not pop_sql:
        return []
    pop_result = await session.execute(text(pop_sql), pop_params)
    population_rows = {(
        r["champion_id"],
        r["rank_tier"],
        r["action_type"],
        r["action_key"],
    ): r for r in pop_result.mappings().all()}

    aggregates: list[ActionAggregate] = []
    for r in personal_rows:
        key = GroupKey(
            champion_id=r["champion_id"],
            rank_tier=r["rank_tier"],
            action_type=r["action_type"],
            action_key=r["action_key"],
            opponent_damage_bucket=OPPONENT_DAMAGE_BUCKET_V1,
        )
        k = r["k"]
        personal_stats = _row_to_aggregate_row(
            k,
            r["mean_delta_w"],
            r["mean_pre_win_prob"],
            r["stddev_delta_w"],
        )
        insufficient = k < MIN_PERSONAL_SAMPLE_SIZE

        pop_key = (key.champion_id, key.rank_tier, key.action_type, key.action_key)
        pop_row = population_rows.get(pop_key)
        population_stats = (
            _row_to_aggregate_row(
                pop_row["k"],
                pop_row["mean_delta_w"],
                pop_row["mean_pre_win_prob"],
                pop_row["stddev_delta_w"],
            )
            if pop_row
            else AggregateRow(0, None, None, None)
        )

        aggregates.append(ActionAggregate(
            group_key=key,
            personal_stats=personal_stats,
            population_stats=population_stats,
            insufficient_personal_sample=insufficient,
        ))

    logger.info(
        "aggregate_action_stats_done",
        extra={
            "riot_account_id": str(riot_account_id),
            "group_count": len(aggregates),
            "insufficient_count": sum(
                1 for a in aggregates if a.insufficient_personal_sample
            ),
        },
    )
    return aggregates
