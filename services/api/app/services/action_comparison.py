"""Compare summoner action choices against population-optimal alternatives (pipeline step 6).

Consumes step 5 ActionAggregate output, ranks actions by effective ΔW within
each (champion, rank, action_type) group, identifies improvement gaps, and
detects selection bias (high W(x) + low ΔW).

Pure synchronous logic — no DB or network I/O.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass

from app.services.action_aggregation import ActionAggregate

# Default threshold for selection bias detection (W(x) >= this value)
SELECTION_BIAS_W_THRESHOLD = 0.55


@dataclass
class RankedAction:
    """Single action within a comparison group, ranked by effective ΔW."""

    action_key: str
    action_name: str | None
    effective_delta_w: float
    personal_delta_w: float | None
    population_delta_w: float | None
    personal_count: int
    population_count: int
    mean_pre_win_prob: float | None
    used_population_fallback: bool
    rank: int


@dataclass
class SelectionBiasFlag:
    """An item flagged for high W(x) but low ΔW — win-more pattern."""

    action_key: str
    action_name: str | None
    mean_pre_win_prob: float
    effective_delta_w: float
    population_best_delta_w: float


@dataclass
class ImprovementGap:
    """A specific gap: summoner's choice vs. a better alternative."""

    summoner_action: RankedAction
    better_alternative: RankedAction
    delta_w_gap: float


@dataclass
class ComparisonGroup:
    """Comparison within one (champion, rank, action_type) bucket."""

    champion_id: str
    rank_tier: str
    action_type: str
    opponent_damage_bucket: str
    ranked_actions: list[RankedAction]
    summoner_top_actions: list[RankedAction]
    improvement_gaps: list[ImprovementGap]
    selection_bias_flags: list[SelectionBiasFlag]


@dataclass
class ComparisonResult:
    """Full comparison output for one summoner, serializable to LLM input_payload."""

    schema_version: int
    champion_id: str
    rank_tier: str
    groups: list[ComparisonGroup]
    top_improvement_opportunities: list[ImprovementGap]
    top_selection_bias_flags: list[SelectionBiasFlag]

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for LLMAnalysis.input_payload."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _effective_stats(agg: ActionAggregate) -> tuple[float, float | None, bool] | None:
    """Return (effective_delta_w, effective_mean_pre_win_prob, used_fallback) or None.

    Uses personal stats when K >= 50 (insufficient_personal_sample is False),
    otherwise falls back to population. Returns None when neither has data.
    """
    if not agg.insufficient_personal_sample and agg.personal_stats.mean_delta_w is not None:
        return (
            agg.personal_stats.mean_delta_w,
            agg.personal_stats.mean_pre_win_prob,
            False,
        )
    if agg.population_stats.mean_delta_w is not None:
        return (
            agg.population_stats.mean_delta_w,
            agg.population_stats.mean_pre_win_prob,
            True,
        )
    return None


def _resolve_name(
    action_type: str,
    action_key: str,
    item_names: dict[str, str] | None,
    objective_names: dict[str, str] | None,
) -> str | None:
    """Resolve an action_key to a human-readable name if mappings are provided."""
    if action_type == "ITEM_PURCHASE" and item_names:
        return item_names.get(action_key)
    if action_type == "OBJECTIVE_KILL" and objective_names:
        return objective_names.get(action_key)
    return None


def _build_ranked_actions(
    group_aggs: list[ActionAggregate],
    item_names: dict[str, str] | None,
    objective_names: dict[str, str] | None,
) -> list[RankedAction]:
    """Convert aggregates to ranked actions, sorted by effective ΔW descending.

    Entries where effective ΔW is None are excluded.
    """
    actions: list[RankedAction] = []
    for agg in group_aggs:
        stats = _effective_stats(agg)
        if stats is None:
            continue
        eff_dw, eff_wpre, used_fallback = stats
        actions.append(RankedAction(
            action_key=agg.group_key.action_key,
            action_name=_resolve_name(
                agg.group_key.action_type,
                agg.group_key.action_key,
                item_names,
                objective_names,
            ),
            effective_delta_w=eff_dw,
            personal_delta_w=agg.personal_stats.mean_delta_w,
            population_delta_w=agg.population_stats.mean_delta_w,
            personal_count=agg.personal_stats.count,
            population_count=agg.population_stats.count,
            mean_pre_win_prob=eff_wpre,
            used_population_fallback=used_fallback,
            rank=0,  # assigned below
        ))

    actions.sort(key=lambda a: a.effective_delta_w, reverse=True)
    for i, action in enumerate(actions):
        action.rank = i + 1

    return actions


def _detect_selection_bias(
    ranked_actions: list[RankedAction],
    threshold: float,
) -> list[SelectionBiasFlag]:
    """Flag actions with high W(x) but below-median ΔW (win-more pattern).

    Args:
        ranked_actions: Actions sorted by effective ΔW descending.
        threshold: Minimum W(x) to consider for bias flagging.

    Returns:
        List of bias flags sorted by effective ΔW ascending (worst first).
    """
    if len(ranked_actions) < 2:
        return []

    delta_ws = [a.effective_delta_w for a in ranked_actions]
    median_dw = statistics.median(delta_ws)
    best_dw = ranked_actions[0].effective_delta_w

    flags: list[SelectionBiasFlag] = []
    for action in ranked_actions:
        w = action.mean_pre_win_prob
        if (
            w is not None
            and w >= threshold
            and action.effective_delta_w < median_dw
        ):
            flags.append(SelectionBiasFlag(
                action_key=action.action_key,
                action_name=action.action_name,
                mean_pre_win_prob=w,
                effective_delta_w=action.effective_delta_w,
                population_best_delta_w=best_dw,
            ))

    return sorted(flags, key=lambda f: f.effective_delta_w)


def _compute_improvement_gaps(
    ranked_actions: list[RankedAction],
    summoner_top: list[RankedAction],
) -> list[ImprovementGap]:
    """Compute gaps between summoner's top choices and the best alternative.

    Args:
        ranked_actions: All actions sorted by effective ΔW descending.
        summoner_top: Summoner's most-used actions by personal count.

    Returns:
        Improvement gaps sorted by gap size descending (largest first).
    """
    if not ranked_actions:
        return []

    best = ranked_actions[0]
    gaps: list[ImprovementGap] = []
    for action in summoner_top:
        if action.action_key == best.action_key:
            continue
        gap = best.effective_delta_w - action.effective_delta_w
        if gap > 0:
            gaps.append(ImprovementGap(
                summoner_action=action,
                better_alternative=best,
                delta_w_gap=gap,
            ))

    return sorted(gaps, key=lambda g: g.delta_w_gap, reverse=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_action_stats(
    aggregates: list[ActionAggregate],
    *,
    item_names: dict[str, str] | None = None,
    objective_names: dict[str, str] | None = None,
    top_n_summoner_actions: int = 5,
    top_n_improvement_gaps: int = 3,
    selection_bias_w_threshold: float = SELECTION_BIAS_W_THRESHOLD,
) -> ComparisonResult | None:
    """Rank summoner's choices against optimal alternatives (pipeline step 6).

    Args:
        aggregates: Step 5 output from aggregate_action_stats_for_player.
        item_names: Optional mapping item_id -> display name (from DDragon).
        objective_names: Optional mapping monster_type -> display name.
        top_n_summoner_actions: Number of most-used summoner actions per group.
        top_n_improvement_gaps: Number of top gaps across all groups.
        selection_bias_w_threshold: W(x) threshold for selection bias flags.

    Returns:
        ComparisonResult with ranked actions and improvement gaps,
        or None if aggregates is empty.
    """
    if not aggregates:
        return None

    # Group by (champion_id, rank_tier, action_type)
    grouped: dict[tuple[str, str, str], list[ActionAggregate]] = defaultdict(list)
    for agg in aggregates:
        k = agg.group_key
        grouped[(k.champion_id, k.rank_tier, k.action_type)].append(agg)

    groups: list[ComparisonGroup] = []
    all_gaps: list[ImprovementGap] = []
    all_bias_flags: list[SelectionBiasFlag] = []

    for (champ_id, rank, action_type), group_aggs in grouped.items():
        ranked = _build_ranked_actions(group_aggs, item_names, objective_names)
        if not ranked:
            continue

        # Summoner's most-used actions by personal count
        summoner_top = sorted(ranked, key=lambda a: a.personal_count, reverse=True)[
            :top_n_summoner_actions
        ]

        gaps = _compute_improvement_gaps(ranked, summoner_top)
        bias_flags = _detect_selection_bias(ranked, selection_bias_w_threshold)

        # Use opponent_damage_bucket from the first aggregate in the group
        odm = group_aggs[0].group_key.opponent_damage_bucket

        groups.append(ComparisonGroup(
            champion_id=champ_id,
            rank_tier=rank,
            action_type=action_type,
            opponent_damage_bucket=odm,
            ranked_actions=ranked,
            summoner_top_actions=summoner_top,
            improvement_gaps=gaps,
            selection_bias_flags=bias_flags,
        ))

        all_gaps.extend(gaps)
        all_bias_flags.extend(bias_flags)

    if not groups:
        return None

    # Cross-group top gaps and bias flags
    top_gaps = sorted(all_gaps, key=lambda g: g.delta_w_gap, reverse=True)[
        :top_n_improvement_gaps
    ]
    top_bias = sorted(all_bias_flags, key=lambda f: f.effective_delta_w)

    # Use first group's champion/rank for top-level context
    first = groups[0]

    return ComparisonResult(
        schema_version=1,
        champion_id=first.champion_id,
        rank_tier=first.rank_tier,
        groups=groups,
        top_improvement_opportunities=top_gaps,
        top_selection_bias_flags=top_bias,
    )
