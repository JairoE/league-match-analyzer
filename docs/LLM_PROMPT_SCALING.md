# LLM Prompt Scaling & Token Budget

How the LLM analysis pipeline (steps 5-8) handles data growth, where prompt size is capped, and what to watch as the system scales.

## Core Insight: Aggregation Absorbs Match Volume

The Step 5 SQL query (`aggregate_action_stats_for_player`) groups by `(champion_id, rank_tier, action_type, action_key)`. Scoring 100 or 10,000 matches with the same item produces **one aggregate row** with averaged stats (`mean_delta_w`, `mean_pre_win_prob`, `stddev_delta_w`, `count`). More matches improve statistical quality without adding rows to the prompt.

## What Drives Prompt Size

The primary variable is **unique action_keys per (champion, rank, action_type) group** — i.e., how many distinct items or objectives the player has used on that champion at that rank.

## Caps by Pipeline Layer

| Layer | Source | What grows | Cap |
|-------|--------|-----------|-----|
| Step 5 (Aggregate) | `action_aggregation.py` | Unique `(champion, rank, action_type, action_key)` rows | **None** |
| Step 6 (Compare) | `action_comparison.py` | `ranked_actions` per group | **None** |
| Step 6 (Compare) | `action_comparison.py:247` | `summoner_top_actions` per group | **5** (`top_n_summoner_actions`) |
| Step 6 (Compare) | `action_comparison.py:248` | Cross-group improvement gaps | **3** (`top_n_improvement_gaps`) |
| Step 6 (Compare) | `action_comparison.py:166-202` | Selection bias flags | **None** |
| Step 7 (Prompt) | `llm_prompt.py:108` | Ranked actions shown per group | **10** (`ranked[:10]`) |
| Step 7 (Prompt) | `llm_prompt.py:66-82` | Improvement opportunities section | **3** (inherited from Step 6) |
| Step 7 (Prompt) | `llm_prompt.py:85-98` | Selection bias section | **None** (all flags rendered) |

## Current Prompt Budget (V1 — single champion, single rank)

With the current filters (one champion, one rank tier), the prompt contains at most:

- **2 comparison groups**: `ITEM_PURCHASE` + `OBJECTIVE_KILL`
- **10 ranked actions per group** = ~20 action lines
- **3 improvement opportunities**
- **5 summoner top actions per group** = ~10 lines
- **~2-5 selection bias flags** (typical)

Observed token usage from integration test (`gpt-4o-mini`):
- **Input:** ~1,261 tokens (4 items, 1 group)
- **Output:** ~451 tokens (3 recommendations)
- **Cost:** ~$0.0005 per request

Realistic upper bound with full item diversity (~30 unique items across 2 groups):
- **Input:** ~2,500-3,500 tokens (well within `max_tokens=1024` output budget and model context)

## Scaling Risks

### 1. Number of Comparison Groups (HIGH if filters are removed)

Groups are keyed by `(champion_id, rank_tier, action_type)`. Currently filtered to one champion + one rank + 2 action types = **2 groups max**. If champion or rank filters are removed:

- 10 champions x 4 ranks x 2 action types = 80 groups
- Each group adds up to 10 ranked actions + 5 summoner actions to the prompt
- **Mitigation:** Keep filters mandatory, or add a `top_n_groups` cap in `llm_prompt.py`

### 2. Selection Bias Flags (LOW but uncapped)

`_detect_selection_bias` in `action_comparison.py:166-202` returns every action with `W(x) >= 0.55` and `delta_w < median`. No slice is applied before rendering in the prompt. In practice this is 2-5 items, but a player who buys many situational "win-more" items could push this higher.

**Mitigation:** Add a `[:5]` or `[:10]` cap in `_build_bias_section` or at the comparison layer.

### 3. New Action Types (LOW — future concern)

Adding action types beyond `ITEM_PURCHASE` and `OBJECTIVE_KILL` (e.g., `SUMMONER_SPELL`, `RUNE_SELECTION`) would add one group each, with up to 10 ranked actions per group.

**Mitigation:** Cap total groups rendered in the prompt, or summarize low-impact groups.

## Key File References

- Aggregation query: `services/api/app/services/action_aggregation.py`
- Comparison + caps: `services/api/app/services/action_comparison.py`
- Prompt construction + caps: `services/api/app/services/llm_prompt.py`
- LLM client (temperature, max_tokens): `services/api/app/services/llm_client.py`
- Response schema: `services/api/app/services/llm_response_schema.py`
- Job orchestration: `services/api/app/jobs/llm_analysis.py`
- Integration test: `services/api/tests/test_llm_integration.py`
