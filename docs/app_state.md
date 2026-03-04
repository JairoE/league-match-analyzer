# App State

**Last Updated:** 2026-03-03 (session 3)
**Branch:** `main`
**Status:** BUILDING — rank badges + laning stats implemented

---

## Current Phase

Active development on the `frontend-matches-paginated` branch. Server-side pagination is implemented for both match endpoints. Riot API sync is gated to page 1 only — subsequent pages query the database directly.

---

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
- **Match card**: `MatchCard` now supports `expanded?: boolean` for backward-compatible reuse in the detail panel.
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

## Next Recommended Steps

1. **Fix race condition** (see Open Tickets) — highest priority, blocks production reliability.
2. **Step 3** — Champion KDA History Chart (`recharts` bar chart, no backend changes needed).
3. **Step 4** — Live Game integration (lowest priority, requires polling architecture).
4. **Consider server-side queue filtering** — current tab filtering is client-side.
5. **Implement vector embeddings** — `pgvector` is enabled; wire up `sentence-transformers` worker job.
