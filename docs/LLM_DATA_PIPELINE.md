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

## Pipeline Runbook

Steps 1-2 run automatically when matches are fetched through the API/worker. Steps 3-6 require manual invocation. Steps 7-8 are not yet implemented.

**Prerequisites**: `make db-up`, `make db-migrate`, `make install`, and a valid `RIOT_API_KEY` in `services/api/.env`.

### Step 1-2: Ingest + Extract (automatic)

Triggered automatically when matches are fetched via the search endpoint or ARQ worker sync. To backfill extraction for existing matches that are missing state vectors:

```bash
# Dry run — see which matches would be enqueued
make backfill-extraction-dry

# Run backfill (requires ARQ worker running)
make backfill-extraction
```

The ARQ worker must be running to process the enqueued jobs:

```bash
make worker-dev
```

### Step 3: Train Win Probability Model (manual)

Export training data from extracted state vectors, then train the logistic regression model:

```bash
# Export CSV (samples one state per 5-min interval per match, per thesis)
./.venv/bin/python scripts/export_training_data.py --output data/training.csv --sample-interval 1

# Train model and save to joblib
make win-prob-model-training
# Output: data/win_prob_model.joblib
```

Set `WIN_PROB_MODEL_PATH=../../data/win_prob_model.joblib` in `services/api/.env` so the worker can load it.

### Step 4: Score Actions (manual, per match)

Enqueues `score_actions_job` via ARQ. Requires the worker to be running with the model loaded.

```bash
# Score a single match
make score-actions MATCH_ID=NA1_1234567890
```

To score all unscored matches for an account, use:

```bash
# By account UUID (preferred when you already have it)
make score-account-matches RIOT_ACCOUNT_ID=<uuid>

# Or by Riot ID (gameName#tagLine), the helper will resolve the account UUID from the DB:
make score-account-matches RIOT_ID="damanjr#NA1"

# Dry run — just show how many matches would be scored, without enqueueing jobs
make score-account-matches-dry RIOT_ID="damanjr#NA1"

# Inspect how many matches have already been scored vs total, and how many remain:
make account-match-stats RIOT_ID="damanjr#NA1"
```

Under the hood this runs a Postgres query against the `match` and `riot_account_match` tables to find all matches for the account that do not yet have `delta_w` populated in `match_action`, then enqueues `score_actions_job` for each match via `make score-actions`. The `-dry` variant runs the same filter query but only prints the count.

### Step 5: Aggregate (manual, read-only)

Aggregation runs on-the-fly over scored actions — no persistence step needed.

```bash
# By Riot ID
make aggregate-actions-debug RIOT_ID=damanjr#NA1

# By account UUID (skip DB lookup)
make aggregate-actions-debug RIOT_ACCOUNT_ID=<uuid>

# With filters
./.venv/bin/python scripts/aggregate_actions_debug.py --riot-id "damanjr#NA1" --champion 157 --rank-tier GOLD
```

If this returns "No action aggregates", it means step 4 has not been run for this account's matches (no `delta_w` values exist).

### Backfill average_rank on state vectors (optional, one-time)

After rank data has accumulated (via the rank endpoint persisting `rank_tier` on `riot_account`), backfill `average_rank` into existing state vectors without re-running extraction:

```bash
# Dry run — see which matches would be updated
./.venv/bin/python scripts/backfill_rank_on_vectors.py --dry-run

# Run backfill (default: requires >= 3 known ranks per match)
make backfill-rank

# Lower threshold for V1 if most matches only have 1-2 known ranks
./.venv/bin/python scripts/backfill_rank_on_vectors.py --min-known 1
```

New extractions resolve `average_rank` automatically (Redis + DB lookup in `extract_match_timeline_job`). This backfill is only needed for state vectors created before rank resolution was wired in.

After backfilling, re-export training data and retrain to give the model a rank signal:

```bash
./.venv/bin/python scripts/export_training_data.py --output data/training.csv --sample-interval 1
make win-prob-model-training
```

### Step 6: Compare (manual, read-only)

Comparison runs on-the-fly over step 5 aggregation output — ranks summoner's choices against population-optimal alternatives, identifies improvement gaps, and detects selection bias (high W(x) + low ΔW).

```bash
# By Riot ID
make compare-actions-debug RIOT_ID=damanjr#NA1

# By account UUID (skip DB lookup)
make compare-actions-debug RIOT_ACCOUNT_ID=<uuid>

# With filters
./.venv/bin/python scripts/compare_actions_debug.py --riot-id "damanjr#NA1" --champion 157 --rank-tier GOLD
```

If this returns "No comparison results", it means step 5 returned no aggregates (no scored actions for this account/filters).

### Steps 7-8: Not yet implemented

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
| 1→2 Wiring | **Done** | `fetch_match_details_job` auto-enqueues `extract_match_timeline_job` after persisting `game_info`. `enqueue_timeline_extraction.py` handles idempotency (skips matches with existing state vectors) and deterministic `_job_id`. Job registered via `func(extract_match_timeline_job, max_tries=5)` in `WorkerSettings.functions`. Rate-limited jobs raise `arq.Retry(defer=120)` instead of failing permanently (up to 5 ARQ retries, ~10 min total). All existing matches backfilled via `scripts/backfill_extraction.py`. |
| 3. Score | **Done** | `scripts/train_win_prob_model.py` trains logistic regression from exported CSV and saves joblib. Scoring service in `app/services/win_prob_scoring.py` loads model (optional `WIN_PROB_MODEL_PATH`), `score_state(features)` returns w(x). |
| 4. Compute ΔW | **Done** | `score_actions_job` in `app/jobs/score_actions.py` loads state vectors and actions per match, scores pre/post states via `score_state()`, persists `delta_w`, `pre_win_prob`, `post_win_prob` on `match_action`. Idempotent; skips when model not loaded. |
| 5. Aggregate | **Done** | `app/services/action_aggregation.py` — read-only SQL aggregations on `match_action` joined to `match` and `riot_account_match`. Groups by champion_id, rank_tier, action_type, action_key, opponent_damage_bucket (V1: "mixed"). `aggregate_action_stats_for_player(session, riot_account_id, champion?, rank_tier?)` returns list of `ActionAggregate` with personal_stats, population_stats, and `insufficient_personal_sample` when K < 50. Population restricted to same (champion, rank_tier) buckets. Optional dispersion: stddev(delta_w). Debug script: `scripts/aggregate_actions_debug.py` and `make aggregate-actions-debug RIOT_ACCOUNT_ID=...` or `RIOT_ID=...`. |
| 6. Compare | **Done** | `compare_action_stats()` in `app/services/action_comparison.py` — pure sync function consuming step 5 `list[ActionAggregate]`. Groups by (champion, rank, action_type), ranks by effective ΔW (personal K≥50, else population), computes improvement gaps (summoner's top items vs. rank-1 alternative), detects selection bias (W(x) ≥ 0.55 + ΔW below group median). Output: `ComparisonResult` (champion-agnostic top level; each `ComparisonGroup` carries champion/rank) serializable to `LLMAnalysis.input_payload` via `dataclasses.asdict()`. Supports multi-champion analysis. Debug script: `scripts/compare_actions_debug.py` and `make compare-actions-debug`. |
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
- `services/api/app/services/enqueue_timeline_extraction.py` — `enqueue_missing_extraction_jobs()` with DB idempotency check and deterministic `_job_id`
- `services/api/app/services/background_jobs.py` — `WorkerSettings` with all 4 job functions registered
- `services/api/app/models/match_state_vector.py` — `MatchStateVector` SQLModel
- `services/api/app/models/match_action.py` — `MatchActionRecord` SQLModel
- `services/api/app/models/llm_analysis.py` — `LLMAnalysis` SQLModel
- `scripts/export_training_data.py` — standalone training data export (CSV, 5-min interval sampling per thesis)
- `scripts/train_win_prob_model.py` — train V1 logistic regression from CSV, save joblib (default `data/win_prob_model.joblib`)
- `scripts/backfill_extraction.py` — one-off script to enqueue extraction jobs for existing matches missing state vectors
- `scripts/backfill_rank_on_vectors.py` — targeted backfill of `average_rank` on existing state vectors (DB-only, no API calls)
- `services/api/app/services/resolve_match_rank.py` — `resolve_average_rank()` — computes median rank from Redis cache + `riot_account.rank_tier` DB column
- `services/api/app/services/win_prob_features.py` — `FEATURE_ORDER`, `encode_rank()` (shared by train script and scoring)
- `services/api/app/services/win_prob_scoring.py` — `load_model()`, `score_state(features)` → w(x) or None
- `services/api/app/jobs/score_actions.py` — `score_actions_job(ctx, match_id)` populates ΔW columns on match_action
- `services/api/app/services/action_aggregation.py` — `aggregate_action_stats_for_player(session, riot_account_id, champion?, rank_tier?)` → list of `ActionAggregate` (personal + population stats, K≥50 fallback); `GroupKey`, `AggregateRow`, `ActionAggregate`; `_build_personal_sql`, `_build_population_sql` for optional filters and IN expansion
- `services/api/app/services/action_comparison.py` — `compare_action_stats(aggregates, item_names?, objective_names?)` → `ComparisonResult` (champion-agnostic) with `ComparisonGroup`, `RankedAction`, `ImprovementGap`, `SelectionBiasFlag`; pure sync function, supports multi-champion input
- `scripts/compare_actions_debug.py` — CLI debug script for step 6 comparison output
- `services/api/tests/test_action_comparison.py` — 14 tests
- `services/api/tests/test_action_aggregation.py` — 12 tests
- `services/api/tests/test_state_vector.py` — 10 tests
- `services/api/tests/test_action_extraction.py` — 12 tests

### Next steps to continue

1. ~~Wire `extract_match_timeline_job` into the existing match ingestion flow~~ **Done**
2. ~~Build a training data export~~ **Done** (`scripts/export_training_data.py`)
3. ~~Accumulate training data by running the app with real matches + `make backfill-extraction` for existing matches~~ **Done** — all existing matches have state vectors
4. ~~Train V1 logistic regression on exported CSV and expose as a scoring service~~ **Done** — `scripts/train_win_prob_model.py`, `win_prob_scoring.py`
5. ~~Build a `score_actions_job` to populate `delta_w` / `pre_win_prob` / `post_win_prob` on `match_action` rows~~ **Done**
6. ~~Build aggregation queries~~ **Done** — `action_aggregation.py` with personal/population merge and K≥50 fallback.
7. ~~Build comparison logic~~ **Done** — `action_comparison.py` with ranking, improvement gaps, selection bias detection.
8. Implement LLM prompt construction and `llm_analysis` persistence

## Future Extensions

- **Champion kill $\Delta W$**: add when sample sizes support it; $z$-state is after death timer expires
- **Skill level-up order**: add when data volume allows per-champion analysis
- **Multi-item sequencing**: evaluate item build paths (combinatorial; requires significantly more data)
- **Production observability**: trace IDs, latency monitoring, error rates, manual review flags
- **Pre-game prediction**: incorporate draft-phase win probability (72-75% accuracy per [12, 60]) for champion select advice
