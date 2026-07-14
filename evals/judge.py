"""LLM-as-judge rubric for retrieved few-shot example quality.

Scores each (query, retrieved examples) pair on three 1-5 axes:
- relevance: do the examples describe a similar coaching situation?
- factuality: are the example recommendations internally consistent
  with the stats they cite?
- completeness: do the examples cover the query's improvement themes?

Calibrate against your own judgments on 10-20 cases before trusting
aggregates (see evals/README.md).
"""

from __future__ import annotations

import json
from typing import Any

JUDGE_SYSTEM_PROMPT = """\
You are grading the retrieval quality of a RAG system inside a League of \
Legends coaching app. Given a QUERY (a player's analysis context) and the \
RETRIEVED EXAMPLES (past coaching analyses injected as few-shot examples), \
score the retrieved set on three axes, each an integer from 1 (poor) to 5 \
(excellent):

- relevance: how well the examples match the query's champion, rank, and \
improvement themes.
- factuality: whether each example's recommendations are internally \
consistent with the stats it cites (no contradictions or fabricated-looking \
numbers).
- completeness: whether the set covers the query's main improvement themes \
or leaves obvious gaps.

Respond with JSON only:
{"relevance": <1-5>, "factuality": <1-5>, "completeness": <1-5>, \
"rationale": "<one or two sentences>"}
"""


def build_judge_user_prompt(
    query_text: str,
    examples: list[dict[str, Any]],
) -> str:
    """Format the query context and retrieved examples for the judge.

    Args:
        query_text: Compact embedding text of the query analysis.
        examples: Output of format_few_shot_examples() for the retrieved set.

    Returns:
        Judge user prompt.
    """
    lines = [f"QUERY: {query_text}", "", "RETRIEVED EXAMPLES:"]
    if not examples:
        lines.append("(none retrieved)")
    for index, example in enumerate(examples, start=1):
        lines.append(
            f"{index}. {example.get('champion_name')} "
            f"({example.get('rank_tier')}) — "
            f"assessment: {example.get('overall_assessment') or 'n/a'}"
        )
        for rec in (example.get("recommendations") or [])[:3]:
            if isinstance(rec, dict):
                lines.append(
                    f"   - {rec.get('title')}: {rec.get('current_choice')} -> "
                    f"{rec.get('recommended_choice')} "
                    f"(gap {rec.get('delta_w_gap')})"
                )
    return "\n".join(lines)


def parse_judge_response(content: str) -> dict[str, Any] | None:
    """Parse and validate the judge's JSON, clamping scores to 1-5.

    Returns:
        {relevance, factuality, completeness, rationale} or None on
        malformed output.
    """
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    scores: dict[str, Any] = {}
    for axis in ("relevance", "factuality", "completeness"):
        value = payload.get(axis)
        if not isinstance(value, int | float):
            return None
        scores[axis] = max(1, min(5, int(value)))
    scores["rationale"] = str(payload.get("rationale") or "")
    return scores
