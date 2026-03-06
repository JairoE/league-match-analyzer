# App State

**Last Updated:** 2026-03-06
**Branch:** `backend-tests-refactor` (merged with `llm-phase-0`)
**Status:** STABLE — 42/42 tests pass, lint clean, race-condition blocker resolved; LLM pipeline Steps 1–2 implemented

## What's Built

### Backend (FastAPI + ARQ)

- **Search flow**: `GET /search/{riot_id}/matches` — find-or-create account, upsert match IDs, backfill basic details inline, enqueue timeline prefetch in background. Supports `?page=N&limit=N` pagination.
- **Auth match flow**: `GET /riot-accounts/{id}/matches` — paginated match list with Riot API sync on page 1 only.
- **Pagination schema**: `PaginatedMatchList` wraps `data` + `PaginationMeta` (page, limit, total, last_page).
- **Auth flow**: `POST /users/sign_in`, `POST /users/sign_up` — optional user authentication.
- **Riot API Client**: Redis-backed sliding-window rate limiter with dynamic header parsing and exponential backoff.
- **Background jobs**: `fetch_match_details_job` (batch), `fetch_timeline_cache_job` (timeline warmup), `sync_all_riot_accounts_matches` (cron every 6h).
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

| Ticket                                                                                                                                        | File                                                             | Status       |
| --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------ |
| Race condition in `_get_or_create_match` and `upsert_user_from_riot` — non-atomic check-then-insert causes `IntegrityError` under concurrency | `services/api/app/services/match_sync.py`, `riot_account_upsert.py` | **RESOLVED** |

**Resolved** (session 15): All select-then-insert patterns replaced with `INSERT ... ON CONFLICT DO NOTHING` for `Match`, `RiotAccountMatch`, `User`, and `UserRiotAccount`.

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
  - `enqueue_match_timelines.py` *(new)* — `enqueue_missing_timeline_jobs()` enqueues `fetch_timeline_cache_job` per batch with deterministic `_job_id`.
  - `match_timeline_enqueue.py` *(new)* — fire-and-forget wrapper `enqueue_timelines_background()`.
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
- **Why**: allows lint to become a reliable blocking signal for *new* issues while existing noise is burned down incrementally.

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

## Next Recommended Steps

### Documentation Guardrail (Drift Prevention)

- Treat `docs/RIOT_API_PARTICIPANT_FIELDS.md` as the source of truth for Riot
  participant field coverage, priority, and DDragon mapping references.
- Keep these files synchronized whenever participant data usage changes:
  - `docs/RIOT_API_PARTICIPANT_FIELDS.md`
  - `league-web/src/lib/types/match.ts`
  - `league-web/src/components/MatchCard/MatchCard.tsx`
  - `league-web/src/lib/constants/ddragon.ts`
  - `docs/MATCHCARD_REDESIGN.md`
  - `docs/app_state.md`

1. **LLM Pipeline Step 3 — Win Probability Model**: Train logistic regression on extracted state vectors. Start with stored `match_state_vector` features + match outcomes.
2. **LLM Pipeline Step 4–6 — ΔW Scoring + Aggregation**: Score actions via the trained model, compute per-action ΔW, aggregate by (champion, action, rank) with K≥50 threshold.
3. **LLM Pipeline Step 7 — LLM Prompt**: Build gap analysis payload and submit to Claude for recommendations. Populate `llm_analysis` table.
4. **Wire `extract_match_timeline_job` into existing match ingestion flow** — enqueue after `fetch_match_details_job` completes.
5. ~~**Fix race condition**~~ — **DONE** (session 15).
6. **Live Game integration** — requires polling architecture + `LiveGameCard` component.
7. **Consider server-side queue filtering** — current tab filtering is client-side.
8. **Implement vector embeddings** — `pgvector` is enabled; wire up `sentence-transformers` worker job.
