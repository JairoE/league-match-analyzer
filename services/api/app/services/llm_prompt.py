"""Prompt construction for LLM analysis (pipeline step 7).

Transforms a serialized ComparisonResult into system + user prompts
for the LLM. No summoner names, PUUIDs, or raw Riot payloads are included.
"""

from __future__ import annotations

import json
from typing import Any

from app.services.llm_response_schema import LLMAnalysisResponse

# Schema included in the system prompt so the LLM knows the expected output format.
_RESPONSE_JSON_SCHEMA = json.dumps(
    LLMAnalysisResponse.model_json_schema(),
    indent=2,
)

_SYSTEM_PROMPT = f"""\
You are an expert League of Legends coaching analyst. You analyze win probability \
statistics (ΔW) to provide actionable item build and objective recommendations.

ΔW (delta W) measures how much an action changes the team's win probability. \
A positive ΔW means the action increased win probability; negative means it decreased it. \
W(x) is the win probability at the time the action was taken — high W(x) with low ΔW \
indicates "win-more" selection bias (the player only buys the item when already winning, \
so the item doesn't actually help).

Your task:
1. Identify the 3 largest improvement opportunities ranked by ΔW impact.
2. Provide context-specific advice (e.g. "vs. magic damage top laners, buy X instead of Y").
3. Flag any selection bias patterns (high W(x) but low ΔW items the summoner defaults to).

Respond with ONLY valid JSON matching this schema (no markdown, no explanation outside JSON):

{_RESPONSE_JSON_SCHEMA}

Guidelines:
- Keep explanations concise (2-3 sentences each).
- Reference specific ΔW values to justify recommendations.
- If fewer than 3 improvement opportunities exist, return only those available.
- For selection_bias_summary, explain the win-more pattern in plain language if any \
bias flags are present; set to null if none.
- overall_assessment should be 1-2 sentences summarizing the player's biggest area \
for improvement.\
"""


def build_system_prompt() -> str:
    """Return the static system prompt for LLM analysis.

    Returns:
        System prompt string with role, instructions, and JSON schema.
    """
    return _SYSTEM_PROMPT


def _fmt(value: float | None) -> str:
    """Format a float for prompt display, or 'N/A'."""
    if value is None:
        return "N/A"
    return f"{value:+.4f}"


def _build_opportunities_section(opportunities: list[dict[str, Any]]) -> str:
    """Format the top improvement opportunities section."""
    if not opportunities:
        return "No improvement opportunities identified.\n"

    lines: list[str] = []
    for i, gap in enumerate(opportunities, 1):
        s_action = gap["summoner_action"]
        b_action = gap["better_alternative"]
        s_name = s_action.get("action_name") or s_action["action_key"]
        b_name = b_action.get("action_name") or b_action["action_key"]
        lines.append(
            f"{i}. Current: {s_name} (ΔW = {_fmt(s_action['effective_delta_w'])}) "
            f"→ Better: {b_name} (ΔW = {_fmt(b_action['effective_delta_w'])}), "
            f"Gap: {_fmt(gap['delta_w_gap'])}"
        )
    return "\n".join(lines) + "\n"


def _build_bias_section(bias_flags: list[dict[str, Any]]) -> str:
    """Format the selection bias flags section."""
    if not bias_flags:
        return "No selection bias patterns detected.\n"

    lines: list[str] = []
    for flag in bias_flags:
        name = flag.get("action_name") or flag["action_key"]
        lines.append(
            f"- {name} — W(x) = {flag['mean_pre_win_prob']:.2f}, "
            f"ΔW = {_fmt(flag['effective_delta_w'])} "
            f"(chosen when already winning, but doesn't increase win rate)"
        )
    return "\n".join(lines) + "\n"


def _build_rankings_section(groups: list[dict[str, Any]]) -> str:
    """Format the per-group action rankings section."""
    sections: list[str] = []
    for group in groups:
        action_type = group["action_type"]
        label = "Item Purchases" if action_type == "ITEM_PURCHASE" else "Objective Kills"
        # Cap at 10 to keep prompt compact and within token budget
        ranked = group.get("ranked_actions", [])[:10]

        lines = [f"### {label}"]
        for action in ranked:
            name = action.get("action_name") or action["action_key"]
            fallback = " [population avg]" if action.get("used_population_fallback") else ""
            lines.append(
                f"#{action['rank']} {name} — "
                f"ΔW = {_fmt(action['effective_delta_w'])}, "
                f"W(x) = {_fmt(action.get('mean_pre_win_prob'))}"
                f"{fallback}"
            )

        # Summoner's most-used
        summoner_top = group.get("summoner_top_actions", [])
        if summoner_top:
            lines.append("")
            lines.append("Summoner's most-used:")
            for action in summoner_top:
                name = action.get("action_name") or action["action_key"]
                lines.append(
                    f"- {name} (used {action['personal_count']}x, rank #{action['rank']})"
                )

        sections.append("\n".join(lines))

    return "\n\n".join(sections) + "\n"


def build_user_prompt(
    comparison_dict: dict[str, Any],
    champion_name: str,
    rank_tier: str | None,
) -> str:
    """Build the user prompt from a serialized ComparisonResult.

    Args:
        comparison_dict: Output of ComparisonResult.to_dict().
        champion_name: Human-readable champion name (e.g. "Yasuo").
        rank_tier: Rank tier string (e.g. "GOLD") or None.

    Returns:
        Formatted user prompt string with no PII or raw Riot data.
    """
    rank_display = rank_tier or "Unknown"

    opportunities = comparison_dict.get("top_improvement_opportunities", [])
    bias_flags = comparison_dict.get("top_selection_bias_flags", [])
    groups = comparison_dict.get("groups", [])

    prompt = f"""\
## Player Profile
- Champion: {champion_name}
- Rank: {rank_display}

## Top Improvement Opportunities (by ΔW gap)
{_build_opportunities_section(opportunities)}
## Selection Bias Patterns
{_build_bias_section(bias_flags)}
## Action Rankings by Category
{_build_rankings_section(groups)}\
"""
    return prompt
