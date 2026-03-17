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


# ---------------------------------------------------------------------------
# Shared SQL fragments
# ---------------------------------------------------------------------------

# Derives champion_id, rank_tier, action_key from raw join of match_action + match.
_ACTION_COLUMNS = """
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
"""

_AGG_COLUMNS = """
    COALESCE(champion_id, '') AS champion_id,
    COALESCE(rank_tier, '') AS rank_tier,
    action_type,
    COALESCE(action_key, '') AS action_key,
    count(*) AS k,
    avg(delta_w) AS mean_delta_w,
    avg(pre_win_prob) AS mean_pre_win_prob,
    stddev_samp(delta_w) AS stddev_delta_w
"""


def _build_query(
    champion: str | None,
    rank_tier: str | None,
) -> tuple[str, dict[str, str]]:
    """Build a single SQL statement with personal + population CTEs.

    Returns the SQL string and a dict of extra bind params (champion/rank filters).
    The caller must also bind :riot_account_id.
    """
    filters: list[str] = []
    params: dict[str, str] = {}
    if champion is not None:
        filters.append("champion_id = :champion")
        params["champion"] = champion
    if rank_tier is not None:
        filters.append("rank_tier = :rank_tier")
        params["rank_tier"] = rank_tier

    personal_extra = (" AND " + " AND ".join(filters)) if filters else ""

    sql = f"""
WITH player_actions AS (
  SELECT
    {_ACTION_COLUMNS}
  FROM match_action ma
  JOIN match m ON ma.match_id = m.id
  JOIN riot_account_match ram
    ON ram.match_id = m.id AND ram.riot_account_id = :riot_account_id
  JOIN riot_account ra ON ra.id = ram.riot_account_id
  WHERE m.game_info IS NOT NULL
    AND ma.delta_w IS NOT NULL
    AND ma.participant_id = (
      SELECT (p2.elem->>'participantId')::int
      FROM jsonb_array_elements(m.game_info->'info'->'participants') AS p2(elem)
      WHERE p2.elem->>'puuid' = ra.puuid
      LIMIT 1
    )
),
personal_agg AS (
  SELECT
    {_AGG_COLUMNS}
  FROM player_actions
  WHERE champion_id IS NOT NULL AND champion_id != ''{personal_extra}
  GROUP BY champion_id, rank_tier, action_type, action_key
),
all_actions AS (
  SELECT
    {_ACTION_COLUMNS}
  FROM match_action ma
  JOIN match m ON ma.match_id = m.id
  WHERE m.game_info IS NOT NULL
    AND ma.delta_w IS NOT NULL
),
population_agg AS (
  SELECT
    {_AGG_COLUMNS}
  FROM all_actions
  WHERE champion_id IS NOT NULL AND champion_id != ''
    AND (champion_id, COALESCE(rank_tier, '')) IN (
      SELECT DISTINCT champion_id, rank_tier FROM personal_agg
    )
  GROUP BY champion_id, rank_tier, action_type, action_key
)
SELECT
  p.champion_id,
  p.rank_tier,
  p.action_type,
  p.action_key,
  p.k              AS personal_k,
  p.mean_delta_w   AS personal_mean_delta_w,
  p.mean_pre_win_prob AS personal_mean_pre_win_prob,
  p.stddev_delta_w AS personal_stddev_delta_w,
  COALESCE(pop.k, 0)        AS pop_k,
  pop.mean_delta_w           AS pop_mean_delta_w,
  pop.mean_pre_win_prob      AS pop_mean_pre_win_prob,
  pop.stddev_delta_w         AS pop_stddev_delta_w
FROM personal_agg p
LEFT JOIN population_agg pop
  ON  p.champion_id = pop.champion_id
  AND p.rank_tier   = pop.rank_tier
  AND p.action_type = pop.action_type
  AND p.action_key  = pop.action_key
"""
    return sql, params


def _to_float(val: object) -> float | None:
    """Coerce a DB value (Decimal/float/None) to float or None."""
    return float(val) if val is not None else None


async def aggregate_action_stats_for_player(
    session: AsyncSession,
    riot_account_id: UUID,
    champion: str | None = None,
    rank_tier: str | None = None,
) -> list[ActionAggregate]:
    """Compute per-group action stats for a player with population fallback.

    Runs a single read-only SQL statement with two CTEs: personal aggregates
    for this riot_account, and population aggregates for the same
    (champion, rank_tier) buckets.  For each group, if personal count < 50,
    marks insufficient_personal_sample and relies on population_stats.

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

    sql, filter_params = _build_query(champion, rank_tier)
    params: dict[str, str] = {"riot_account_id": str(riot_account_id)}
    params.update(filter_params)

    result = await session.execute(text(sql), params)
    rows = result.mappings().all()

    aggregates: list[ActionAggregate] = []
    for r in rows:
        k = r["personal_k"]
        aggregates.append(ActionAggregate(
            group_key=GroupKey(
                champion_id=r["champion_id"],
                rank_tier=r["rank_tier"],
                action_type=r["action_type"],
                action_key=r["action_key"],
                opponent_damage_bucket=OPPONENT_DAMAGE_BUCKET_V1,
            ),
            personal_stats=AggregateRow(
                count=k or 0,
                mean_delta_w=_to_float(r["personal_mean_delta_w"]),
                mean_pre_win_prob=_to_float(r["personal_mean_pre_win_prob"]),
                stddev_delta_w=_to_float(r["personal_stddev_delta_w"]),
            ),
            population_stats=AggregateRow(
                count=r["pop_k"] or 0,
                mean_delta_w=_to_float(r["pop_mean_delta_w"]),
                mean_pre_win_prob=_to_float(r["pop_mean_pre_win_prob"]),
                stddev_delta_w=_to_float(r["pop_stddev_delta_w"]),
            ),
            insufficient_personal_sample=k < MIN_PERSONAL_SAMPLE_SIZE,
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
