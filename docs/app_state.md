# App State

**Last Updated:** 2026-07-15
**Branch:** `chat`
**Status:** STABLE — LLM/RAG pipeline is fully user-facing (AI Coach button **with champion picker** + AnalysisPanel, streaming tool-calling Coach Chat drawer, `RUN_EVALS=1`-gated eval harness), five-axis-reviewed, simplify+ship-passed (**GO**), and the **corpus is seeded (36 embedded rows: 5 accounts × 7 champions + 1 Jhin)**. 224 backend tests + 32 Playwright E2E green, lint clean. **PR #47 open and current** — https://github.com/JairoE/league-match-analyzer/pull/47.

> This file holds current state only — architecture, blockers, next steps. Session-by-session
> history moved to [`docs/app_state_archive.md`](app_state_archive.md); `git log` / merged PRs
> are the source of truth for "what happened when." When updating this file (e.g. via
> `/UPDATE_APP_STATE`), overwrite the relevant section in place rather than prepending a new
> dated entry — append a one-paragraph summary to the archive file instead if the history is
> worth preserving.

## Current Phase

**Champion picker + retry fix shipped; corpus seeded (`chat`, 2026-07-13).** The AI Coach button pairs with a champion `<select>` (all champions from loaded match history, most-played first), so any champion with data can be analyzed. `useAiCoach` hook centralizes the picker/analysis wiring shared by both match pages. Recent ARQ fix: `llm_analysis_job` now registers with `keep_result=10` (was 1h) so a transient LLM failure doesn't stick a day-bucketed job id and silently swallow retries — **requires a worker restart to take effect on any environment still running the old registration**.

### RAG architecture (complete)

- **Step 6.5**: embed query → cosine KNN in pgvector → inject top-3 as `## Reference Examples` in user prompt
- **Post-persist**: generate + store embedding on new `LLMAnalysis` rows so corpus grows automatically
- **Cold start**: empty corpus returns `[]`, pipeline never aborts; RAG activates meaningfully at ~5+ rows per champion, quality improves at ~50+ per champion/rank bucket
- **Seeding**: `make seed-rag-corpus ARGS='--from-file seeding_list.txt'` or `--entry "name#NA1:157"`
- **Corpus now**: 36 embedded rows — 5 accounts × 7 champions (Brand, Blitzcrank, Zac, Teemo, Alistar, Lux, Vel'Koz) + 1 Jhin

## Blockers

- None blocking. Lint clean; 224 backend tests pass (2 skipped — real-API integration only); 32/32 Playwright E2E (one pre-existing flaky live-game test, passes in isolation).
- Not yet run (needs live services): manual end-to-end smoke test of AI Coach + chat against a real OpenAI key and running worker; SSE streaming smoke test on Railway.
- Operational note: Railway dashboard must run `release.sh` as the API service's pre-deploy/release command.
- Operational note: any long-running ARQ worker needs a restart to pick up `keep_result=10` (see Current Phase).

### Security posture (accepted for now, reviewed 2026-07-12)

The `POST /riot-accounts/{id}/analysis` and `POST /riot-accounts/{id}/chat/stream`
endpoints spend OpenAI tokens with **no authentication or per-IP rate limiting**, consistent
with every other route in this portfolio app. Guards in place: chat caps concurrency at 4
streams (`MAX_CONCURRENT_CHAT_STREAMS`, best-effort 429 `chat_busy`); analysis dedupes per
`(account, champion, day)` via the deterministic ARQ job id; per-turn token caps
(≤3 tool rounds, 12-message window, `max_tokens=700`, gpt-4o-mini). Accepted as-is —
iterating champions/accounts remains an unbounded token-spend path. If this ever goes properly
public, add per-IP rate limiting and a spend guard, and make the chat semaphore acquire
non-blocking so the 429 fails fast under a check-then-acquire race.

## Next Steps

1. **Merge PR `chat` → `main`** (#47).
2. **Manual smoke test with real key**: `make db-up && make api-dev && make worker-dev` + `npm run dev`; click AI Coach on a scored account, then chat ("How is my dragon control?") and watch tool activity + streaming.
3. **Run `make evals`** — corpus has 36 rows (>10 minimum) — records precision@k / MRR / judge scores in `evals/results/`.
4. Decide whether to reconcile with the parallel `codex/durable-ai-coach` branch (its picker sources from account eligibility instead of loaded match history).
5. Consider server-side queue filtering — tab filtering in `MatchesTable` is still client-side.
6. (Optional) Delete superseded docs: `docs/rag-design.md`, `docs/LLM_RAG_COMPLIMENTARY.md` — both replaced by `docs/LLM_PIPELINE_STATUS.md`.
7. (Future) **Next.js server data layer** — Server Components + server `fetch` for match list shells (documented in `TECHNICAL_ARCHITECTURE_AND_PATTERNS.md` §3.7).

### Documentation guardrail (drift prevention)

Treat `docs/RIOT_API_PARTICIPANT_FIELDS.md` as the source of truth for Riot participant field
coverage. Keep these in sync whenever participant data usage changes: that doc,
`league-web/src/lib/types/match.ts`, `league-web/src/components/MatchCard/MatchCard.tsx`,
`league-web/src/lib/constants/ddragon.ts`, and this file.

---

## What's Built

### Backend (FastAPI + ARQ)

- **Search flow**: `GET /search/{riot_id}/matches` — account resolved from DB first; Riot called for account only on first sync (account not in DB). Match IDs fetched from Riot on first sync, `?refresh=true` (page 1), or see more (`after>0`). Supports `?page=N&limit=N&refresh=true`.
- **Auth match flow**: `GET /riot-accounts/{id}/matches` — paginated match list from DB; Riot match IDs only when `?refresh=true` (page 1) or see more (`after>0`).
- **Pagination schema**: `PaginatedMatchList` wraps `data` + `PaginationMeta` (page, limit, total, last_page, stale, stale_reason). On 429 during page-1 sync, endpoints fall back to DB and return cached data with `stale=true`.
- **Auth flow**: `POST /users/sign_in`, `POST /users/sign_up` — optional user authentication.
- **Riot API Client**: Redis-backed sliding-window rate limiter with dynamic header parsing and exponential backoff.
- **Background jobs**: `fetch_match_details_job` (batch → auto-enqueues `extract_match_timeline_job`), `extract_match_timeline_job` (state vector + action extraction), `score_actions_job` (ΔW scoring), `llm_analysis_job` (steps 5→8 orchestration, `keep_result=10`), `fetch_timeline_cache_job` (timeline warmup), `sync_all_riot_accounts_matches` (cron every 6h).
- **Data model**: `RiotAccount`, `Match` (with `game_info` JSONB), `RiotAccountMatch` join table. `pgvector` extension enabled.
- **Observability**: Structured JSON logging, `increment_metric_safe` metric helper.
- **AI Coach / RAG pipeline**: 8-step pipeline (ingest → extract → score → aggregate → compare → prompt → LLM call → persist), with Step 6.5 RAG few-shot retrieval. See `docs/LLM_PIPELINE_STATUS.md` and `docs/LLM_DATA_PIPELINE.md`.
- **Coach Chat**: stateless SSE streaming, tool-calling loop (`app/services/chat/`) with 4 tools (`get_player_profile`, `get_latest_analysis`, `get_action_stats`, `list_recent_matches`), all strictly account-scoped.
- **Eval harness**: `evals/` — retrieval + LLM-as-judge metrics, gated behind `RUN_EVALS=1` (`make evals`).

### Frontend (Next.js 16)

- **Pages**: `/` (search + optional auth), `/home` (match results dashboard), `/riot-account/[riotId]` (search results view).
- **API client**: `src/lib/api.ts` — typed `apiGet<T>` / `apiPost<T>` wrappers.
- **Client cache**: `src/lib/cache.ts` — in-memory LRU-like cache with TTL.
- **Session management**: `sessionStorage`-backed `useSession` hook.
- **Match history UX**:
  - `MatchesTable` replaces card-grid history on `/home` and `/riot-account/[riotId]`.
  - Table uses sticky headers, queue-group tabs, row-level selection, and skeleton states.
  - Right-side detail overlay (`MatchDetailPanel`) renders `MatchCard` in `expanded` mode.
  - Queue type modeling is centralized in `src/lib/types/queue.ts` with coarse tab grouping (`GameQueueGroup`) and granular row labels (`GameQueueMode`).
- **Match card**: `MatchCard` is decomposed into `ItemSlot`, `Teams`, `ChampionKdaChart`, `match-card.utils.ts`, and `types.ts` within `MatchCard/`. The main file is a ~200-line orchestrator, `memo`-wrapped at export.
- **Pagination**: Reusable `Pagination` component with Previous/Next buttons, "Page X of Y", total count. Hidden when single page. Wired into `MatchesTable` via optional `paginationMeta`/`onPageChange` props. "See more" load-more button appended on the last page for inline accumulation without losing context.
- **Rank in header**: `useRank(riotAccountId, { refreshIndex })` fetches `GET /riot-accounts/{id}/fetch_rank` and returns `{ rank, rankSubtitle }`. Used on `/home` and `/riot-account/[riotId]`.
- **Live game**: `useLiveGameWhenReady` gates a single-attempt SSE connection on match list readiness; `LiveGameSlot` renders live/not_in_game/error/connecting states with a retry action.
- **AI Coach**: `useAiCoach` hook (shared by both match pages) wraps champion picker state, most-played fallback, panel-open invariant, and the analyze click handler; resets picked champion on account switch. `useAnalysis` polls `POST/GET /riot-accounts/{id}/analysis` with cache-busting GETs.
- **Coach Chat**: `useChat` + hand-rolled SSE parser (`src/lib/sse.ts`) drive a streaming transcript in `ChatPanel`/`ChatButton`; AbortController on unmount/account switch, ≤20-message history, strips empty assistant turns before resend.
- **Error handling** (`src/lib/errors/`):
  - `ApiError` class with `status`, `detail`, `riotStatus` fields.
  - `buildApiErrorFromResponse` / `toApiError` for normalising HTTP and plain errors.
  - `formatApiError` — translates backend codes via `DETAIL_MESSAGES` lookup table; handles `riot_api_failed` with `riotStatus` branching (404/429/other); HTTP status fallbacks for unknown codes; no misleading "Network error" prefix on non-HTTP errors.
  - `useAppError(scope)` React hook — `{ errorMessage, reportError, clearError }`.
  - Call sites use `reportError(err)` for general errors; intercept before `reportError` when a page-level context string (e.g. summoner name) is needed.
- **Perf**: code-split `ChampionKdaChart` and `LiveGameSlot` via `next/dynamic`; `useTransition` on table pagination/tab switches; React Compiler annotation mode on `MatchesTable` and both page components; stable `matchDetails` reference in `useMatchList` to avoid re-renders on polling ticks.

### Infrastructure

- Docker Compose: `api`, `worker`, `db`, `redis`.
- Railway deployment via `railway.json` + nixpacks. API starts Uvicorn immediately on boot; `release.sh` runs `alembic upgrade head` as the pre-deploy/release step (must be configured in the Railway dashboard).
- Alembic async migrations.

---

## Request Flow Summary

```
User → Search (Riot ID) → GET /search/{riot_id}/matches?page=1
  → find_or_create_riot_account (DB upsert)
  → Rate limit check (Redis)
  → Fetch match IDs (Riot API)
  → Upsert match IDs (DB, ON CONFLICT DO NOTHING)
  → Pre-query backfill of missing game_info (Riot API, max_fetch=limit)
  → Return paginated match list + meta

User → Page 2+ → GET /search/{riot_id}/matches?page=N
  → Resolve riot account from DB (no Riot API)
  → Return paginated match list + meta

Background (async, route-level BackgroundTasks → ARQ):
  → enqueue_missing_timeline_jobs → fetch_timeline_cache_job → Redis cache `timeline:{match_id}`
  → fetch_match_details_job → extract_match_timeline_job → score_actions_job (ΔW scoring)

AI Coach:
  → POST /riot-accounts/{id}/analysis → llm_analysis_job (aggregate → compare → RAG retrieve → prompt → LLM → persist)
  → Frontend polls GET .../analysis every 2s until a row exists (or already_exists short-circuits)

Coach Chat:
  → POST /riot-accounts/{id}/chat/stream → SSE (token/tool_call/tool_result/done/error)
  → Tool loop: ≤3 rounds, ≤2 tool executions/round, account-scoped tools only

Optional:
  → Sign In/Up → POST /users/sign_in → Validate (DB) → Save session
```

---

## Open Tickets

None open. The last tracked ticket (race condition in `_get_or_create_match` / `upsert_user_from_riot`) was resolved via `INSERT ... ON CONFLICT DO NOTHING` — see [`docs/app_state_archive.md`](app_state_archive.md) session 15 (2026-03-06) for detail.
