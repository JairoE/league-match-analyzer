# LLM Data Pipeline

## Goal

Ingest a summoner's match history, compute contextualized win probability statistics (following xPetu's thesis framework), and generate actionable improvement recommendations via LLM.

## Pipeline Steps

1.  **Ingest**: Fetch match list + timeline from Riot API. Transiently cache timeline payloads (~1MB) with TTL to save storage.
2.  **Extract**: Pull per-minute state vectors (see Game State Vector below) and discrete action events (item purchases, objective kills) from timeline data. Attach champion metadata from the champions table. Drop raw timeline payload after extraction.
3.  **Score**: Apply win probability model $w(x)$ to pre-action and post-action states. Start with logistic regression on the features below; upgrade to DNN when training data supports it (350K+ matches per the thesis benchmark).
4.  **Compute $\Delta W$**: For each action $d = (a, x, z)$, calculate $\Delta W(d) = w(z) - w(x)$ and initial win probability $W(d) = w(x)$.
5.  **Aggregate**: Compute mean $\overline{\Delta W_X}(a)$ and mean $\overline{W_X}(a)$ per action type. When the summoner's personal sample size $K < 50$, fall back to population-level statistics (all players on that champion at that rank).
6.  **Compare**: Rank the summoner's actual choices against the highest-$\Delta W$ alternatives for their champion, rank, and opponent damage type (physical vs. magic).
7.  **Prompt LLM**: Send the gap analysis (summoner choices vs. optimal alternatives) with schema version. Request 3 ranked recommendations ordered by expected win probability impact.
8.  **Store + Log**: Persist LLM output with match IDs, schema version, and basic request metadata (timestamp, model, token count).

## Game State Vector ($X$)

Extract per-minute state vectors from `participantFrames` and `events`. These align with Table 5 of the thesis (75.9% accuracy, 0.90% ECE):

**Per-player features (x10):**
- `position.x`, `position.y` — from participantFrame (1-min resolution)
- `level` — current champion level
- `totalGold` — cumulative gold acquired
- `damageStats.totalDamageDoneToChampions` — cumulative damage dealt
- `damageStats.totalDamageTaken` — cumulative damage taken
- Kills / Deaths / Assists — derived from `CHAMPIONKILL` events

**Per-team features (x2):**
- Voidgrubs killed — from `ELITEMONSTERKILL` events
- Dragons killed — from `ELITEMONSTERKILL` events
- Barons killed — from `ELITEMONSTERKILL` events
- Turrets destroyed — from `BUILDINGKILL` events
- Inhibitors destroyed — from `BUILDINGKILL` events

**Global features:**
- `timestamp` — current in-game time
- Rank — average rank of the players (pre-game feature)

No sub-minute interpolation is needed for the win probability model; the thesis confirms momentum effects are negligible (Markov assumption holds). Use nearest-frame snapping when joining actions to state vectors.

## Action $\Delta W$ Processing

Compute $\Delta W$ for two action types in V1. Additional action types (champion kills, skill level-ups) can be added when data volume supports statistically significant results.

### Item Purchases
- Action ($a$): `ITEMPURCHASED` — focus on legendary items only (82 items in `LEGENDARY_ITEM_IDS`, clearest strategic signal)
- Initial state ($x$): game state at the minute frame nearest to purchase time
- Final state ($z$): game state when item is sold, destroyed, upgraded, or terminal match state
- `ITEMUNDO` events are key signals of players correcting suboptimal decisions

### Objective Kills (Dragon / Baron / Herald)
- Action ($a$): `ELITEMONSTERKILL`
- Initial state ($x$): game state at the minute frame nearest to the kill
- Final state ($z$): game state ~3-5 minutes later (the objective's effective buff window)

## Win Probability Model

### V1: Logistic Regression
Start with logistic regression using the features above. This follows Maymin [27] and achieves a usable baseline (~72% accuracy per White & Romano [60]).

### V2: Deep Neural Network
Upgrade to a DNN when training data exceeds ~100K matches. The thesis achieved 75.9% accuracy / 0.90% ECE on 350K matches with M=20 bins. Use temperature scaling for calibration (second-best method per Kim et al. [22], simpler to implement than data uncertainty loss).

### Evaluation
- **Accuracy**: proportion of correctly predicted outcomes
- **ECE**: expected calibration error with $M = 20$ bins
- **Reliability diagrams**: plot $\overline{w}(B_m)$ vs. $\overline{y}(B_m)$ per bin, split by 10-min time intervals

### Key Design Decisions
- Train on one random game state per 5-min interval per match to reduce overfitting from correlated successive states (per thesis and AlphaGo [46])
- Items are excluded from model features (categorical complexity of 60 variables); item evaluation uses $\Delta W$ from the action space, which is independent of the state space
- Use the $\overline{W_X}(a)$ statistic to detect selection bias: $\overline{W_X}(a) > 0.5$ means the action is taken more often when already winning (e.g., Heartsteel in the thesis case study)

## Aggregation Strategy

The thesis is explicit: single-match $\Delta W$ values are noisy due to variance and external factors (Section 4.2). Meaningful insights require aggregation over many similar data points.

- **Minimum sample size**: $K \geq 50$ matches for a given (champion, action, opponent-type) tuple
- **Population fallback**: when personal data is insufficient, use population-level $\Delta W$ statistics for the same champion at the same rank tier
- **State set specificity**: condition on opponent damage type (physical vs. magic) as the thesis demonstrates this produces meaningfully different rankings (Tables 8-9)
- **Specificity vs. sample size trade-off**: start broad (champion + rank), narrow (+ opponent type, + game phase) only when $K$ remains above threshold

## LLM Prompt Design

The LLM receives a structured gap analysis, not raw match data:

```
Input to LLM:
- Summoner's champion and rank
- Summoner's most common item choices with their ΔW values
- Population-optimal item choices with their ΔW values
- Notable gaps (items where summoner's choice has significantly lower ΔW)
- Opponent damage type distribution from recent matches
```

The LLM is asked to:
1. Explain the 3 largest improvement opportunities ranked by $\Delta W$ impact
2. Provide context-specific advice (e.g., "vs. magic damage top laners, buy X instead of Y")
3. Flag any selection bias patterns (high $W$ but low $\Delta W$ items the summoner defaults to)

## Sanitization

- Strip raw timeline data after feature extraction (prevents LLM context bloat)
- Remove summoner name, account ID, PUUID from LLM payload
- Never include API keys, tokens, or raw Riot payloads
- Keep the LLM payload minimal and versioned; store schema version with every response

## Implementation Status

| Step | Status | Implementation |
|------|--------|----------------|
| 1. Ingest | **Done** | `extract_match_timeline_job` in `app/jobs/timeline_extraction.py`. Fetches timeline via `RiotApiClient.fetch_match_timeline()`, caches in Redis (`timeline:{matchId}`, 1h TTL). |
| 2. Extract | **Done** | `extract_state_vectors()` in `app/services/state_vector.py` — per-minute `GameStateVector` with cumulative KDA/objective trackers. `extract_actions()` in `app/services/action_extraction.py` — legendary item purchases + objective kills with pre/post state linking. |
| 3. Score | Not started | Requires training a logistic regression on `match_state_vector.features` + match outcomes. |
| 4. Compute ΔW | Not started | `match_action` table has `delta_w`, `pre_win_prob`, `post_win_prob` columns ready (nullable). |
| 5. Aggregate | Not started | No aggregation service yet. |
| 6. Compare | Not started | No comparison service yet. |
| 7. Prompt LLM | Not started | `llm_analysis` table exists with `input_payload`, `output_payload`, `recommendations` columns. |
| 8. Store + Log | Not started | `LLMAnalysis` model ready with `schema_version`, `model_name`, token counts. |

### DB tables (migration `20260305_0002`)

- `match_state_vector` — per-minute game state features (JSONB), unique on `(match_id, minute)`
- `match_action` — discrete actions with pre/post state refs and ΔW scoring columns
- `llm_analysis` — LLM output persistence with schema versioning and token counts

### Key files

- `services/api/app/services/state_vector.py` — `GameStateVector`, `PlayerState`, `TeamState` dataclasses; `extract_state_vectors()`, `get_nearest_state_vector()`
- `services/api/app/services/action_extraction.py` — `MatchAction` dataclass, `ActionType` enum, `LEGENDARY_ITEM_IDS` set (82 items); `extract_actions()`
- `services/api/app/jobs/timeline_extraction.py` — `extract_match_timeline_job` ARQ job (idempotent, Redis-cached timeline fetch)
- `services/api/app/models/match_state_vector.py` — `MatchStateVector` SQLModel
- `services/api/app/models/match_action.py` — `MatchActionRecord` SQLModel
- `services/api/app/models/llm_analysis.py` — `LLMAnalysis` SQLModel
- `services/api/tests/test_state_vector.py` — 10 tests
- `services/api/tests/test_action_extraction.py` — 12 tests

### Next steps to continue

1. Wire `extract_match_timeline_job` into the existing match ingestion flow (enqueue after `fetch_match_details_job` completes)
2. Build a training data export: query `match_state_vector` features + match outcomes from `match.game_info`
3. Train V1 logistic regression and expose as a scoring service
4. Populate `delta_w` / `pre_win_prob` / `post_win_prob` on `match_action` rows
5. Build aggregation queries and comparison logic
6. Implement LLM prompt construction and `llm_analysis` persistence

## Future Extensions

- **Champion kill $\Delta W$**: add when sample sizes support it; $z$-state is after death timer expires
- **Skill level-up order**: add when data volume allows per-champion analysis
- **Multi-item sequencing**: evaluate item build paths (combinatorial; requires significantly more data)
- **Production observability**: trace IDs, latency monitoring, error rates, manual review flags
- **Pre-game prediction**: incorporate draft-phase win probability (72-75% accuracy per [12, 60]) for champion select advice
