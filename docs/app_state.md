# App State

**Last Updated:** 2026-06-01
**Branch:** `claude-workflows-rag`
**Status:** STABLE — RAG few-shot retrieval (Phase 2 of `docs/rag-design.md`) implemented on the backend and verified via `/verify-changes` against `main`: **GO-WITH-NITS**. Lint clean, full backend suite green (181 passed, 2 skipped — real-API integration only), and **zero new dependencies** (`pgvector>=0.3.6` and `openai>=1.58.0` were already declared). One WARN (dead `Vector` import-shim in the migration) plus minor NOTEs; nothing blocking. The Alembic up/down round-trip was not exercised (no DB container up). The earlier `frontend-enhancements` branch (React perf S1–S5 + 22-test Playwright suite) remains a separate in-flight branch — its ship steps live in the Recent Changes history below.

## Current Phase

**RAG few-shot retrieval on `claude-workflows-rag` — implemented, verified GO-WITH-NITS, ready to address nits + ship.** Adds pipeline Step 6.5 (embed the comparison context, retrieve the most similar prior `LLMAnalysis` records for the same champion via pgvector cosine KNN, inject as few-shot examples) plus a post-persist embedding store so the corpus grows itself. All RAG paths are gated by `rag_enabled` (default True) + `openai_api_key` and are fail-soft (errors logged, pipeline never aborts). `/verify-changes` was run end-to-end for real this time (Phase 1 dependency gate + Phase 4 lint/test executed, not a manual stand-in), partially resolving the prior caveat about the workflow never having been invoked.

### verify-changes findings (2026-06-01, RAG branch — all non-blocking)

- **WARN** — `20260601_0004_rag_embedding_column.py:16-26`: dead `try/except ImportError` fallback `Vector` type. `pgvector` is a hard runtime dep (`pyproject.toml:14`, imported unconditionally at `models/llm_analysis.py:13`), so the shim can never run where migrations run. Import `Vector` directly; delete ~11 lines.
- **NOTE** — `jobs/llm_analysis.py`: `OpenAIClient` instantiated 3×, `comparison.to_dict()` called 3×, `build_embedding_text(...)` computed twice with identical args. Build once and reuse.
- **NOTE** — HNSW index (`vector_cosine_ops`, m=16/ef=64) is premature-but-harmless at current corpus size (~hundreds of rows); removable, leaks nothing into call sites. Keep as forward-looking.
- **NOTE** — `rag_enabled=True` by default means 2 embedding calls per job before the corpus is seeded (retrieval returns little until ~50/bucket per the design doc). Negligible cost; decision point.

## Blockers

- None. The RAG feature passes lint + the full backend suite; all findings are NOTE/WARN.
- Open integrity gap (not a blocker): the Alembic up/down round-trip for `20260601_0004` was not run (no Postgres container up). Verify before merge.
- Model change + new migration are AGENTS.md ⚠️ ask-before-doing items; `docs/rag-design.md` pre-authorizes them — confirm reviewer sign-off.
- Operational note from earlier phase still stands: Railway dashboard must run `release.sh` as the API service's pre-deploy/release command (unchanged from 2026-03-04).

## Next Steps

1. Remove the dead `Vector` ImportError shim in `20260601_0004_rag_embedding_column.py` — import pgvector directly (the only WARN).
2. Run the migration round-trip (`make db-up && make db-migrate`, then downgrade one step) — not covered by any test.
3. (Optional cleanup) Reuse one `OpenAIClient` + one embed-text/dict in `jobs/llm_analysis.py`; tighten `few_shot_examples: list[dict]` → `list[dict[str, Any]]`.
4. (Decision) Confirm `rag_enabled=True`-by-default is intended before the corpus is seeded — otherwise default it off and flip after `make backfill-rag-embeddings`.
5. Confirm reviewer sign-off on the model + migration (ask-before-doing), then open PR `claude-workflows-rag` → `main`.
6. Once enough analyses exist (~50+ per champion/rank bucket per the design doc), run `make backfill-rag-embeddings` to embed pre-RAG rows, then evaluate few-shot quality.

**Separate in-flight branch — `frontend-enhancements`** (React perf S1–S5 + Playwright suite): still pending its own ship steps — run `cd league-web && npm run test:e2e`, open PR → `main`, and the two non-blocking nits (pin `babel-plugin-react-compiler` / `eslint-plugin-react-compiler` to exact `19.1.0-rc.2`; slim `league-web/e2e/fixtures/matches.ts`). Full detail in the 2026-05-27 / 2026-06-01 Recent Changes history below.

## Recent Changes (2026-06-01 — RAG few-shot retrieval, `claude-workflows-rag`)

### What changed (Phase 2 of `docs/rag-design.md`)

- **Schema**: nullable `vector(1536)` `embedding` column on `llm_analysis` + HNSW cosine index (`ix_llm_analysis_embedding_hnsw`, m=16/ef_construction=64). Migration `20260601_0004` (revises `20260316_0003`); runs `CREATE EXTENSION IF NOT EXISTS vector`. Model: `embedding: list[float] | None` via `pgvector.sqlalchemy.Vector` (`models/llm_analysis.py`).
- **Embeddings**: `OpenAIClient.embed(text, model="text-embedding-3-small")` (`services/llm_client.py`).
- **Retrieval service** (`services/rag_retrieval.py`): `build_embedding_text()` (compact champion/rank/gaps/bias single-line text), `retrieve_few_shot_examples()` (champion-filtered cosine KNN, fail-soft → `[]`), `format_few_shot_examples()` (prompt-friendly dicts).
- **Prompt** (`services/llm_prompt.py`): `build_user_prompt(..., few_shot_examples=...)` renders a `## Reference Examples` section before the Player Profile; no-ops on empty.
- **Pipeline** (`jobs/llm_analysis.py`): new Step 6.5 (embed query → retrieve → inject) and a post-persist embedding store; both gated by `rag_enabled` + `openai_api_key` and wrapped fail-soft.
- **Config** (`core/config.py`): `rag_enabled=True`, `rag_embedding_model="text-embedding-3-small"`, `rag_few_shot_limit=3`.
- **Backfill**: `scripts/backfill_rag_embeddings.py` (`--batch-size`, `--dry-run`) + Makefile targets `backfill-rag-embeddings` / `backfill-rag-embeddings-dry`.
- **Design doc**: `docs/rag-design.md` (Proposed) — problem, rejected standalone-search alternative, phased plan.

### Tests / lint

- New `test_rag_retrieval.py` (17 tests) + additions to `test_llm_client.py` (embed), `test_llm_prompt.py` (few-shot injection), `test_llm_analysis_job.py` (injection + fail-soft). Touched files: 47 passed.
- `make lint` clean; `make test` → **181 passed, 2 skipped**. No new dependencies (`pgvector>=0.3.6`, `openai>=1.58.0` pre-declared).
- Not run: migration up/down round-trip (no DB container up).

### Note on the prior verify-changes caveat

- The 2026-06-01 scale-verification entry below recorded that `/verify-changes` had been authored but **never actually invoked**. It has now been run end-to-end for real on this branch (Phase 1 dependency gate + Phase 4 lint/test executed against live tooling, not a manual stand-in), partially resolving prior Next Step 9. Phase 5 (`--deep` subagents) was not used (default fast run).

## Recent Changes (2026-06-01 — scale & maintainability verification)

### What changed

- **New reusable workflow command**: `.claude/commands/verify-changes.md`. Invoke as `/verify-changes [base-ref] [--deep]`. It diffs a branch against a base ref and gates it on two bars — (1) **scale-appropriate** (no unneeded deps; optimizations justified at current scale) and (2) **maintainable** (not overengineered) — by orchestrating the agent-skills (`code-simplification`, `code-review-and-quality`, `performance-optimization`) plus an explicit dependency-hygiene gate and a lint/build/e2e integrity check. `--deep` fans out to the `code-reviewer` + `test-engineer` subagents.
- **Authored the command but did not actually invoke it.** The GO-WITH-NITS verdict below is from a **manual review performed by hand** (real `git diff` + file reads + reasoning) that *mirrors* the workflow's phases — NOT from running `/verify-changes` or its agent-skills (`code-simplification`, `code-review-and-quality`, `performance-optimization`). Phase 4 (lint/build/e2e) and Phase 5 (`--deep` subagents) were not run. The findings are evidence-based, but the workflow itself is unvalidated end-to-end.

### Findings (verify-changes, 2026-06-01)

- **Dependencies** — 3 new deps, all **devDependencies**, **zero new runtime/bundle deps**. `@playwright/test ^1.59.0` justified (real E2E suite). The two React Compiler packages (`babel-plugin-react-compiler`, `eslint-plugin-react-compiler`, both `^19.1.0-rc.2`) power S4 annotation mode on 3 files — **WARN** on caret-on-RC pin (non-reproducible); **NOTE** marginal ROI at current scale (contained, removable).
- **Overengineering** — only real flag is `e2e/fixtures/matches.ts` (255 lines): fixtures carry detail (`perks`, damage/CS totals, summoner-spell IDs) and repeated ally/enemy blocks that no spec asserts. Everything else (`e2e/helpers.ts`, `DynamicImportBoundary.tsx` at 35 lines, `LiveGameSlot.tsx`, `playwright.config.ts`) is lean; deterministic anchors used throughout (no arbitrary timeouts); conditional paths branch-tested.
- **Performance at scale** — S1/S3 code-splitting (recharts, `LiveGameCard`) and S5 `matchDetails` reference stability all **Justified**; S4 React Compiler annotation **borderline but not harmful** (opt-in, removable).

### Tests / lint

- Not re-run this session (static review per the request's focus). Recorded status stands: lint clean (pre-existing `AuthForm.tsx` exhaustive-deps warning only); 22/22 E2E green as of 2026-05-30.

## Recent Changes (2026-05-27, frontend-enhancements — React perf S1–S5 + Playwright E2E)

### What changed

- **S1 — Code-split `ChampionKdaChart`** via `next/dynamic` (`ssr:false`); recharts ships only when a match with 2+ point KDA history is expanded. New `MatchCard/ChartSkeleton.tsx` placeholder + `components/common/DynamicImportBoundary.tsx` error boundary with a `resetKey` prop so transient chunk-load failures don't permanently break the UI.
- **S2 — `useTransition`** wired into `MatchesTable` pagination and queue-tab switches; stale render stays visible while the next page/filter computes, click feedback stays instant.
- **S3 — Code-split `LiveGameSlot`** via `next/dynamic`; the `LiveGameCard` chunk only loads when SSE reports an in-game state. Idle / `not_in_game` / error renders are pure status UI.
- **S4 — React Compiler annotation mode (`"use memo"`)** opted-in on `MatchesTable`, `home` page, and `riot-account/[riotId]` page (per-file rather than repo-wide).
- **S5 — Stable `matchDetails` reference** in `useMatchList`. Removed the `matchDetailsRef` / `loadedDetailCount` gate; `setMatchDetails` now returns `prev` when content is unchanged, and the polling seeding effect only merges entries genuinely absent from `prev`. Stops `matchSummaryStats` / `championHistoryByMatchId` memos from re-running every 3-second poll tick.

### Config + follow-up fixes

- **`next.config.ts`**: `reactCompiler` moved to top-level (stable in Next.js 16; staying under `experimental` triggered a startup warning + risked silent fallback).
- **`useMatchList` polling tick fix**: the seeding effect was overwriting existing entries with freshly-deserialized objects every poll, churning `matchDetails` references. Now only merges entries absent from `prev`.

### Playwright E2E suite (`league-web/e2e/`)

- 22 tests across 4 specs:
  - `matches-table-tabs.spec.ts` — queue tab filtering (S2) + summary stats W/L correctness (S5 regression).
  - `matches-table-pagination.spec.ts` — Next/Previous via `useTransition` (S2).
  - `match-card-chart.spec.ts` — dynamic chart load, skeleton→chart transition, `DynamicImportBoundary` `resetKey` recovery (S1).
  - `live-game-slot.spec.ts` — dynamic `LiveGameSlot` with SSE `not_in_game` / error / retry flows (S3).
- Typed fixtures in `e2e/fixtures/matches.ts` cover Ranked Solo, Normal Draft, and ARAM queue types with multi-champion history data.
- Mocks use `page.route()` wildcards — no backend required to run tests (`cd league-web && npm run test:e2e`).
- Locator hardening fixes: `data-testid="tab-bar"` on the tab bar to scope tab-click locators away from row cells with the same accessible name; `exact: true` on pagination button locators so `Next` no longer matches the Next.js Dev Tools button.

### Staged-but-uncommitted (test stability + doc clarification)

- New `gotoAccountAndWait(page)` helper in `e2e/helpers.ts` — navigates to the riot-account page and awaits the first "Ranked Solo" cell.
- `live-game-slot.spec.ts`: removed `waitForTimeout(500/2000)` calls. Retry test now uses `Promise.all([page.waitForRequest(...), click])`; "no account loaded" test waits on the deterministic page-error copy "No search results for the summoner …"; error-state test asserts the "Please try again." copy.
- `match-card-chart.spec.ts`: collapsed three overlapping expansion tests into one combined "expand → chart loads → SVG renders" test. Single-game (Lux/ARAM) no-chart test now anchors on close-button visibility instead of `waitForTimeout(1000)`.
- `matches-table-pagination.spec.ts`: merged the standalone "no JS errors during navigation" assertion into the "Next navigates to page 2" test (single `pageerror` listener); reused `gotoAccountAndWait`.
- `matches-table-tabs.spec.ts`: added a `queueLabelCells(page)` helper because `MatchRow` renders `<tr role="button">`, overriding the implicit row role — rows are now counted via the first cell. Removed the redundant "switch back to All" test.
- `docs/TECHNICAL_ARCHITECTURE_AND_PATTERNS.md`: clarified that `isHydrated` is a workaround for client-only `sessionStorage` reads on `"use client"` routes, not a Next.js feature. Notes the cookie-migration path that would let those routes render server-side and remove the pattern.

### Key files

- `league-web/next.config.ts`
- `league-web/src/components/MatchesTable/MatchesTable.tsx` (useTransition, `data-testid="tab-bar"`, `"use memo"`)
- `league-web/src/components/MatchCard/{MatchCard.tsx, ChartSkeleton.tsx, MatchCard.module.css}`
- `league-web/src/components/common/DynamicImportBoundary.tsx` (new)
- `league-web/src/components/LiveGameSlot/LiveGameSlot.tsx` (dynamic import)
- `league-web/src/lib/hooks/useMatchList.ts` (S5 reference stabilization + poll-tick merge fix)
- `league-web/src/app/{home,riot-account/[riotId]}/page.tsx` (`"use memo"`)
- `league-web/playwright.config.ts`, `league-web/TESTING.md`, `league-web/e2e/` (suite + fixtures)

### Tests / lint

- Frontend lint clean; backend untouched (still 160/160).

---

## What's Built

### Backend (FastAPI + ARQ)

- **Search flow**: `GET /search/{riot_id}/matches` — account resolved from DB first; Riot called for account only on first sync (account not in DB). Match IDs fetched from Riot on first sync, `?refresh=true` (page 1), or see more (`after>0`). Supports `?page=N&limit=N&refresh=true`.
- **Auth match flow**: `GET /riot-accounts/{id}/matches` — paginated match list from DB; Riot match IDs only when `?refresh=true` (page 1) or see more (`after>0`).
- **Pagination schema**: `PaginatedMatchList` wraps `data` + `PaginationMeta` (page, limit, total, last_page, stale, stale_reason). On 429 during page-1 sync, endpoints fall back to DB and return cached data with `stale=true`.
- **Auth flow**: `POST /users/sign_in`, `POST /users/sign_up` — optional user authentication.
- **Riot API Client**: Redis-backed sliding-window rate limiter with dynamic header parsing and exponential backoff.
- **Background jobs**: `fetch_match_details_job` (batch → auto-enqueues `extract_match_timeline_job`), `extract_match_timeline_job` (state vector + action extraction), `score_actions_job` (ΔW scoring), `llm_analysis_job` (steps 5→8 orchestration), `fetch_timeline_cache_job` (timeline warmup), `sync_all_riot_accounts_matches` (cron every 6h).
- **Data model**: `RiotAccount`, `Match` (with `game_info` JSONB), `RiotAccountMatch` join table. `pgvector` extension enabled.
- **Observability**: Structured JSON logging, `increment_metric_safe` metric helper.

### Frontend (Next.js 16)

- **Pages**: `/` (search + optional auth), `/home` (match results dashboard), `/riot-account/[riotId]` (search results view).
- **API client**: `src/lib/api.ts` — typed `apiGet<T>` / `apiPost<T>` wrappers.
- **Client cache**: `src/lib/cache.ts` — in-memory LRU-like cache with TTL.
- **Session management**: `sessionStorage`-backed `useSession` hook.
- **Match history UX**:
  - `MatchesTable` now replaces card-grid history on `/home` and `/riot-account/[riotId]`.
  - Table uses sticky headers, queue-group tabs, row-level selection, and skeleton states.
  - Right-side detail overlay (`MatchDetailPanel`) renders `MatchCard` in `expanded` mode.
  - Queue type modeling is centralized in `src/lib/types/queue.ts` with coarse tab grouping (`GameQueueGroup`) and granular row labels (`GameQueueMode`).
- **Match card**: `MatchCard` is decomposed into `ItemSlot`, `Teams`, `ChampionKdaChart`, `match-card.utils.ts`, and `types.ts` within `MatchCard/`. The main file is a ~200-line orchestrator, `memo`-wrapped at export.
- **Pagination**: Reusable `Pagination` component with Previous/Next buttons, "Page X of Y", total count. Hidden when single page. Wired into `MatchesTable` via optional `paginationMeta`/`onPageChange` props.
- **Rank in header**: `useRank(riotAccountId, { refreshIndex })` in `src/lib/hooks/useRank.ts` fetches `GET /riot-accounts/{id}/fetch_rank` and returns `{ rank, rankSubtitle }`. Used on `/home` and `/riot-account/[riotId]` so both show rank subtitle in `SubHeader`; refresh on either page refetches rank via `refreshIndex`.
- **Error handling** (`src/lib/errors/`):
  - `ApiError` class with `status`, `detail`, `riotStatus` fields.
  - `buildApiErrorFromResponse` / `toApiError` for normalising HTTP and plain errors.
  - `formatApiError` — translates backend codes via `DETAIL_MESSAGES` lookup table; handles `riot_api_failed` with `riotStatus` branching (404/429/other); HTTP status fallbacks for unknown codes; no misleading "Network error" prefix on non-HTTP errors.
  - `useAppError(scope)` React hook — `{ errorMessage, reportError, clearError }`.
  - Call sites use `reportError(err)` for general errors; intercept before `reportError` when a page-level context string (e.g. summoner name) is needed.

### Infrastructure

- Docker Compose: `api`, `worker`, `db`, `redis`.
- Railway deployment via `railway.json` + nixpacks.
- Alembic async migrations.

---

## Open Tickets / Blockers

| Ticket                                                                                                                                        | File                                                                | Status       |
| --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------ |
| Race condition in `_get_or_create_match` and `upsert_user_from_riot` — non-atomic check-then-insert causes `IntegrityError` under concurrency | `services/api/app/services/match_sync.py`, `riot_account_upsert.py` | **RESOLVED** |

**Resolved** (session 15): All select-then-insert patterns replaced with `INSERT ... ON CONFLICT DO NOTHING` for `Match`, `RiotAccountMatch`, `User`, and `UserRiotAccount`.

---

## Recent Changes (2026-03-18, LLM pipeline code review fixes)

### Code review fixes for LLM pipeline steps 7-8

- **Deduplicated shared helpers**: Removed duplicate `_OBJECTIVE_LABELS` dict and `_load_item_name_map()` from `scripts/llm_analysis_debug.py`. Debug script now imports `OBJECTIVE_LABELS`, `load_item_name_map`, and `_get_scored_match_ids` from `app/jobs/llm_analysis.py`. Functions renamed from private (`_`) to public since they're part of the module's import API.
- **Aligned recommendation constraints**: Changed `Recommendation.rank` from `le=5` to `le=3` and `LLMAnalysisResponse.recommendations` from `max_length=5` to `max_length=3` in `llm_response_schema.py`. Matches the system prompt instruction ("identify the 3 largest improvement opportunities") and pipeline doc. Tests updated accordingly.
- **Documented prompt truncation**: Added inline comment explaining the `[:10]` cap on ranked actions in `_build_rankings_section()` (`llm_prompt.py`) — keeps prompts compact and within token budget.
- **Added `max_tokens=1024`**: Set token budget on the OpenAI `create()` call in `llm_client.py` for cost control. Expected response is a JSON object with 3 recommendations + 2 summary strings, well under 1K tokens.
- **Tests**: 160/160 pass. Lint clean.

---

## Recent Changes (2026-03-18, LLM pipeline steps 7-8 — Prompt LLM + Store)

### Step 7 — LLM prompt construction + calling

- **Provider abstraction**: `app/services/llm_client.py` — `LLMClient` protocol + `OpenAIClient` implementation. Uses `response_format={"type": "json_object"}` for structured output, `temperature=0.3`, `max_tokens=1024`. To swap to Claude/Anthropic later: add `AnthropicClient` in this same file, change one instantiation line in the job.
- **Response schema**: `app/services/llm_response_schema.py` — `Recommendation` (rank 1-3, title, current_choice, recommended_choice, delta_w_gap, explanation, category) + `LLMAnalysisResponse` (up to 3 recommendations, selection_bias_summary, overall_assessment). Pydantic v2 with `model_validate_json()` for parsing.
- **Prompt construction**: `app/services/llm_prompt.py` — `build_system_prompt()` with JSON schema inline, coaching analyst role, ΔW explanation. `build_user_prompt(comparison_dict, champion_name, rank_tier)` formats improvement opportunities, selection bias flags, and per-group action rankings (capped at 10 per group). Sanitized: no summoner names, PUUIDs, account IDs, or raw Riot payloads.

### Step 8 — Persistence + orchestration

- **ARQ job**: `app/jobs/llm_analysis.py` — `llm_analysis_job(ctx, riot_account_id, champion, rank_tier?)` orchestrates steps 5→8 end-to-end. Aggregates actions (step 5), compares against population (step 6), resolves champion name from DB, fetches item names from DDragon, builds/sends prompt (step 7), parses response, persists `LLMAnalysis` row (step 8). Registered in `WorkerSettings.functions`. Exports `OBJECTIVE_LABELS`, `load_item_name_map()` for reuse by debug script.
- **Error handling**: `no_data` (empty aggregation), `no_comparison` (all None ΔW), `llm_error` (API failure), `parse_error` (invalid JSON — raw response stored in `output_payload`, recommendations set to `[]`), `skipped` (no API key configured).
- **Config**: Added `openai_api_key: str = ""` and `llm_model_name: str = "gpt-4o-mini"` to `Settings`. Added to `.env.example`.
- **Dependency**: Added `openai>=1.58.0` to `services/api/pyproject.toml`.
- **Debug script**: `scripts/llm_analysis_debug.py` — accepts `--riot-account-id` or `--riot-id`, `--champion` (required), `--rank-tier`, `--dry-run`. Make: `make llm-analysis-debug RIOT_ID="damanjr#NA1" CHAMPION=157 [DRY_RUN=1]`. Imports shared helpers from `llm_analysis.py` (no code duplication).
- **Tests**: 35 new tests across 4 files — `test_llm_prompt.py` (11), `test_llm_response_schema.py` (12), `test_llm_client.py` (6), `test_llm_analysis_job.py` (6). Total: 160 tests pass.
- **Doc**: `docs/LLM_DATA_PIPELINE.md` updated — steps 7-8 marked Done; runbook, key files, and next steps revised.

---

## Recent Changes (2026-03-17, LLM pipeline step 6 — Compare)

### Step 6 — Action comparison (pure sync, no DB)

- **Service**: `app/services/action_comparison.py` — pure sync function consuming step 5 `list[ActionAggregate]`. Groups by (champion_id, rank_tier, action_type), ranks actions by effective ΔW (personal K≥50, else population fallback), computes improvement gaps (summoner's most-used items vs. rank-1 alternative), detects selection bias (W(x) ≥ 0.55 + ΔW below group median).
- **Output**: `ComparisonResult` with `ComparisonGroup`, `RankedAction`, `ImprovementGap`, `SelectionBiasFlag`. Serializable to `LLMAnalysis.input_payload` via `dataclasses.asdict()`.
- **Post-review fix**: Removed top-level `champion_id` and `rank_tier` from `ComparisonResult` — these were arbitrarily set from the first group and misleading for multi-champion analysis. Each `ComparisonGroup` carries its own champion/rank context.
- **Debug script**: `scripts/compare_actions_debug.py` — accepts `--riot-account-id` or `--riot-id`, optional `--champion` / `--rank-tier`. Make: `make compare-actions-debug RIOT_ACCOUNT_ID=<uuid>` or `RIOT_ID="name#NA1"`.
- **Tests**: `services/api/tests/test_action_comparison.py` — 14 tests (ranking, fallback, gaps, bias detection, serialization).
- **Doc**: `docs/LLM_DATA_PIPELINE.md` updated — step 6 marked Done; steps 7-8 remain.

---

## Recent Changes (2026-03-16, code review + doc sync)

### Aggregation refactor + debug script fix (from code review)

- **Single-query consolidation**: `action_aggregation.py` rewritten from two separate queries (personal, then population with bind-parameter IN expansion) into a single SQL statement with `personal_agg` and `population_agg` CTEs. Population CTE now filters via subquery (`SELECT DISTINCT champion_id, rank_tier FROM personal_agg`) instead of expanding `(:cr_c0, :cr_r0), ...` pairs.
- **Simplified query builder**: `_build_personal_sql` and `_build_population_sql` replaced with single `_build_query(champion, rank_tier)` that returns the full SQL + filter params.
- **Debug script**: `scripts/aggregate_actions_debug.py` now uses `python-dotenv` for env loading; runs from project root (sys.path includes `services/api`) and formats stats via a helper so `mean_ΔW` / `mean_W(x)` / `stddev_ΔW` print as `N/A` instead of crashing when values are missing.
- **Tests updated**: Reflect new single-query structure; population subquery assertion replaces bind-param assertions.

### Documentation sync

- **`TECHNICAL_ARCHITECTURE_AND_PATTERNS.md`**: Pipeline steps 3-5 updated from "(future)" to implemented status. Added `action_aggregation.py`, `win_prob_features.py`, `win_prob_scoring.py` to service table. Added `score_actions_job` to jobs list. Test count corrected (42 → 106). Roadmap updated (steps 6-8 remaining). Fixed duplicate `### 4.3` header.
- **`WIN_PROB_MODEL_NOTES.md`**: Added "Aggregation stability" subsection on model versioning implications for step 5.

### LLM pipeline tooling — batch scoring helper

- **Make target**: Added `make score-account-matches RIOT_ACCOUNT_ID=<uuid>` (and `RIOT_ID=name#TAG` variant) to enqueue `score_actions_job` for all unscored matches tied to a given `riot_account` in the database.
- **Dry run helper**: Added `make score-account-matches-dry` to print how many matches would be scored for an account without enqueueing any jobs.
- **Stats helper**: Added `make account-match-stats RIOT_ACCOUNT_ID=<uuid>` / `RIOT_ID=name#TAG` to print `total_matches`, `scored_matches` (with `delta_w`), and `remaining_to_score` for an account.
- **Debug output**: `scripts/aggregate_actions_debug.py` now decorates `action_key` with human-readable labels — item purchases show the Data Dragon item name plus item ID, and objective kills show friendly labels (e.g. "Dragon (DRAGON)", "Baron Nashor (BARON_NASHOR)").
- **Docs**: `docs/LLM_DATA_PIPELINE.md` updated so Step 4 (Score Actions) references the new batch helper, dry-run variant, and stats helper instead of a raw `docker exec psql | xargs make score-actions` shell one-liner.

### Champion metadata helper

- **Script**: `scripts/print_champion_ids.py` — fetches the latest Data Dragon champion catalog via `DdragonClient` and prints a JSON map of `champ_id -> name`.
- **Make target**: `make print-champion-ids` — convenience wrapper around the script for quickly looking up Riot numeric champion IDs from the terminal.

---

## Recent Changes (2026-03-10, LLM pipeline step 5 — Aggregate)

### Step 5 — Action aggregation (read-only, V1)

- **Service**: `app/services/action_aggregation.py` — read-only SQL aggregations on `match_action` joined to `match` and `riot_account_match`. Groups by champion_id (from game_info participants), rank_tier (from first `match_state_vector.features['average_rank']`), action_type, action_key (item_id or monster_type), opponent_damage_bucket (V1: "mixed").
- **API**: `aggregate_action_stats_for_player(session, riot_account_id, champion=None, rank_tier=None)` returns `list[ActionAggregate]`. Each item has `group_key`, `personal_stats` (count, mean_delta_w, mean_pre_win_prob, stddev_delta_w), `population_stats` for same bucket, and `insufficient_personal_sample` when personal K < 50. Population query restricted to (champion_id, rank_tier) pairs from the player's data; IN clause expanded for asyncpg.
- **Constants**: `MIN_PERSONAL_SAMPLE_SIZE = 50`, `OPPONENT_DAMAGE_BUCKET_V1 = "mixed"`.
- **Debug script**: `scripts/aggregate_actions_debug.py` — accepts `--riot-account-id` or `--riot-id`, optional `--champion` / `--rank-tier`; prints aggregates. Make: `make aggregate-actions-debug RIOT_ACCOUNT_ID=<uuid>` or `RIOT_ID="name#NA1"`.
- **Tests**: `services/api/tests/test_action_aggregation.py` — 12 tests (helpers, SQL builders, merge + K≥50 flag).
- **Doc**: `docs/LLM_DATA_PIPELINE.md` updated — step 5 marked Done; key files and next steps revised.

---

## Recent Changes (2026-03-09, LLM pipeline step 4)

### Step 4 — Scoring service + score_actions_job

- **Scoring service**: `app/services/win_prob_scoring.py` — `load_model()` (from optional `WIN_PROB_MODEL_PATH`), `score_state(features)` returns w(x) in [0, 1] or None when model not loaded. Feature order and rank encoding in `app/services/win_prob_features.py` (shared with training script).
- **Training script**: `scripts/train_win_prob_model.py` — reads CSV from export, fits logistic regression, saves joblib (default `data/win_prob_model.joblib`). Run after exporting training data; set `WIN_PROB_MODEL_PATH` in API/worker env to enable scoring.
- **score_actions_job**: `app/jobs/score_actions.py` — for a given match_id, loads state vectors and actions, scores pre/post states, persists `delta_w`, `pre_win_prob`, `post_win_prob` on each `match_action`. Idempotent; returns skipped when model not loaded. Registered in `WorkerSettings.functions`.
- **Config**: `win_prob_model_path: str = ""` added to Settings; empty disables action scoring.
- **Doc**: `docs/LLM_DATA_PIPELINE.md` updated — steps 3 and 4 marked Done; key files and next steps revised.
- **Helper script**: `scripts/score_actions_for_match.py` + `make score-actions MATCH_ID=NA1_...` helper to enqueue `score_actions_job` for a single match via ARQ (requires `make worker-dev` and `WIN_PROB_MODEL_PATH` set in worker env).

### Env loading for scoring helper (2026-03-10)

- **Change**: `scripts/score_actions_for_match.py` now loads env vars from `services/api/.env` (if present) before resolving `REDIS_URL`, falling back to shell env and then the hardcoded default.
- **Why**: Keeps the scoring helper consistent with API/worker configuration without requiring manual `export REDIS_URL=...` in the shell.

---

## Recent Changes (2026-03-09)

### Export training data: normalize JSONB from asyncpg

- **Change**: `scripts/export_training_data.py` now normalizes JSONB column values to dicts before use. When using raw asyncpg (no ORM), JSONB can be returned as JSON strings; the script now uses `_normalize_game_info()` for `game_info` and `_normalize_jsonb_dict()` for `features`, so it works whether the driver returns dict or str.
- **Why**: Avoids `AttributeError: 'str' object has no attribute 'get'` when running the export. Export run verified: 1586 rows from 245 matches written to CSV.

### Match card layout tweak

- **Change**: Updated `MatchCard` layout so the main match summary columns and the champion KDA chart sit side by side on desktop, while remaining stacked on mobile/tablet via responsive flex styles.

### Match list: backend year filter for current-season views

- **Change**: Both match-list endpoints now support an optional `year` query parameter:
  - `GET /search/{riot_id}/matches?...&year=2026`
  - `GET /riot-accounts/{id}/matches?...&year=2026`
- **Backend behaviour**:
  - `list_matches_for_riot_account()` accepts a `since_ts` filter; when set, it limits both `data` and `total` to matches with `game_start_timestamp >= since_ts` (calendar year start in ms), excluding null timestamps.
  - `search.py` and `matches.py` compute `since_ts` from `year` using `datetime(..., tzinfo=UTC)`; direct function calls in tests still work because the routers treat non-int defaults (FastAPI `Query` objects) as `None`.
  - All existing 429 / stale-meta semantics are unchanged; year filtering only affects which rows are considered and counted.
- **Frontend wiring**:
  - `/home`: `matchesUrl` now calls `/riot-accounts/{riotAccountId}/matches?page=X&limit=20&year=<currentYear>` so the authenticated dashboard shows a consistent \"this season\" view.
  - `/riot-account/[riotId]`: `matchesUrl` now calls `/search/{riotId}/matches?page=X&limit=20&year=<currentYear>` so searching another account also shows only current-year matches.
  - `useMatchList.loadMoreMatches` still has a defensive current-year filter, but the authoritative boundary is now enforced on the backend; refreshes no longer reveal older-year matches or bump totals unexpectedly after a load-more that crossed the year boundary.

### Live-game stream logging crash fix (+ ARQ jobs)

- **Issue**: When Riot returned 401 (or any `RiotRequestError`), handlers that logged with `extra={"message": exc.message}` triggered Python's reserved `LogRecord.message`, causing `KeyError: "Attempt to overwrite 'message' in LogRecord"` and crashing the stream or ARQ worker.
- **Fix**: Replaced `"message"` with a non-reserved key in logger `extra` and error payloads. All such keys are now **`error_message`** (live_game.py, timeline_extraction.py, match_ingestion.py). SSE live-game error payload uses `error_message`; frontend `LiveGameErrorPayload` type updated to match. Global HTTP exception handler in exceptions.py still returns `detail` in the response body for API compatibility.
- **Clarification**: `staleMessage` on the frontend is only for match-list 429 fallback (from `PaginationMeta.stale` / `stale_reason`). The live-game stream is a separate SSE endpoint; it does not set pagination meta, so no stale message is expected when the stream fails. To show a user-visible warning on live-game errors (e.g. 401/429), the frontend would need to handle the stream's `error` events (optional enhancement).

### Global warning for 401 and other Riot API failures

- **Goal**: Show the same amber global warning when any Riot-backed request fails with 401 (or other non-200/500): fetch_rank, live-game stream, and match list.
- **Frontend** (page-level aggregation, no context):
  - **stale-message.ts**: Added reason `"riot_unavailable"` with message "Riot API is temporarily unavailable. Some data may be cached or missing."
  - **useRank**: Added `rankStaleReason` state; on fetch failure with `isApiError` and status/riotStatus not 200 and not 500 (e.g. 401, 403, 429), set `"riot_unavailable"`. Return `rankStaleMessage = getStaleMessage(rankStaleReason)`.
  - **useLiveGame**: Added `liveGameWarning` state; when stream emits `error` (or connection error), set to `getStaleMessage("riot_unavailable")`; clear on live/not_in_game or reconnect. Return `liveGameWarning` in hook result.
  - **home/page.tsx** and **riot-account/[riotId]/page.tsx**: `warning = staleMessage ?? rankStaleMessage ?? liveGameWarning ?? null`; pass to `MatchPageShell`. So 401 from fetch_rank or live-game stream now shows the amber banner.

### Home initial load: latest matches + single request

- **Issue 1 — Stale matches on first load:** Auth matches endpoint fetches fresh match IDs from Riot only when `?refresh=true` (page 1) or `after>0`. Initial /home load used `page=1&limit=20` with no refresh, so the API returned DB-only data (last synced on a previous Refresh or see-more). User had to click Refresh to see latest.
- **Fix 1:** In **useMatchList**, the very first page-1 fetch (when `allMatches.length === 0`) now sends `refresh: true` via a ref `initialPage1FetchDoneRef`. So the first load of /home (or first load after switching account via `resetKey`) hits the backend with refresh and gets latest match IDs; no manual Refresh needed.
- **Issue 2 — Two matches API requests on initial load:** In development, React 18 Strict Mode double-invokes effects (mount → effect → cleanup → remount → effect again). Both runs saw `allMatches.length === 0` and each started a fetch.
- **Fix 2:** **useMatchList** uses an `AbortController` per effect run: the effect passes `controller.signal` to `apiGet` (via **api.ts** `ApiFetchOptions.signal`); on cleanup we call `controller.abort()`. The first run’s request is aborted when Strict Mode cleans up; the second run’s request completes and updates state. So only one response is applied and loading is cleared. Abort errors are ignored in the catch block so they are not reported to the user.

---

## Recent Changes (2026-03-07)

### Riot API call gating (account once, fresh match IDs when appropriate)

- **Account/summoner**: Riot is called only when the account is not in DB (first sync). `GET /search/{riot_id}/account` and sign-in use DB only when account exists; sign-in no longer refreshes account from Riot.
- **Match IDs**: Fetched from Riot on first sync (account just created), on explicit refresh (`?refresh=true` on page 1), and on see more (`after>0`). Otherwise match list is served from DB. Match detail and timeline are only requested from Riot when not already stored/cached.
- **Backend**: Search router resolves account via `get_riot_account_by_riot_id` first; first sync when missing; page 1 without refresh uses DB only; `refresh` and see-more paths fetch fresh match IDs, upsert, backfill, enqueue timelines. Matches router: page 1 DB-only unless `refresh=true`; see more fetches fresh match IDs. `riot_sync.fetch_sign_in_user` no longer calls Riot — returns existing user + account from DB.
- **Frontend**: `useMatchList` passes `refresh=true` when the user clicks Refresh (`matchesUrl(page, { refresh: true })`). Home and riot-account pages build match URLs with optional `&refresh=true`.

### 429 rate-limit graceful degradation

- **Goal**: When Riot API returns 429 on page-1 sync, return cached matches from DB with a `stale` signal instead of a blank error screen.
- **Backend**:
  - `PaginationMeta` now has `stale: bool` and `stale_reason: str | None`; `PaginationMeta.build()` accepts and forwards them.
  - **matches.py** (page 1): Page-1 block wrapped in `try/except RiotRequestError`. On `exc.status == 429` set `sync_skipped = True`, `sync_skip_reason = "rate_limited"`, log warning, fall through to `resolve_riot_account_identifier` and DB query. After query: if `sync_skipped and total == 0` → raise `HTTPException(429, detail="riot_api_max_retries_exceeded")`. Pass `stale`/`stale_reason` to `PaginationMeta.build()`.
  - **search.py** (page 1): On 429 in existing `except RiotRequestError`, set `sync_skipped`, resolve account via `get_riot_account_by_riot_id`; if no account or 0 matches → raise 429. Pass `stale`/`stale_reason` to meta.
  - **Global backoff**: When the rate limiter is in global backoff, **search.py** and **matches.py** mark DB-only responses as stale: before building `PaginationMeta`, if `not sync_skipped` and `await get_rate_limiter().is_globally_backing_off()`, set `stale=True` and `stale_reason="rate_limited"`. Backoff is set in two cases: (1) **429 from Riot** — `set_retry_after(seconds, reason="429")` in the API client when Riot returns 429 with Retry-After. (2) **Proactive limiter** — when the app's sliding-window limiter blocks in `wait_if_needed` (e.g. app_long at 100/100), we call `set_retry_after(sleep_time, reason="proactive")` before sleeping so navigating to another account during the wait still returns 200 with `stale_reason` and the frontend shows the amber warning. **Redis persistence**: Backoff is stored in Redis (`riot_rate_limited_until`) by `set_retry_after`; `is_globally_backing_off()` checks in-memory then Redis so all workers see the same state.
  - **Tests**: `test_rate_limit_fallback.py` — 6 tests (matches 429+cached → 200+stale, matches 429+no data → 429, matches non-429 propagates; search 429+cached → 200+stale, search 429+no account → 429, search 429+0 matches → 429). Updated `test_search_router_page2.py::test_search_page1_riot_429_maps_to_http_429` to mock `get_riot_account_by_riot_id` returning None so 429 path is exercised without real DB.
- **Frontend**:
  - `PaginationMeta` type in `match.ts`: added `stale?`, `stale_reason?`.
  - **useMatchList**: `staleReason` state set from `meta?.stale_reason ?? (meta?.stale ? "cached" : null)` on fetch success so the shell warning shows even when backend sends `stale: true` without `stale_reason`; reset in `handleRefresh` and `resetKey` effect. `staleMessage` from `getStaleMessage(staleReason)` (`league-web/src/lib/stale-message.ts`). **Stale message fix (navigate after rate limit)**: (1) `apiGet` uses `cache: 'no-store'` when `useCache: false` so the browser does not serve an old cached response that lacks `stale_reason`. (2) Main fetch, `loadMoreMatches`, and polling all set `staleReason` from `meta?.stale_reason` or fallback to `"cached"` when `meta?.stale === true`. Backend logs `search_matches_stale_global_backoff` / `list_matches_stale_global_backoff` when marking responses stale due to global backoff.
  - **MatchPageShell**: New optional `warning?: string | null` prop; rendered as `<p className={styles.warning}>` above error slot. `.warning` in CSS: amber color, light background, left border.
  - **home/page.tsx** and **riot-account/[riotId]/page.tsx**: Destructure `staleMessage` from `useMatchList`, pass as `warning` to `MatchPageShell`.

### Safety-net inline backfill removed

- **Removed** `backfill_match_details_inline` from `riot_sync.py` and from both match-list routers (search, matches). It was a post-query fallback that fetched Riot details inline when result rows had null `game_info` (rare: partial failures, races).
- **Rationale**: Simplifies the model — only two paths now populate `game_info` (ARQ job and pre-query `backfill_match_details_by_game_ids`). Avoids request-path Riot calls and latency for an edge case; if a row is missing details, the worker will backfill later.
- **Kept** `backfill_match_details_by_game_ids` (pre-query backfill before ordering) so new matches from first sync / refresh / see more still get timestamps and sort correctly on first request.

---

## Recent Changes (2026-03-06)

### Rank data shared across home and riot-account pages

- **useRank hook** (`league-web/src/lib/hooks/useRank.ts`): Fetches `GET /riot-accounts/{id}/fetch_rank` when `riotAccountId` is set; re-runs on `riotAccountId` or `refreshIndex` change. Returns `{ rank, rankSubtitle }` with subtitle formatted as "Queue · Tier Rank · N LP" or "Rank data unavailable". Debug logging: `[useRank] fetch start/done/fail`.
- **Home** (`league-web/src/app/home/page.tsx`): Removed local `rank` state and rank `useEffect`; uses `useRank(riotAccountId ?? null, { refreshIndex })` and passes `rankSubtitle` to `SubHeader` as before.
- **Riot-account** (`league-web/src/app/riot-account/[riotId]/page.tsx`): Uses `useRank(account?.id ?? null, { refreshIndex })` and passes `subtitle={rankSubtitle}` to `SubHeader` so the search result view shows rank under the title.

### Live game: gate on matches ready, single attempt, status UI

- **useLiveGameWhenReady(puuid, matchesReady)**: New composed hook in `league-web/src/lib/hooks/useLiveGameWhenReady.ts`. Calls `useLiveGame` only when `matchesReady` is true (e.g. `!isLoading` from `useMatchList`), so live-game fetch runs after match list is loaded. MatchPageShell stays presentational (no hooks).
- **useLiveGame** (single attempt): Removed auto-retries. Connects once; on first `live_game` / `not_in_game` / `error` or connection failure, sets status and closes the EventSource. Returns `{ liveGame, isLive, status, retry }` with `status`: `'idle' | 'connecting' | 'live' | 'not_in_game' | 'error'`. `retry()` increments an attempt key to trigger one new connection.
- **LiveGameSlot** (`league-web/src/components/LiveGameSlot/`): Presentational component for the live-game slot. Renders `LiveGameCard` when live; "No live game." + "Fetch live game" button when `not_in_game`; "Please try again." + "Fetch live game" button when `error`; "Checking for live game…" when `connecting`. Used by home and riot-account pages so message/button copy lives in one place.
- **Pages**: Home and `/riot-account/[riotId]` now use `useLiveGameWhenReady(puuid, !isLoading)` and pass `<LiveGameSlot status={...} liveGame={...} targetPuuid={...} onRetry={retry} />` to MatchPageShell.

### Match list pagination rewrite (`useMatchList`)

- **Accumulate-then-slice**: Matches are stored in one list (`allMatches`). The table always shows a slice for the current page: `matches = allMatches.slice((page-1)*limit, page*limit)`. Pagination meta is derived from `total = max(totalFromApi, allMatches.length)` and `last_page = ceil(total/limit)`.
- **Fetch behavior**: Initial load fetches page 1 and sets the list. Navigating to page N fetches only when `allMatches.length < page*limit` and merges (replaces that page’s segment). So Next accumulates pages; Previous just changes `page` and uses existing data — no refetch, no clearing `matchDetails`.
- **See more**: Fetches with `after=allMatches.length`, appends the new batch to `allMatches`, then sets `page` to the page that contains the first new item (`floor(offset/limit)+1`). So e.g. 73 matches + 20 new → stay on page 4 (20 rows: 13 old + 7 new); 20 + 20 → go to page 2 (20 new rows). Total and last_page update from the new length.
- **Previous bug fixed**: We no longer clear `matchDetails` on page change or refetch when going back; the slice comes from accumulated matches and details stay in sync.
- **Removed**: Virtual page / `hasLoadedMore` / `realLastPageRef` / `loadMorePage`; polling now merges into the current page’s segment of `allMatches`.

### Background job rate-limit retry hardening (`llm-phase-0`, session 2)

- **Bug fixed**: `extract_match_timeline_job` permanently failed when the rate limiter exhausted its internal 5-retry budget — `RuntimeError` from `wait_if_needed` was uncaught, causing ARQ to mark the job as permanently failed.
- **`rate_limiter.py`**: Added `match_timeline` to `METHOD_LIMITS` (`2000 req / 10s`) alongside `match_detail`, enabling per-method tracking for timeline requests.
- **`timeline_extraction.py`**: Catches `RuntimeError` containing `"Rate limit"` and raises `arq.Retry(defer=120)` — re-enqueues the job with a 2-minute delay instead of failing permanently.
- **`background_jobs.py`**: Wrapped `extract_match_timeline_job` with `func(..., max_tries=5)` to cap ARQ-level retries at 5 attempts (~10 min total).
- All existing matches now have state vectors populated via `scripts/backfill_extraction.py` (script kept for future re-extraction needs).

### LLM Pipeline Wiring (Steps 1–2 → auto-trigger, Step 3 prep)

- **Registered `extract_match_timeline_job`** in `WorkerSettings.functions` (`background_jobs.py`) — ARQ worker can now process extraction jobs.
- **Created `enqueue_timeline_extraction.py`** — enqueue service that checks `match_state_vector` for idempotency, filters to matches with `game_info`, enqueues one job per match with deterministic `_job_id`.
- **Wired `fetch_match_details_job` → `extract_match_timeline_job`** — after successfully persisting `game_info`, the details job now auto-enqueues extraction for successfully-fetched matches.
- **Added ML dependencies** — `scikit-learn>=1.5.0` and `numpy>=1.26.0` to `pyproject.toml` for the V1 logistic regression model.
- **Created `scripts/export_training_data.py`** — standalone script to export `match_state_vector` features + match outcomes as CSV for model training. Implements per-match 5-minute interval sampling per thesis anti-overfitting strategy.
- **Fixed merge conflict** in `test_riot_api_client_retry.py` — resolved conflict markers, removed broken debug prints referencing undefined variables in `test_riot_api_client_match_fetch.py` and `test_riot_api_client_retry.py`. Test count now 88/88 (was 42/42 pre-merge).

---

## Recent Changes (2026-03-03)

### Pagination feature (`frontend-matches-paginated`)

- Added `PaginationMeta` and `PaginatedMatchList` response schemas with `PaginationMeta.build()` helper.
- `list_matches_for_riot_account` now accepts `page`/`limit` and returns `tuple[list[Match], int]` using `func.count()` + `offset()`/`limit()`.
- Both match endpoints (`/riot-accounts/{id}/matches`, `/search/{riot_id}/matches`) return `PaginatedMatchList` with `?page=N&limit=N` query params.
- Riot API sync gated to page 1 only — page 2+ queries DB directly, skipping Riot API calls entirely.
- Search endpoint on page 2+ resolves riot account from DB via `get_riot_account_by_riot_id` instead of hitting Riot API.
- New `Pagination` component with Previous/Next controls and "Page X of Y" display.
- `MatchesTable` accepts optional `paginationMeta`/`onPageChange` props; renders `<Pagination>` below the table.
- Home and Search pages manage `page` state, pass pagination to `MatchesTable`, clear `matchDetails` on page change, scroll to top.
- Search page resets `page` to 1 when `riotId` changes.
- Tab filtering remains client-side (some pages may show fewer items after tab filter — acceptable trade-off).

### Bug fix — account re-fetch on page change (`frontend-matches-paginated`, session 2)

- **Root cause**: the combined `Promise.all` effect in `riot-account/[riotId]/page.tsx` included `page` in its dependency array, causing the `/search/{riotId}/account` endpoint to be called on every page navigation — firing `fetch_account_by_riot_id` + `fetch_summoner_by_puuid` against the Riot API unnecessarily and contradicting the PR's stated goal of avoiding rate-limit consumption on page 2+.
- **Fix**: split the single combined effect into two independent effects:
  - **Account effect** (deps: `[riotId, decodeError, clearError, reportError]`) — fetches `/search/${encodedQuery}/account` once per searched summoner; never triggered by `page`.
  - **Matches effect** (deps: `[riotId, decodeError, page, clearError, reportError]`) — fetches `/search/${encodedQuery}/matches?page=N` on every page or riotId change; does not touch the account endpoint.
- Decode-error guard preserved in both effects without introducing a race that could clear the page error.
- Each effect has its own `isActive` cancellation flag and independent error handling.
- **File changed**: `league-web/src/app/riot-account/[riotId]/page.tsx`

### Previous changes

- Consolidated MatchCard redesign documentation into `docs/MATCHCARD_REDESIGN.md`.
- Replaced match history card grid with table + side panel.
- Queue-type tab filtering, champion preloading, keyboard accessibility improvements.

---

## Request Flow Summary

```
User → Search (Riot ID) → GET /search/{riot_id}/matches?page=1
  → find_or_create_riot_account (DB upsert)
  → Rate limit check (Redis)
  → Fetch match IDs (Riot API)
  → Upsert match IDs (DB)
  → Backfill basic details inline (Riot API)
  → Return paginated match list + meta

User → Page 2+ → GET /search/{riot_id}/matches?page=N
  → Resolve riot account from DB (no Riot API)
  → Return paginated match list + meta

Background (async):
  → Enqueue timeline warmup → Redis/ARQ
  → Fetch timeline (Riot API) → Cache `timeline:{match_id}`

Optional:
  → Sign In/Up → POST /users/sign_in → Validate (DB) → Save session
```

---

## Recent Changes (2026-03-03, session 3)

### Step 1 — Per-Player Rank Badges

- **Backend**: New `GET /rank/batch?puuids=<csv>` endpoint (`routers/rank.py`). Fetches up to 10 PUUIDs concurrently via `asyncio.gather`. Caches each PUUID individually in Redis (`rank:{puuid}`, TTL 1h). Registered in router registry.
- **Frontend**: `MatchesTable` fetches `/rank/batch` via `useEffect` keyed on `selectedMatchId`. Only fetches PUUIDs not already in `rankByPuuid` cache. Passed down: `MatchesTable` → `MatchDetailPanel` → `MatchCard` → `Teams`. Each `PlayerRow` in `Teams` renders a `.rankBadge` span (purple, 10px) when rank data is available.

### Step 2 — Timeline API (Laning Phase Analytics)

- **Backend**: `fetch_match_timeline()` added to `RiotApiClient` (`MATCH_TIMELINE_URL + /timeline`). New `fetch_timeline_stats()` in `riot_sync.py` — fetches timeline, caches raw JSON in Redis indefinitely (`timeline:{matchId}`), parses CS/gold diffs at frames 10 and 15, identifies lane opponent by `individualPosition` on opposing team. New `LaneStats` Pydantic model in `schemas/match.py`. New `GET /matches/{matchId}/timeline-stats?participant_id=N` endpoint — returns compact `LaneStats`, never ships 1MB timeline to client.
- **Frontend**: `MatchesTable` fetches `/matches/{matchId}/timeline-stats` on expand (keyed on `selectedMatchId + matchDetails`). Result stored in `laneStatsByMatchId`. Passed to `MatchCard` via `MatchDetailPanel`. `MatchCard` renders `CS@10`, `CS@15`, `G@10` diffs in a `.laningRow` below the CS stat — blue for positive, red for negative.

### New CSS (`MatchCard.module.css`)

- `.rankBadge` — purple 10px label next to summoner name in Teams
- `.laningRow`, `.laningStat`, `.laningPos`, `.laningNeg` — laning diff display

## Recent Changes (2026-03-03, session 4)

### Bug fix — timeline-stats always returning 404

- **Root cause**: `fetch_timeline_stats` read participant metadata (`individualPosition`, `teamId`, `championName`) from `timeline["info"]["participants"]`, but the Riot `/matches/{matchId}/timeline` endpoint only returns `participantId` + `puuid` per participant. Those fields are only present in the match detail response (`/matches/{matchId}`). So `current_pos` was always `""`, `opponent_meta` was always `None`, `result` was always empty, and `return result or None` returned `None` → 404.
- **Fix** ([riot_sync.py](services/api/app/services/riot_sync.py)): replaced `p_info_list = (timeline.get("info") or {}).get("participants") or []` with `p_info_list = (match.game_info.get("info") or {}).get("participants") or []` — using the already-loaded `match` record's `game_info` JSONB column, which has the full participant details.
- **Tests** ([test_riot_api_client_match_fetch.py](services/api/tests/test_riot_api_client_match_fetch.py)): 5 new unit tests with scripted `httpx` clients verifying:
  - `fetch_match_by_id` returns the payload and calls the correct URL (no `/timeline`).
  - `fetch_match_timeline` returns the payload and calls the correct URL (with `/timeline`).
  - The timeline URL is exactly the match detail URL + `/timeline` — same Riot match ID, no UUID drift between the two endpoints.

## Recent Changes (2026-03-03, session 5)

### Bug fix — hard-coded frame indices in `fetch_timeline_stats`

- **Root cause**: `frames[10]` and `frames[15]` assumed a 60-second `frameInterval`, never validating the `frameInterval` field from the timeline response. If Riot changes the interval the indices would silently reference wrong timestamps.
- **Fix** ([riot_sync.py](services/api/app/services/riot_sync.py) lines 310–327): reads `timeline_info["frameInterval"]` (ms, default `60_000`) and computes `idx_10 = round(10 * frames_per_minute)` / `idx_15 = round(15 * frames_per_minute)`. All four frame accesses (current + opponent at 10 and 15 min) now use `idx_10`/`idx_15`.

---

## Recent Changes (2026-03-04)

### Railway Deploy Hardening (Healthcheck Stability)

- **Root cause addressed**: API startup previously ran `alembic upgrade head` before binding `$PORT`, which could delay startup and trigger Railway `Network › Healthcheck failure` under transient DB slowness.
- **Startup change**: `services/api/entrypoint.sh` now starts Uvicorn immediately (no migration step in runtime boot path).
- **Release step added**: new `services/api/release.sh` runs `alembic upgrade head` for Railway Pre-Deploy/Release execution.
- **Docker image update**: `services/api/Dockerfile` now marks both `entrypoint.sh` and `release.sh` executable.
- **Docs updated**: `docs/RAILWAY_API_DEPLOYMENT.md` now specifies:
  - API Start Command: `/workspace/services/api/entrypoint.sh`
  - API Pre-Deploy/Release Command: `/workspace/services/api/release.sh`
  - Worker must be private (no public domain/networking) and no HTTP healthcheck path.

**Status impact**: deployment startup path is now faster and less likely to fail healthchecks due to migration latency.

**Open operational note**: Railway dashboard must be configured to run `release.sh` as pre-deploy/release command for API service.

**Next recommended steps (deployment validation)**:

1. Confirm API service deploy settings include release command.
2. Confirm worker service has no public domain and no HTTP healthcheck.
3. Trigger deploy and verify logs show release migrations before API boot and stable `/health` pass.

### Champion KDA History Chart (`frontend-chart`)

- **New dependency**: `recharts` installed in `league-web/`
- **New type**: `ChampionKdaPoint` added to `league-web/src/lib/types/match.ts` — `{ matchId, kills, deaths, assists, outcome, timestamp }`
- **MatchesTable**: new `championHistoryByMatchId` useMemo groups all loaded matches by `championId`, sorts oldest→newest, passes `championHistory` array to `MatchDetailPanel` via prop
- **MatchDetailPanel**: threads `championHistory` straight through to `MatchCard` (no logic change)
- **MatchCard**: added `ChampionKdaChart` internal sub-component (recharts `BarChart`, height 100px). Current match bar = white; wins = blue-tinted; losses = red-tinted. X-axis shows M/D date labels from `timestamp`. Renders only when `history.length >= 2`. Chart sits below the 4 flex columns via `flex: 0 0 100%; order: 99` — no layout changes to existing columns.
- **CSS**: appended `.kdaChart`, `.kdaChartLabel`, `.kdaTooltip` to `MatchCard.module.css`
- **No backend changes** — all data was already available in `matchDetails`

---

## Recent Changes (2026-03-04, session 2)

### Phase 1 Frontend Refactor — Folderize (`frontend-components-refactor`)

- **What changed**: Folderized all 10 components in `league-web/src/components/` — each component now lives in its own subdirectory with its CSS module. Zero logic changes.
- **New structure**: `Auth/`, `FeatureCard/`, `Header/`, `MatchCard/`, `MatchDetailPanel/`, `MatchesTable/`, `MatchRow/`, `Pagination/`, `SearchBar/`, `SubHeader/`
- **Barrel files added**: `MatchCard/index.ts` and `MatchesTable/index.ts` (re-export defaults; will grow in Phase 2/3)
- **Import path fixes**: All `../lib/` → `../../lib/` inside moved components; cross-component imports updated (`MatchesTable` → `../MatchRow/MatchRow`, `../MatchDetailPanel/MatchDetailPanel`, `../Pagination/Pagination`; `MatchDetailPanel` → `../MatchCard/MatchCard`); `Auth/SignInForm` + `SignUpForm` retain `./AuthForm` (same folder)
- **Trivial fixes**: Added `type="button"` to all non-submit buttons in `Header`, `Pagination`, `MatchDetailPanel`, and `MatchesTable` tab buttons
- **Verification**: `npm run lint` — 1 pre-existing warning (unchanged); `npm run build` — clean

### Phase 1 Frontend Refactor — Hook Extraction (`frontend-components-refactor`, session 3)

- **What changed**: Extracted hooks and sub-pieces from `MatchesTable.tsx`; zero behavior changes.
- **New files**:
  - `MatchesTable/useMatchSelection.ts` — `selectedMatchId` state + `handleRowClick` / `handleClosePanel` / `clearSelection`
  - `MatchesTable/useMatchDetailData.ts` — all 3 fetch-on-select effects (`championById`, `rankByPuuid`, `laneStatsByMatchId`) with functional updater pattern; `eslint-disable` comments removed from champion and rank effects; timeline effect omits `matches`/`getParticipantForMatch`/`laneStatsByMatchId` from deps (stable within a selection)
  - `MatchesTable/constants.ts` — `COLUMNS` array
  - `MatchesTable/SkeletonRows.tsx` — skeleton row component
- **`MatchesTable.tsx`** slimmed from ~397 → ~215 lines; tab click handlers use `clearSelection()` instead of `setSelectedMatchId(null)`
- **Verification**: `npm run lint` — same 1 pre-existing warning; `npm run build` — clean

## Recent Changes (2026-03-04, session 3)

### Phase 2 Frontend Refactor — MatchCard Decomposition + CSS Var Extraction (`frontend-components-refactor`)

- **What changed**: Decomposed `MatchCard.tsx` (535 lines) into 5 focused files; extracted CSS vars. Zero behavior changes.
- **New files**:
  - `MatchCard/types.ts` — `MatchCardProps`, `TeamsProps`, `ChampionKdaChartProps`, `MultikillEntry`
  - `MatchCard/ItemSlot.tsx` — standalone item slot
  - `MatchCard/Teams.tsx` — memoized teams column (`memo` preserved)
  - `MatchCard/ChampionKdaChart.tsx` — recharts chart; bar fills use `--match-bar-*` CSS vars; X-axis tick fill uses `--match-text-muted`
  - `MatchCard/match-card.utils.ts` — `diffLabel`, `getMultikillBadges`, `getOutcomeDisplay`
- **`MatchCard.tsx`** slimmed from 535 → ~200 lines; now `memo`-wrapped at export
- **CSS vars added to `globals.css`**: `--match-victory-bg`, `--match-defeat-bg`, `--match-remake-bg`, `--match-text-blue`, `--match-text-red`, `--match-text-muted`, `--badge-gold`, `--match-bar-victory`, `--match-bar-defeat`, `--match-bar-remake`
- **`MatchCard.module.css`**: outcome background/border colors, text colors, badge backgrounds, KDA chart label replaced with CSS vars; `laningPos`/`laningNeg` kept as raw hex with an explanatory comment (intentionally distinct shades)
- **Verification**: `npm run lint` — same 1 pre-existing warning; `npm run build` — clean

### Bug fix — champion fetch pre-fetch filter (`useMatchDetailData`)

- **Issue**: Champion effect was requesting every `championIdsToLoad` on each run; only the `setChampionById` updater skipped already-loaded IDs, so network/cache work still ran for all IDs.
- **Fix**: Compute `missingIds = championIdsToLoad.filter((id) => championById[id] == null)` at effect start; early-return if `missingIds.length === 0`; call `apiGet` only for `missingIds`. Dependency array now includes `championById` so the filter sees current state.

---

## Recent Changes (2026-03-05)

### LLM Pipeline Phase 0 — Ingest + Extract (`llm-phase-0`)

- **Design doc overhaul**: [LLM_DATA_PIPELINE.md](docs/LLM_DATA_PIPELINE.md) rewritten from outline to concrete 8-step pipeline spec. Covers game state vector definition (Table 5 features), V1 action types (item purchases + objective kills), win probability model progression (logistic → DNN), aggregation strategy (K≥50, population fallback), and LLM prompt design.
- **3 new DB models** + Alembic migration (`20260305_0002`):
  - `MatchStateVector` — per-minute game state (JSONB features), unique on `(match_id, minute)`
  - `MatchActionRecord` — discrete actions with pre/post state refs and nullable ΔW scoring columns
  - `LLMAnalysis` — future-facing LLM output persistence with schema versioning and token counts
- **State vector extraction** (`services/api/app/services/state_vector.py`): Per-player features (position, level, gold, damage dealt/taken, KDA from events) + per-team objectives (dragons, barons, voidgrubs, turrets, inhibitors) + global (timestamp, rank). Cumulative trackers, nearest-frame snapping. No sub-minute interpolation per thesis.
- **Action extraction** (`services/api/app/services/action_extraction.py`): V1 actions — legendary item purchases (90+ item IDs) and elite monster kills (dragon/baron/herald). Tracks ITEMUNDO/SOLD/DESTROYED for post-state. Clamps post-state to vector range.
- **ARQ job** (`services/api/app/jobs/timeline_extraction.py`): `extract_match_timeline_job` — fetches timeline (Redis-cached, 1h TTL), extracts vectors + actions, persists to DB. Idempotent (skips if vectors exist). Proper `RiotApiClient` lifecycle management.
- **22 tests**: `test_state_vector.py` (10 tests) + `test_action_extraction.py` (12 tests) — comprehensive coverage of extraction logic, edge cases, clamping, team assignment, cumulative tracking.
- **Uncommitted cleanup** (staged): explicit `Float` columns on scoring fields, `dataclasses.replace()` for TeamState snapshots, inlined helper, fixed `RiotApiClient` leak in `_fetch_timeline_cached`.

### Phase 3 Frontend Refactor — MatchRow table row + summary stats (`frontend-refactor-match-row-relationships`)

**Branch:** `frontend-refactor-match-row-relationships`
**Status:** REFACTORING

#### What changed

- **`MatchRow.tsx`** — converted from a card-style component to a proper `<tr>/<td>` table row. Renders inline `MatchDetailPanel` in a full-width expansion `<tr>` when `isSelected`. Keyboard accessible (Enter/Space). Champion icon uses `next/image` with `?` fallback.
- **`MatchRow.module.css`** — new styles: `.rowEven`, `.rowOdd`, `.rowSelected` (blue tint + 2px primary outline), `.cell`, `.champion`, `.championIcon`, `.championIconFallback`, `.panelCell`.
- **`match-utils.ts`** — added `getKdaRatio(participant)` and `getCsPerMinute(participant)` pure helpers.
- **`MatchesTable.tsx`** — added `matchSummaryStats` memo (W/L record + best consecutive-win streak per champion); summary bar rendered above table. Added `championHistoryByMatchId` memo for KDA sparkline data passed to `MatchDetailPanel`.

#### Bug fixes / simplifications (code review session)

- **`useMatchSelection`** — simplified from `Set<string>` multi-selection to `string | null` single-selection. Eliminates `expandedMatchIds` Set, replaces with `selectedMatchId`. `toggleMatch`, `closeMatch`, `clearAll` still exported but now trivially simple.
- **`useMatchDetailData`** — rank/timeline effects now each handle a single `selectedMatchId` string (no `for` loops over a Set). Rank effect replaced fake `AbortController` array with the same `isActive`/cleanup pattern used by timeline.
- **`useMatchDetailData` champion effect** — removed `championById` from dep array (was causing a re-run after every champion load). `setChampionById` updater now bails early before spreading when nothing new to add (`toAdd.length === 0 → return prev`).
- **`championHistoryByMatchId`** — gated behind `selectedMatchId != null`; returns `{}` early when no row is expanded, avoiding full-list iteration on every rank/champion fetch.

#### Open questions

- `queueId` is resolved in both `resolveQueueId` (MatchesTable) and inline in `MatchRow` (line 76). Low-priority duplication; could pass resolved `queueId` as a prop in a follow-up.
- `MatchDetailPanel` is a thin wrapper around `MatchCard` + skeleton + close button. Could be inlined into `MatchRow` in a future cleanup pass.

---

## Recent Changes (2026-03-05, session 2)

### Bug fix — Refresh shows stale matches (requires two presses)

- **Root cause**: On page 1, `fetch_match_list_for_riot_account()` upserts new Match records with `game_info=NULL` / `game_start_timestamp=NULL`. The subsequent `list_matches_for_riot_account()` orders by `game_start_timestamp DESC NULLS LAST`, pushing new matches to the bottom. The inline backfill only operates on the already-returned (old) matches. New matches never get backfilled until the second request.
- **Fix (8 files)**:
  - `riot_sync.py` — new `backfill_match_details_by_game_ids(session, game_ids)` queries Match records by game ID where `game_info IS NULL`, fetches details from Riot API, persists `game_info` + `game_start_timestamp`.
  - `matches.py` — calls `backfill_match_details_by_game_ids()` **before** the ordering query on page 1. Background task switched from detail enqueue to timeline pre-fetch.
  - `search.py` — same pre-query backfill + timeline enqueue swap.
  - `enqueue_match_timelines.py` _(new)_ — `enqueue_missing_timeline_jobs()` enqueues `fetch_timeline_cache_job` per batch with deterministic `_job_id`.
  - `match_timeline_enqueue.py` _(new)_ — fire-and-forget wrapper `enqueue_timelines_background()`.
  - `match_ingestion.py` — new `fetch_timeline_cache_job`: checks Redis (`timeline:{match_id}`), fetches from Riot if absent, caches indefinitely.
  - `background_jobs.py` — registered `fetch_timeline_cache_job` in `WorkerSettings.functions`.
  - `jobs/__init__.py` — exported `fetch_timeline_cache_job`.
- **Why timeline enqueue instead of detail enqueue**: Details are now backfilled inline (pre-query). Background work shifts to pre-caching timelines so row-expand loads instantly.
- **Safety net**: post-query `backfill_match_details_inline()` remains as a fallback for edge cases.
- **Tests**: 19/19 pass. No new lint issues.

### Code review follow-ups (session 3)

- **`enqueue_match_timelines.py`** — added Redis `MGET` pre-filter so only uncached timelines are enqueued (previously enqueued all 20 blindly, relying on job-level Redis check).
- **`riot_sync.py`** — extracted `_backfill_single_match()` and `_commit_and_refresh_backfilled()` helpers; both `backfill_match_details_inline` and `backfill_match_details_by_game_ids` now share the same fetch-and-persist logic instead of duplicating it.
- **`matches.py` / `search.py`** — post-query backfill log level upgraded from `info` to `warning` (event names: `*_backfill_fallback`). If this safety net ever fires, it now stands out in logs.

## Recent Changes (2026-03-05, session 4)

### Backend hardening follow-up — high-impact fixes from review

- **Page-1 sync now respects requested page size**:
  - `GET /riot-accounts/{id}/matches?page=1&limit=N` now fetches `N` Riot match IDs before DB read (was hard-coded to 20).
  - `GET /search/{riot_id}/matches?page=1&limit=N` now fetches `N` Riot match IDs before DB read (was hard-coded to 20).
  - **Why**: avoids partial stale page-1 responses when `limit > 20`.
- **Timeline enqueue `_job_id` collision risk removed**:
  - `enqueue_match_timelines.py` now derives `_job_id` from a SHA-1 hash of the full sorted batch contents, not only first/last IDs + count.
  - **Why**: prevents accidental de-duplication collisions across distinct batches.
- **Timeline frame interval parsing hardened**:
  - `riot_sync.py` now coerces `frameInterval` safely and clamps to at least 1ms before index math.
  - **Why**: prevents divide-by-zero / malformed-payload 500s in `fetch_timeline_stats`.
- **Backfill DB round-trips reduced**:
  - Removed per-row `session.refresh()` calls after successful backfill commit.
  - **Why**: lowers DB chatter without changing endpoint behavior.

**Verification**:

- `make test` — pass (19/19).
- Targeted `ruff check` on edited files still reports pre-existing style noise in those files (import order/line length), with no functional regressions from this change set.

---

## Recent Changes (2026-03-05, session 5)

### Backend bug fix — page-1 stale ordering when `limit > 20`

- **Root cause**: both page-1 routes fetched `limit` Riot match IDs, but pre-query backfill called `backfill_match_details_by_game_ids(...)` without `max_fetch`, so it defaulted to `20`. With `limit=50`, only ~20 newly upserted rows got `game_start_timestamp` before ordering; remaining new rows could still sort stale on first load.
- **Fix**:
  - `services/api/app/api/routers/matches.py` now calls:
    - `backfill_match_details_by_game_ids(session, match_ids, max_fetch=limit)`
  - `services/api/app/api/routers/search.py` now calls:
    - `backfill_match_details_by_game_ids(session, match_ids, max_fetch=limit)`
- **Why**: ensures pre-query backfill capacity matches requested page size so all page-1 candidates can be timestamped before DB ordering.
- **Status**: REFACTORING (no blockers introduced by this fix).

**Verification**:

- `make test` — pass (19/19).
- `npm --prefix league-web run lint` — pass with 1 pre-existing warning in `league-web/src/components/Auth/AuthForm.tsx` (`react-hooks/exhaustive-deps`).
- `make lint` — still fails on pre-existing repo-wide backend lint noise; no new lint errors introduced by this change.

**Next recommended steps**:

1. Add targeted unit tests around `backfill_match_details_by_game_ids(..., max_fetch=limit)` behavior for `limit > 20`.
2. Triage and baseline existing backend `ruff` violations so `make lint` can become a blocking signal again.

---

## Recent Changes (2026-03-05, session 6)

### Backend cleanup — flattened timeline enqueue path

- **Question addressed**: whether the timeline enqueue flow still had avoidable over-structuring (`router wrapper -> enqueue service -> ARQ job`).
- **Result**: yes, it still existed; the router wrapper layer was removed.
- **What changed**:
  - `services/api/app/api/routers/match_timeline_enqueue.py` deleted.
  - `services/api/app/api/routers/matches.py` now schedules background work directly with:
    - `background_tasks.add_task(enqueue_missing_timeline_jobs, match_ids)`
  - `services/api/app/api/routers/search.py` now schedules background work directly with:
    - `background_tasks.add_task(enqueue_missing_timeline_jobs, match_ids)`
  - Both routers now log explicit route-level enqueue start events (`*_enqueuing_timelines`) before dispatch.
- **Why**: removes one indirection layer while preserving behavior (same enqueue service + same ARQ timeline job), making the page-1 sync path simpler to follow and maintain.
- **Current phase/status**: REFACTORING (incremental simplification, no behavior change intended).
- **Blockers / open questions**:
  - None introduced by this cleanup.
  - Existing backend lint baseline still contains pre-existing line-length noise in router files; unchanged in scope.
- **Verification**:
  - `make test` — pass (19/19).
  - `npm --prefix league-web run lint` — pass with 1 pre-existing warning in `league-web/src/components/Auth/AuthForm.tsx` (`react-hooks/exhaustive-deps`).
  - `make lint` — still reports pre-existing backend lint noise; no new functional regressions found.

---

## Recent Changes (2026-03-05, session 7)

### Documentation sync — technical flow docs updated to flattened timeline enqueue path

- **What changed**:
  - Updated `docs/TECHNICAL_REQUEST_FLOW.md` to reflect:
    - direct route-level timeline enqueue (`router -> enqueue service -> ARQ`)
    - pre-query detail backfill + post-query safety-net backfill
    - timeline cache warmup semantics (`timeline:{match_id}`)
  - Updated `docs/TECHNICAL_ARCHITECTURE_AND_PATTERNS.md` to reflect:
    - current page-1 correctness strategy (`backfill_match_details_by_game_ids(..., max_fetch=limit)`)
    - timeline warmup job (`fetch_timeline_cache_job`)
    - explicit flattened enqueue pattern and rationale
    - refreshed "Last Updated" date
- **Why**: existing docs still described an older background detail-enqueue path and wrapper indirection that no longer matched implementation.
- **Current phase/status**: REFACTORING (documentation alignment; no runtime behavior changes).
- **Blockers / open questions**:
  - None introduced by this docs-only update.
- **Next recommended steps**:
  1. Keep request-flow docs synchronized whenever queue/job wiring changes.
  2. Add a short "Flow changed?" checklist item to future backend PR descriptions for `matches.py` / `search.py` edits.

---

## Recent Changes (2026-03-06, session 8)

### Branch review + follow-up execution

- **Review outcome**:
  - Confirmed the highest-priority race-condition blocker remains open in:
    - `services/api/app/services/match_sync.py` (`upsert_matches_for_riot_account` uses select-then-insert flow)
    - `services/api/app/services/riot_account_upsert.py` (`ensure_user_riot_account_link` uses select-then-insert flow)
  - Existing `upsert_riot_account` already includes nested transaction + retry-on-`IntegrityError`, but link and match upserts still need atomic conflict-safe writes.

### 1) Targeted tests for `backfill_match_details_by_game_ids(..., max_fetch=limit)` with `limit > 20`

- **New file**: `services/api/tests/test_riot_sync_backfill.py`
- **Added tests**:
  - `test_backfill_by_game_ids_honors_max_fetch_above_default_20` — validates `max_fetch=25` backfills 25/30 matches and commits once.
  - `test_backfill_by_game_ids_can_fetch_all_when_max_fetch_exceeds_missing` — validates `max_fetch=50` backfills all 30 matches.
- **Why**: guards page-1 correctness for larger `limit` values and prevents regression to implicit 20-fetch behavior.

### 2) Repo-wide backend lint-noise baseline

- **New tooling**:
  - `scripts/update_ruff_baseline.py` — captures and normalizes current ruff violations into `scripts/ruff_baseline.json`.
  - `scripts/check_ruff_new_violations.py` — runs ruff and fails only on violations not present in the baseline.
- **Make targets added**:
  - `make lint-baseline`
  - `make lint-new`
- **Baseline snapshot**:
  - `scripts/ruff_baseline.json` currently tracks **63** known violations.
- **Why**: allows lint to become a reliable blocking signal for _new_ issues while existing noise is burned down incrementally.

### Verification

- `./.venv/bin/pytest services/api/tests/test_riot_sync_backfill.py` — pass (2/2).
- `make test` — pass (21/21).
- `make lint` — still fails on pre-existing repo-wide ruff noise (expected).
- `make lint-new` — pass (no new violations vs baseline).
- `npm --prefix league-web run lint` — pass with 1 pre-existing warning in `league-web/src/components/Auth/AuthForm.tsx` (`react-hooks/exhaustive-deps`).

### Blockers / open questions

- **Still open**: race-condition hardening in `match_sync.py` and `riot_account_upsert.py` remains the top reliability blocker.
- **Operational note**: if large lint cleanup shifts line numbers substantially, refresh baseline via `make lint-baseline`.

---

## Recent Changes (2026-03-06, session 9)

### Lint policy simplification — single strict gate

- **What changed**:
  - `Makefile` now exposes one lint command path: `make lint`.
  - `make lint` now runs:
    - backend Ruff: `./.venv/bin/ruff check services/api services/llm`
    - frontend lint: `npm --prefix league-web run lint`
  - Removed baseline-only targets:
    - `make lint-baseline`
    - `make lint-new`
  - Removed baseline scripts/artifacts:
    - `scripts/update_ruff_baseline.py`
    - `scripts/check_ruff_new_violations.py`
    - `scripts/ruff_baseline.json`
- **Why**: project policy switched to one future-facing lint command with no legacy baseline support.
- **Current phase/status**: REFACTORING (tooling simplification complete; strict lint is now canonical).
- **Blockers / open questions**:
  - None for tooling shape.
  - Any existing backend Ruff violations must now be fixed directly because baseline bypass was removed.

---

## Recent Changes (2026-03-06, session 10)

### Backend lint debt cleanup — strict `make lint` now green

- **What changed**:
  - Ran Ruff auto-fixes across backend services:
    - `./.venv/bin/ruff check services/api services/llm --fix`
  - Ran Ruff formatter to resolve remaining line-length violations:
    - `./.venv/bin/ruff format services/api services/llm`
  - This removed remaining backend Ruff violations (line length/import/order/annotation/unused-import mix) introduced by strict no-baseline policy.
- **Why**: `make lint` was intentionally made strict and was failing on legacy backend Ruff debt; this cleanup makes the single lint gate operational.
- **Current phase/status**: REFACTORING (lint policy fully enforced; backend lint debt removed).
- **Blockers / open questions**:
  - No lint blockers remain.
  - Frontend still has 1 pre-existing ESLint warning in `league-web/src/components/Auth/AuthForm.tsx` (`react-hooks/exhaustive-deps`), but it does not fail `npm run lint`.
- **Verification**:
  - `./.venv/bin/ruff check services/api services/llm` — pass.
  - `make lint` — pass (backend clean; frontend warning unchanged).
  - `make test` — pass (`23/23`).

---

## Recent Changes (2026-03-06, session 10)

### Centralized Riot test payload fixtures + router coverage

- **What changed**:
  - Added live-capture utility:
    - `scripts/capture_riot_test_fixtures.py`
    - Captures and writes canonical Riot fixtures for `damanjr#NA1`:
      - account payload
      - summoner payload
      - match IDs payload
      - match detail payload
      - match timeline payload
      - `manifest.json` to map canonical fixture names to files
  - Added centralized fixture loader:
    - `services/api/tests/fixtures/riot_payloads.py`
    - Shared helpers: `fixture_meta()`, `load_account_info()`, `load_summoner_info()`,
      `load_match_ids()`, `load_match_detail()`, `load_match_timeline()`
  - Added fixture capture Make target:
    - `make capture-riot-fixtures`
  - Refactored Riot-related tests to use centralized real payload fixtures instead of
    handcrafted inline payload dicts:
    - `services/api/tests/test_riot_api_client_match_fetch.py`
    - `services/api/tests/test_riot_api_client_retry.py`
    - `services/api/tests/test_riot_sync_backfill.py`
    - `services/api/tests/test_riot_account_upsert.py`
  - Added router-level coverage for captured payload chain:
    - `services/api/tests/test_search_router_riot_fixtures.py`
    - Verifies page-1 `/search/{riot_id}/matches` call path invokes
      account -> summoner -> match IDs with `count=limit`, then upsert/backfill/enqueue.
  - Added fixture contract test:
    - `services/api/tests/test_riot_payload_fixtures_contract.py`
    - Validates required keys and cross-fixture consistency (`puuid`, `primary_match_id`).
- **Why**: removes drift between tests and Riot payload reality, and centralizes fixture
  maintenance so all backend tests share one source of truth.
- **Current phase/status**: REFACTORING — backend hardening follow-ups (fixture realism + test
  maintainability).
- **Blockers / open questions**:
  - `make lint` still reports existing repo-wide Ruff violations unrelated to this change.
  - Frontend lint retains 1 pre-existing warning in `league-web/src/components/Auth/AuthForm.tsx`.
- **Verification**:
  - Targeted pytest for updated files: pass (12/12).
  - `make test`: pass (23/23).
  - Ruff on edited files: pass.
  - `npm --prefix league-web run lint`: pass with 1 pre-existing warning.

---

## Recent Changes (2026-03-06, session 11)

### Fixture review follow-ups — trim, dedup, defer

- **Timeline fixture trimmed**: `match_timeline.na1_5506397559.json` cut from 64K lines to 9K lines.
  Kept 16 frames (covers 0–15 min laning phase). Stripped `events` arrays (tests only use
  `participantFrames`). Capture script now accepts `--timeline-frames N` (default 16).
- **Shared test helpers extracted**: new `tests/fixtures/fake_riot_helpers.py` with `FakeRateLimiter`,
  `ScriptedClient`, `ok_response`, `error_response`, `noop_metric`. Eliminates duplication across
  `test_riot_api_client_match_fetch.py` and `test_riot_api_client_retry.py`.
- **Import-time I/O deferred**: `test_riot_api_client_match_fetch.py` no longer loads fixture JSON
  at module scope. Data is now loaded inside a `@pytest.fixture` so it's only read when tests in
  that file actually run.

**Verification**: 23/23 tests pass. Ruff clean on changed files.

---

## Recent Changes (2026-03-06, session 12)

### Code review fixes — backfill atomicity, job cleanup, polling, tab state

- **Atomic backfill writes** (`riot_sync.py`):
  - `_backfill_single_match` now extracts `timestamp` into a local variable before assigning either
    `game_info` or `game_start_timestamp`. Prevents partial state where `game_info` is set but
    `game_start_timestamp` remains NULL on exception — the exact ordering bug this branch fixes.
  - Same pattern applied to `fetch_match_details_job` in `match_ingestion.py`.

- **Fallback RiotApiClient cleanup** (`match_ingestion.py`):
  - Three job functions (`fetch_riot_account_matches_job`, `fetch_timeline_cache_job`,
    `fetch_match_details_job`) used `ctx.get("riot_client") or RiotApiClient()` but never closed the
    fallback client. Added `try/finally` blocks that call `await client.close()` only when the
    fallback was used (not the shared context client). Prevents HTTP connection leaks.

- **Resilient timeline enqueue** (`enqueue_match_timelines.py`):
  - `enqueue_missing_timeline_jobs` runs in FastAPI `BackgroundTasks` where exceptions are silently
    swallowed. Added try/except around `get_arq_pool()` (returns 0 if pool unavailable) and per-batch
    `enqueue_job` calls (logs warning, continues to next batch instead of aborting).

- **Durable poll counter** (`home/page.tsx`, `riot-account/[riotId]/page.tsx`):
  - Polling `MAX_POLLS` safeguard was ineffective — `pollCount` was a local variable inside the
    polling `useEffect`, resetting to 0 every time the effect re-ran (triggered by
    `missingDetailCount` changes). Replaced with `useRef(0)` that persists across effect re-runs.
    Separate effect resets the ref on `refreshIndex`/`page` change.
  - Also added missing `refreshIndex` to riot-account polling effect deps for consistency with home.

- **Stale tab fallback** (`MatchesTable.tsx`):
  - After page navigation or refresh, `activeTab` could reference a queue group with no matches in
    the new data, showing an empty view. React 19 strict lint rules prevent `useEffect`/ref-based
    reset during render. Solution: `filteredMatches` now falls back to showing all matches when the
    active tab yields zero results.

**Verification**:

- `make test` — pass (23/23).
- `make lint` — pass.
- `npm --prefix league-web run lint` — pass with 1 pre-existing warning.

---

## Recent Changes (2026-03-06, session 13)

### Backend hardening follow-ups — items 6–13 from code review

**Branch:** `backend-tests-refactor`
**Status:** STABLE — all 8 follow-up items resolved; 28/28 tests pass, lint clean.

#### #6 — Simplified timeline ARQ job IDs (`enqueue_match_timelines.py`)

- Removed `hashlib` import and SHA-1-based `_job_id` construction.
- Replaced with the same `batch[0]..batch[-1]:len` range pattern used in `enqueue_match_details.py`.
- Less complexity, same ARQ dedup guarantees.

#### #7 — Double Redis cache check (no change)

- Reviewed both layers: MGET pre-filter at enqueue time (avoids creating unnecessary jobs) and GET per-job at execution time (race-condition dedup). Both serve distinct purposes; intentionally kept as-is.

#### #8 — 429 rate-limit retry tests (`test_riot_api_client_retry.py`, `fake_riot_helpers.py`)

- Added optional `headers` param to `error_response()` helper.
- `test_riot_client_retries_429_then_succeeds`: verifies Retry-After sleep duration, metric tagged `"429"`, and `riot_request_429` log event.
- `test_riot_client_429_max_retries_raises`: verifies repeated 429s exhaust `MAX_RETRIES` and raise `RiotRequestError(status=429)`.

#### #9 — Fixture contract tests for participants and frames (`test_riot_payload_fixtures_contract.py`)

- `test_riot_fixture_contract_match_detail_participants`: asserts exactly 10 participants with required keys (`participantId`, `puuid`, `championName`, `teamId`, `individualPosition`, `kills`, `deaths`, `assists`, `win`).
- `test_riot_fixture_contract_timeline_frames`: asserts `frames` non-empty, `frameInterval` present, every frame has `participantFrames` with 10 entries.

#### #10 — Backfill fake session respects WHERE clause (`test_riot_sync_backfill.py`)

- `_FakeSession.execute()` now filters `[m for m in self._matches if not m.game_info]`, mirroring the real `game_info IS NULL` query.
- Added `test_backfill_by_game_ids_skips_already_backfilled` with 2 pre-filled + 3 missing matches.

#### #11 — Fixture loaders return deepcopy (`riot_payloads.py`)

- Replaced per-call disk reads with `@functools.cache`-backed `_read_json_cached(path)`.
- All mutable loaders (`load_account_info`, `load_summoner_info`, `load_match_detail`, `load_match_timeline`) now return `deepcopy(...)` to prevent cross-test mutation.

#### #12 — Downgrade noisy `logger.exception` for expected Riot errors (`riot_sync.py`)

- Added `RiotRequestError` to imports.
- Split bare `except Exception` in `_backfill_single_match` and `fetch_timeline_stats` into:
  - `except RiotRequestError` → `logger.warning(...)` with `status` and `message` (no traceback for expected 404s etc.)
  - `except Exception` → `logger.exception(...)` (traceback preserved for unexpected failures)

#### #13 — Prevent orphan Match records (`riot_sync.py`)

- `fetch_match_detail` previously created `Match(game_id=...)` when no DB record existed, leaving an unlinked row with no `RiotAccountMatch`.
- Fix: when no existing Match is found, return the fetched payload directly without touching the DB. Log event `riot_sync_fetch_match_detail_no_db_record` emitted instead.

**Verification**:

- `make test` — pass (28/28; was 23/23 before, +5 new tests).
- `make lint` — pass (ruff clean).
- `npm --prefix league-web run lint` — pass (1 pre-existing AuthForm warning unchanged).

---

## Recent Changes (2026-03-06, session 14)

### Top-3 high-impact fixes from code review

**Branch:** `backend-tests-refactor`
**Status:** STABLE — 41/41 tests pass, lint clean.

#### #1 — `getParticipantForUser` no longer returns wrong participant (`match-utils.ts`)

- **Before**: when neither puuid nor summoner name matched, fallback returned `participants[0]` — silently showing the wrong player's stats in the auth-based view.
- **After**: returns `null`, letting the UI handle missing state explicitly.
- **File**: `league-web/src/lib/match-utils.ts`

#### #2 — Search routes convert `RiotRequestError` to proper HTTP status (`search.py`)

- **Before**: `except RiotRequestError: raise` re-raised the raw error and relied on the global exception handler; also used `logger.exception` (full traceback) for expected Riot errors.
- **After**: catches `RiotRequestError`, logs at `warning` level with structured fields, and raises `HTTPException` using `map_riot_status()` (404→404, 429→429, 5xx→502, etc.).
- Renamed `_map_riot_status` → `map_riot_status` in `exceptions.py` (now a public API).
- **Files**: `services/api/app/api/routers/search.py`, `services/api/app/core/exceptions.py`

#### #3a — `fetch_timeline_stats` test coverage (`test_timeline_stats.py`)

- **New file**: `services/api/tests/test_timeline_stats.py` — 6 tests:
  - Happy-path CS/gold diffs using real fixture (MissFortune pid=9 vs Twitch pid=4 at BOTTOM).
  - Cache hit path (Redis pre-populated, Riot API never called).
  - Empty frames (no match in DB) → returns None.
  - No lane opponent (unique positions) → returns None.
  - `RiotRequestError` during fetch → returns None.
  - Short game (11 frames) → produces `cs_diff_at_10` but not `cs_diff_at_15`.

#### #3b — Search page-2+ and RiotRequestError mapping tests (`test_search_router_page2.py`)

- **New file**: `services/api/tests/test_search_router_page2.py` — 7 tests:
  - Page 2 skips Riot API, resolves account from DB, no background tasks.
  - Page 3 returns correct pagination meta (page/limit/total/last_page).
  - Page 2 with missing DB account → 404.
  - `RiotRequestError(status=404)` → HTTP 404.
  - `RiotRequestError(status=429)` → HTTP 429.
  - `RiotRequestError(status=500)` → HTTP 502.
  - `RiotRequestError(status=401)` on `/account` → HTTP 401.

#### Bonus — Fixed `"message"` LogRecord collision bug

- `logger.warning(..., extra={"message": exc.message})` collided with Python's reserved `LogRecord.message` attribute, raising `KeyError` at runtime.
- Renamed to `"error_message"` in `search.py` and `riot_sync.py`.

**Verification**:

- `pytest services/api/` — pass (41/41; was 28/28, +13 new tests).
- `ruff check` — pass on all changed files.
- `npm --prefix league-web run lint` — pass (1 pre-existing AuthForm warning unchanged).

---

## Recent Changes (2026-03-06, session 15)

### Tier 1 — Production reliability fixes

**Branch:** `backend-tests-refactor`
**Status:** STABLE — 41/41 tests pass, lint clean.

#### #1 — Race condition eliminated (`match_sync.py`)

- **Before**: `upsert_matches_for_riot_account` used select-then-insert for both `Match` and `RiotAccountMatch`. Concurrent requests for the same summoner could hit `IntegrityError`.
- **After**: Uses `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL dialect) for both tables. Match rows inserted atomically by `game_id` unique constraint; link rows by `uq_riot_account_match` constraint. No more select-then-insert loop.

#### #2 — Race condition eliminated (`riot_account_upsert.py`)

- **Before**: `ensure_user_riot_account_link` used select-then-insert. `upsert_user_and_riot_account` created `User` via `get_user_by_email` + `session.add` — race-prone.
- **After**: `ensure_user_riot_account_link` uses `INSERT ... ON CONFLICT DO NOTHING` on `uq_user_riot_account` constraint, then selects to return the record. New `_upsert_user_by_email` uses `INSERT ... ON CONFLICT DO NOTHING` on `email` unique index. `upsert_riot_account` retains its existing savepoint+retry pattern (already safe).

#### #3 — Redis resilience in timeline enqueue (`enqueue_match_timelines.py`)

- **Before**: `get_redis()` and `redis.mget()` were outside the try/except. If Redis was down, the background task crashed silently with no log.
- **After**: Both calls wrapped in try/except. On Redis failure, logs `enqueue_missing_timelines_redis_unavailable` and falls back to enqueueing all match IDs (safe — the per-job Redis check is the second dedup layer).

#### #4 — Mid-batch commit safety in `fetch_match_details_job` (`match_ingestion.py`)

- **Before**: Single `session.commit()` after the loop. If match 6/10 raised an unexpected error, matches 1–5 were never committed.
- **After**: Unexpected exceptions trigger an immediate commit of progress so far, then continue. `finally` block catches any remaining dirty state. `RiotRequestError` still skips commit (expected transient failure). Loop-end commit resets the `pending_commit` flag to prevent double-commit in `finally`.

**Verification**:

- `make test` — pass (41/41).
- `ruff check` — pass on all changed files.

---

## Recent Changes (2026-03-06, session 16)

### Frontend refactor — `useMatchList` custom hook extraction

- **New file**: `league-web/src/lib/hooks/useMatchList.ts` (~100 lines)
  - Encapsulates: match fetching, `matchDetails` seeding from `game_info`, polling for missing details, pagination state, refresh logic.
  - Parameterized via `matchesUrl(page)` callback, `errorScope`, `enabled` flag, optional `cacheOptions`, `onFetchError` interceptor, and `resetKey`.
  - Config values (`cacheOptions`, `logTag`, `onFetchError`) stored in refs to avoid triggering re-fetches.
- **Refactored**: `league-web/src/app/home/page.tsx` — 247 → ~135 lines. Removed ~100 lines of duplicated state/effects. Rank fetch separated into its own effect (was previously `Promise.all`'d with matches).
- **Refactored**: `league-web/src/app/riot-account/[riotId]/page.tsx` — 313 → ~195 lines. Removed ~130 lines of duplicated state/effects. Account fetch, decode error handling, `pageError` merge, and session check remain page-specific. Riot 404 error interception handled via `onFetchError` callback.
- **No behavior changes** — identical fetch URLs, cache policies, polling logic, and error handling as before.
- **Verification**: `npm run lint` — pass (1 pre-existing AuthForm warning unchanged). `npm run build` — clean.

---

## Recent Changes (2026-03-06, session 17)

### Tier 2 + Tier 3 correctness and perf fixes

**Branch:** `backend-tests-refactor`
**Status:** STABLE — 42/42 tests pass, lint clean.

#### Double account resolution eliminated (`riot_sync.py`, `matches.py`)

- `fetch_match_list_for_riot_account` now returns `tuple[list[str], RiotAccount] | None`.
- `list_riot_account_matches` router unpacks the tuple on page 1 — reuses the already-resolved account instead of calling `resolve_riot_account_identifier` a second time.
- Page 2+ still calls `resolve_riot_account_identifier` once (single DB round-trip, unchanged).

#### `React.memo` restored on `MatchRow` (`MatchesTable.tsx`)

- `rankByPuuid` (full map) previously passed to all 20 rows; got a new object reference on every rank fetch, defeating memo on unselected rows.
- Fix: pass `rankByPuuid={isExpanded ? rankByPuuid : undefined}` — only the one expanded row receives the map.
- `championHistory` similarly changed to use a module-level `EMPTY_HISTORY` constant for non-expanded rows, preventing new-array references on every render.

#### `matchSummaryStats` no longer recomputes on every 3-second polling tick (`MatchesTable.tsx`)

- Old deps: `[filteredMatches, matchDetails, getParticipantForMatch]` — `matchDetails` gets a new reference every polling tick, triggering the 80-line computation.
- Fix: added `loadedDetailCount` (derived stable number — count of matches with non-null details) as the gate dep. `matchDetails` is accessed via `matchDetailsRef.current` so the memo only re-runs when the count grows (genuine new detail arrived), not on reference-only changes.
- Inline participant lookup (`getParticipantByPuuid` / `getParticipantForUser`) replaces the `getParticipantForMatch` callback dep, removing one layer of instability.

#### `_FakeSession` now enforces `game_id IN (...)` filter (`test_riot_sync_backfill.py`)

- `_FakeSession.__init__` accepts `game_ids: list[str] | None`; `execute` filters by game_id set in addition to `game_info IS NULL`.
- All three existing tests updated to pass `game_ids=game_ids`.
- New test `test_backfill_by_game_ids_ignores_matches_outside_requested_set`: creates 8 matches in session, requests only 5, verifies the 3 extras are never backfilled.

#### `fixture_meta()` returns deepcopy (`riot_payloads.py`)

- Previously returned the raw cached dict from `_read_json_cached`; one mutation would corrupt all downstream test calls.
- One-line fix: return `deepcopy(_read_json_cached(MANIFEST_PATH))`.
- Removed now-unused `lru_cache` import (caching no longer needed since caller always gets a fresh copy).

**Verification**:

- `make test` — pass (42/42; was 41/41, +1 new test).
- `make lint` — pass.
- `npm --prefix league-web run lint` — pass (1 pre-existing AuthForm warning unchanged).

---

## Recent Changes (2026-03-06, session 18)

### Three small correctness / hygiene fixes

**Branch:** `backend-tests-refactor`
**Status:** STABLE — 42/42 tests pass, lint clean.

#### Inlined `_commit_backfilled` (`riot_sync.py`)

- Removed the 3-line helper. Both call sites (`backfill_match_details_inline`, `backfill_match_details_by_game_ids`) now do `if fetched: await session.commit()` directly.
- **Why**: only 2 call sites; indirection wasn't worth a named function.

#### `participant_id` bounds validation (`matches.py`)

- Added `ge=1, le=10` to the `Query()` on the `/matches/{match_id}/timeline-stats` endpoint.
- **Why**: out-of-range IDs (0, 11, etc.) previously fell through to `fetch_timeline_stats`, which returned `None` → misleading 404. Now returns a proper 422 validation error.

#### Fixed `ordinalSuffix` for n > 13 (`match-utils.ts`)

- Before: `ordinalSuffix(21)` → `"21th"`.
- After: uses `n % 100` to handle teens (11th, 12th, 13th) and `n % 10` for the rest (21st, 22nd, 23rd, etc.).
- **Why**: latent bug — only called with 1–10 today but would surface with any future use beyond 13.

**Verification**:

- `make test` — pass (42/42).
- `ruff check` — pass on changed files.
- `npm --prefix league-web run lint` — pass (1 pre-existing AuthForm warning unchanged).

---

## Recent Changes (2026-03-06, session 19)

### Backfill extraction script for existing matches

- **New file**: `scripts/backfill_extraction.py` — standalone script that queries all matches with `game_info IS NOT NULL` but no `match_state_vector` rows, then enqueues `extract_match_timeline_job` for each via ARQ.
- **Why**: `extract_match_timeline_job` was only triggered by `fetch_match_details_job` (new match ingestion). Existing matches that already had `game_info` never got state vectors extracted. This one-off script backfills the gap.
- **Usage**: `make backfill-extraction` (or `python scripts/backfill_extraction.py --dry-run` to preview). Requires the ARQ worker to be running.
- **Make target**: `make backfill-extraction` added to Makefile.
- **No router changes** — the inline backfill paths (`backfill_match_details_by_game_ids`, `backfill_match_details_inline`) remain unchanged; they serve a different purpose (populating `game_info`, not extraction).

---

## Recent Changes (2026-03-06, session 20)

### Worker structured logging + verbose make targets

- **Fix**: `setup_logging()` was not called in the ARQ worker process (`on_startup`), so worker logs used Python's default handler instead of the app's `DevFormatter` (colored, truncated). Now the worker calls `setup_logging()` on startup, making extraction job logs visible with the same formatting as the API.
- **New make targets**: `make worker-dev-verbose` (runs worker with `LOG_LEVEL=DEBUG`), `make backfill-extraction-dry` (dry-run preview of backfill).
- **Files changed**: `services/api/app/services/background_jobs.py`, `Makefile`.

---

## Recent Changes (2026-03-09, session 22)

### Development environment — `make install` virtualenv bootstrap

- **Change**: Updated `Makefile` `install` target to create a local `.venv` (if missing) and run all installs via `./.venv/bin/python -m pip` instead of a bare `pip`.
- **Why**: Some environments no longer expose `pip` on `PATH`, causing `make install` to fail with `pip: No such file or directory`. Using the project-local virtualenv Python makes the install command consistent and self-contained.
- **Status**: STABLE — no runtime behavior changes; only the developer setup flow is affected.

## Recent Changes (2026-03-06, session 21)

### "See More" load-more button for match history (`frontend-graceful-degradation`)

**Why**: The existing Previous/Next pagination forces users to navigate away from
their current matches to see older ones. A load-more pattern lets users
accumulate matches inline without losing context.

**What changed:**

- **`useMatchList.ts`** — three new state variables (`isLoadingMore`,
  `nextLoadMorePage`, `yearBoundaryReached`) + two new return fields:
  - `canLoadMore: boolean` — `true` when `paginationMeta.page === paginationMeta.last_page`
    and no stop condition is active. Checked against `last_page` (not
    `nextLoadMorePage`) so it only appears on the final page, not all pages.
  - `isLoadingMore: boolean` — `true` while a load-more request is in flight.
  - `loadMoreMatches(): Promise<void>` — fetches `nextLoadMorePage`, filters
    out matches before Jan 1 of current year, appends to existing `matches`
    state. Sets `yearBoundaryReached = true` on empty page or year-boundary hit.
    Resets on every main fetch (page nav / refresh).

- **`MatchesTable.tsx`** — new optional props `canLoadMore`, `isLoadingMore`,
  `onLoadMore`; renders a centred "See more" / "Loading..." button between
  the table rows and the `<Pagination>` control.

- **`MatchesTable.module.css`** — `.loadMore`, `.loadMoreBtn`, `:disabled` rules.

- **`home/page.tsx`** + **`riot-account/[riotId]/page.tsx`** — destructure and
  pass all three new props to `MatchesTable`.

**Bug fixes applied mid-session:**

- Button was visible on ALL pages (not just the last) — root cause:
  `nextLoadMorePage <= last_page` is `true` whenever `page < last_page`.
  Fixed by switching to `paginationMeta.page === paginationMeta.last_page`.
- Button was invisible for single-page summoners (page 1 of 1) — same root
  cause; same fix resolves it (page 1 of 1 satisfies `page === last_page`).
- Button didn't disappear after exhausting data — added
  `newMatches.length === 0` check that sets `yearBoundaryReached = true`.

**Verification:** `npm run lint` — pass (1 pre-existing warning). `npm run build` — clean.

---

## Next Recommended Steps

### Documentation Guardrail (Drift Prevention)

- Treat `docs/RIOT_API_PARTICIPANT_FIELDS.md` as the source of truth for Riot
  participant field coverage, priority, and DDragon mapping references.
- Keep these files synchronized whenever participant data usage changes:
  - `docs/RIOT_API_PARTICIPANT_FIELDS.md`
  - `league-web/src/lib/types/match.ts`
  - `league-web/src/components/MatchCard/MatchCard.tsx`
  - `league-web/src/lib/constants/ddragon.ts`
  - `docs/app_state.md`

1. **LLM Pipeline Step 6 — Compare**: Build comparison logic (rank summoner choices vs optimal alternatives by ΔW).
2. **LLM Pipeline Step 7 — LLM Prompt**: Build gap analysis payload and submit to Claude for recommendations. Populate `llm_analysis` table.
3. ~~**Wire `extract_match_timeline_job` into existing match ingestion flow**~~ — **DONE** (enqueued after `fetch_match_details_job`).
4. ~~**Fix race condition**~~ — **DONE** (session 15).
5. **Live Game integration** — requires polling architecture + `LiveGameCard` component.
6. **Consider server-side queue filtering** — current tab filtering is client-side.
7. **Implement vector embeddings** — `pgvector` is enabled; wire up `sentence-transformers` worker job.
