# App State

**Last Updated:** 2026-03-03
**Branch:** `frontend-4-error-handling`
**Status:** BUILDING

---

## Current Phase

Active development on the `frontend-4-error-handling` branch. Core search-to-home flow is functional. Frontend error handling is now complete — all machine-readable backend codes are translated to user-facing messages.

---

## What's Built

### Backend (FastAPI + ARQ)
- **Search flow**: `GET /search/{riot_id}/matches` — find-or-create account, upsert match IDs, backfill basic details inline, enqueue full details in background.
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

| Ticket | File | Status |
|---|---|---|
| Race condition in `_get_or_create_match` and `upsert_user_from_riot` — non-atomic check-then-insert causes `IntegrityError` under concurrency | `services/api/app/services/match_sync.py`, `riot_user_upsert.py` | **OPEN** |

**Fix required**: Replace select-then-insert with `INSERT ... ON CONFLICT DO NOTHING/DO UPDATE` for `Match` (by `game_id`), `User` (by `puuid`), and `RiotAccountMatch` (by `(user_id, match_id)`).

---

## Recent Changes (2026-03-03)

- Replaced match history card grid architecture with a table + side panel implementation.
- Added queue-type tab filtering with queue ID fallback resolution:
  `detail.info.queueId` -> `match.queueId` -> `undefined`.
- Cleaned now-unused page-level CSS rules related to old card-grid containers.
- Fixed `MatchCard` expanded mode behavior: details now render from `showDetails`, and the toggle
  button is hidden when `expanded` is true so side panel cards stay consistently expanded.
- Removed row-level champion metadata fetching from `MatchRow`; `MatchesTable` now preloads champion
  data once into a shared `championById` map to reduce request fan-out and duplicate fetch churn.
- Improved keyboard row activation accessibility: Space key now calls `preventDefault()` before row
  selection to avoid unintended page scrolling.
- Stabilized queue tab UX order using a fixed display sequence
  (Ranked Solo, Ranked Flex, Normal, ARAM, Arena, Swiftplay, Event, Other) and render-only-present
  tabs in that order.

Why this changed:
- Improve scanability and dense comparison for match history.
- Keep page components focused on data ownership while localizing interaction state in `MatchesTable`.
- Reuse `MatchCard` rendering logic for consistency and reduced duplication.
- Improve side panel reliability, reduce avoidable network burstiness, and make tab/filter behavior
  predictable for repeated user sessions.

---

## Request Flow Summary

```
User → Search (Riot ID) → GET /search/{riot_id}/matches
  → find_or_create_riot_account (DB upsert)
  → Rate limit check (Redis)
  → Fetch match IDs (Riot API)
  → Upsert match IDs (DB)
  → Backfill basic details inline (Riot API)
  → Return match list → Home page

Background (async):
  → Enqueue full details → Redis → ARQ worker
  → Fetch full details (Riot API) → Upsert (DB)

Optional:
  → Sign In/Up → POST /users/sign_in → Validate (DB) → Save session
```

---

## Next Recommended Steps

1. **Fix race condition** (see Open Tickets) — highest priority, blocks production reliability.
2. **Validate table architecture** — verify keyboard navigation, responsive behavior, and panel accessibility on both match pages.
3. **Merge `frontend-4-error-handling`** — error handling and match-history UX updates are ready for PR review.
4. **Implement vector embeddings** — `pgvector` is enabled, `Match.to_embedding_text()` exists; wire up `sentence-transformers` worker job and embedding column.
5. **LLM service** — `league-llm` service stub exists; implement tool-calling agent with `GetChampionPerformanceTool`.
