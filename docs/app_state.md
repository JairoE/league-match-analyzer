# App State

**Last Updated:** 2026-03-04
**Branch:** `frontend-components-refactor`
**Status:** STABLE — Champion pre-fetch filter restored

## What's Built

### Backend (FastAPI + ARQ)

- **Search flow**: `GET /search/{riot_id}/matches` — find-or-create account, upsert match IDs, backfill basic details inline, enqueue full details in background. Supports `?page=N&limit=N` pagination.
- **Auth match flow**: `GET /riot-accounts/{id}/matches` — paginated match list with Riot API sync on page 1 only.
- **Pagination schema**: `PaginatedMatchList` wraps `data` + `PaginationMeta` (page, limit, total, last_page).
- **Auth flow**: `POST /users/sign_in`, `POST /users/sign_up` — optional user authentication.
- **Riot API Client**: Redis-backed sliding-window rate limiter with dynamic header parsing and exponential backoff.
- **Background jobs**: `fetch_match_details_job` (batch), `sync_all_riot_accounts_matches` (cron every 6h).
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

| Ticket                                                                                                                                        | File                                                             | Status   |
| --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | -------- |
| Race condition in `_get_or_create_match` and `upsert_user_from_riot` — non-atomic check-then-insert causes `IntegrityError` under concurrency | `services/api/app/services/match_sync.py`, `riot_user_upsert.py` | **OPEN** |

**Fix required**: Replace select-then-insert with `INSERT ... ON CONFLICT DO NOTHING/DO UPDATE` for `Match` (by `game_id`), `User` (by `puuid`), and `RiotAccountMatch` (by `(user_id, match_id)`).

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
  → Enqueue full details → Redis → ARQ worker
  → Fetch full details (Riot API) → Upsert (DB)

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

1. **Fix race condition** (see Open Tickets) — highest priority, blocks production reliability.
2. **Step 2** — Live Game integration (lowest priority, requires polling architecture + `LiveGameCard` component).
3. **Consider server-side queue filtering** — current tab filtering is client-side.
4. **Implement vector embeddings** — `pgvector` is enabled; wire up `sentence-transformers` worker job.
