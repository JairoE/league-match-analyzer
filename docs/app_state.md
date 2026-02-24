# App State

**Last Updated:** 2026-02-24
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
- **Match card**: Redesigned `MatchCard` component (see `MATCHCARD_REDESIGN_SUMMARY.md`).
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
2. **Merge `frontend-4-error-handling`** — error handling is complete; branch is ready for PR review.
3. **Implement vector embeddings** — `pgvector` is enabled, `Match.to_embedding_text()` exists; wire up `sentence-transformers` worker job and embedding column.
4. **LLM service** — `league-llm` service stub exists; implement tool-calling agent with `GetChampionPerformanceTool`.
5. **E2E tests** — concurrent sign-in and match sync scenarios to validate the race condition fix.
