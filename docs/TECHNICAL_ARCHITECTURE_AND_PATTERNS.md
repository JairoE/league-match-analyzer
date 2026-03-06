# Technical Architecture & Design Patterns

**Last Updated:** March 5, 2026
**Scope:** Full codebase of `league-match-analyzer` (FastAPI + Next.js + Infrastructure + LLM Pipeline)

## Executive Summary

The `league-match-analyzer` is a high-performance, asynchronous full-stack application designed to ingest, analyze, and serve League of Legends match data. It leverages a modern Python backend (FastAPI, SQLModel, ARQ) and a Next.js frontend, orchestrated via Docker Compose and deployed on Railway.

Key architectural highlights include a robust **Redis-backed rate limiting system** for the Riot API, an **upsert-heavy synchronization strategy** that blends real-time user requests with background ingestion, a **hybrid data model** using Relational + JSONB storage, and an **LLM data pipeline** for win probability-based match analysis following the xPetu thesis framework.

## 1. System Architecture

### 1.1 High-Level Components

| Component | Location | Tech | Port |
|---|---|---|---|
| **API Service** (`league-api`) | `services/api/` | FastAPI, SQLModel, SQLAlchemy 2.0 async, Pydantic v2 | 8000 |
| **Worker Service** (`league-worker`) | `services/api/` (shared code) | ARQ (Redis-backed) | N/A |
| **Frontend** (`league-web`) | `league-web/` | Next.js 16, React 19, TypeScript 5, recharts | 3000 |
| **LLM Service** (stub) | `services/llm/` | Python, ARQ | N/A |

**Data Stores:**
- **PostgreSQL 16**: Primary data store with `pgvector` extension enabled (port 5432)
- **Redis 7**: Caching, rate limiting counters, task queue, timeline cache (port 6379)

### 1.2 Data Flow & Synchronization

The system employs a **"Stateless Lookup with Side-Effect Persistence"** pattern:

1.  **Request**: User searches for a Riot ID (`GameName#Tag`).
2.  **Live Fetch**: API client fetches Account, Summoner, and Match IDs directly from Riot API (ensuring freshness).
3.  **Idempotent Upsert**:
    - `find_or_create_riot_account`: Upserts identity data.
    - `upsert_matches_for_riot_account`: efficiently inserts new match IDs and links them to the account.
4.  **Hybrid Backfill + Warmup**:
    - **Inline (Pre-query)**: Missing details are backfilled by game IDs (`backfill_match_details_by_game_ids`) before the page-1 DB list query so ordering is correct on first response.
    - **Inline (Fallback)**: `backfill_match_details_inline` remains as a safety net after the query if missing `game_info` rows are still detected.
    - **Background (Timeline warmup)**: Page-1 routes enqueue missing timeline cache work (`enqueue_missing_timeline_jobs`) directly from router background tasks.

### 1.3 LLM Data Pipeline

An 8-step pipeline (Steps 1–2 implemented) for win probability-based match analysis:

1. **Ingest**: Fetch timeline from Riot API with Redis caching (1h TTL).
2. **Extract**: Pull per-minute state vectors and discrete action events from timeline data.
3. **Score** (future): Apply win probability model $w(x)$ to pre/post-action states.
4. **Compute ΔW** (future): $\Delta W(d) = w(z) - w(x)$ per action.
5. **Aggregate** (future): Mean ΔW per action type with K≥50 sample threshold.
6. **Compare** (future): Rank summoner choices vs. population-optimal alternatives.
7. **Prompt LLM** (future): Submit gap analysis to Claude for recommendations.
8. **Store** (future): Persist output to `llm_analysis` table.

See `docs/LLM_DATA_PIPELINE.md` for the full specification.

## 2. Backend Design Patterns (Python/FastAPI)

### 2.1 Riot API Integration (`app/services/riot_api_client.py`)

- **Resilience**: Exponential backoff with jitter for network errors and 5xx responses.
- **Rate Limiting Compliance**:
  - **Custom Rate Limiter** (`RiotRateLimiter`): Redis-backed sliding window algorithm.
  - **Dynamic Configuration**: Parses `X-App-Rate-Limit` and `X-Method-Rate-Limit` headers from every response to adjust limits in real-time.
  - **Global Backoff**: Respects `Retry-After` headers globally across all workers.
- **Async Context**: Designed as an async context manager (`async with RiotApiClient()`) for deterministic resource cleanup.
- **Timeline Support**: `fetch_match_timeline()` for the `/timeline` endpoint, used by both laning stats and the LLM pipeline.

### 2.2 Background Jobs (`app/jobs/`)

- **Library**: `arq` (Async Redis Queue).
- **Shared Context**: Workers initialize a shared `RiotApiClient` on startup to reuse connection pools and rate limiters.
- **Job Types**:
  - `fetch_riot_account_matches_job`: Pagination-aware match ID fetching.
  - `fetch_match_details_job`: Batch fetching of match payloads.
  - `extract_match_timeline_job`: Timeline ingest, state vector + action extraction, DB persistence. Idempotent (skips if vectors already exist).
  - `fetch_timeline_cache_job`: Timeline prefetch/caching for match detail expansion UX.
  - **Cron**: `sync_all_riot_accounts_matches` runs every 6 hours.

### 2.3 Request-Path Simplification Pattern

- **Flattened enqueue path**: routers call `background_tasks.add_task(enqueue_missing_timeline_jobs, match_ids)` directly.
- Enqueue service performs Redis `MGET` pre-filtering; ARQ jobs use deterministic `_job_id` signatures.

### 2.4 Service Layer (`app/services/`)

| Service | Purpose |
|---|---|
| `riot_api_client.py` | HTTP client for all Riot API endpoints with rate limiting |
| `riot_sync.py` | Match synchronization, timeline stats (laning phase CS/gold diffs) |
| `match_sync.py` | Find-or-create matches, upsert match records |
| `riot_account_upsert.py` | Riot account upsert logic |
| `state_vector.py` | Game state vector extraction from timeline data |
| `action_extraction.py` | Discrete action extraction (item purchases, objective kills) |
| `live_game.py` | Live game spectator data with SSE streaming |
| `champions.py` | Champion data management |
| `champion_seed.py` | Auto-seed champions from Data Dragon on startup |
| `matches.py` | Match query and listing |
| `rate_limiter.py` | Redis-backed sliding window rate limiter |
| `cache.py` | Redis cache helpers |
| `worker_metrics.py` | Job metric tracking via `increment_metric_safe` |

### 2.4 State Vector Extraction (`app/services/state_vector.py`)

Extracts per-minute `GameStateVector` from Riot timeline data following the xPetu thesis framework (Table 5: 75.9% accuracy, 0.90% ECE):

- **Per-player features (x10)**: `position.x/y`, `level`, `totalGold`, `damageDealtToChampions`, `damageTaken`, kills/deaths/assists (from `CHAMPION_KILL` events)
- **Per-team features (x2)**: voidgrubs, dragons, barons, turrets, inhibitors (from `ELITE_MONSTER_KILL` and `BUILDING_KILL` events)
- **Global features**: `timestamp`, `average_rank`
- **Design**: Cumulative KDA and objective trackers; nearest-frame snapping (no sub-minute interpolation per thesis Markov assumption)
- **Output**: `GameStateVector.to_feature_dict()` flattens into named keys (`p1_level`, `t100_dragons`, etc.) for model input

### 2.5 Action Extraction (`app/services/action_extraction.py`)

V1 action types for ΔW computation:

- **Item Purchases** (`ITEM_PURCHASE`): Legendary items only (90+ item IDs in `LEGENDARY_ITEM_IDS` set). Tracks `ITEM_UNDO`, `ITEM_SOLD`, `ITEM_DESTROYED` for post-state determination.
- **Objective Kills** (`OBJECTIVE_KILL`): Dragon, Baron, Rift Herald. Post-state set to 4 minutes after kill (buff window).
- **Clamping**: Post-state minutes clamped to available state vector range.

### 2.6 Database Modeling (`app/models/`)

- **Library**: SQLModel (SQLAlchemy + Pydantic).
- **Core Tables**:

| Model | Table | Key Columns |
|---|---|---|
| `User` | `user` | Auth credentials |
| `RiotAccount` | `riot_account` | PUUID, game name, tag line, summoner data |
| `Match` | `match` | `game_id`, `game_info` (JSONB), basic match metadata |
| `RiotAccountMatch` | `riot_account_match` | M2M join table |
| `UserRiotAccount` | `user_riot_account` | User-to-Riot account link |
| `Champion` | `champion` | Name, image URL (auto-seeded from DDragon) |

- **LLM Pipeline Tables**:

| Model | Table | Key Columns |
|---|---|---|
| `MatchStateVector` | `match_state_vector` | `match_id` FK, `minute`, `features` (JSONB). Unique on `(match_id, minute)`. |
| `MatchActionRecord` | `match_action` | `match_id` FK, `action_type`, `participant_id`, `action_detail` (JSONB), `pre_state_minute`, `post_state_minute`, `delta_w`/`pre_win_prob`/`post_win_prob` (nullable, populated by scorer). |
| `LLMAnalysis` | `llm_analysis` | `riot_account_id` FK, `champion_name`, `rank_tier`, `match_ids`, `schema_version`, `input_payload`/`output_payload`/`recommendations` (JSONB), `model_name`, token counts. |

- **Storage Strategy**: Hybrid relational + JSONB. Structured columns for indexing/querying; `JSONB` for flexible payloads (`game_info`, `features`, `action_detail`).
- **UUIDs**: Universally used for primary keys (`default_factory=uuid4`).
- **pgvector**: Extension enabled for future vector search.

### 2.7 API Routers (`app/api/routers/`)

| Router | Endpoints | Purpose |
|---|---|---|
| `search.py` | `GET /search/{riot_id}/matches` | Paginated search-first match lookup |
| `matches.py` | `GET /riot-accounts/{id}/matches`, `GET /matches/{id}/timeline-stats` | Auth match list, laning stats |
| `auth.py` | `POST /users/sign_in`, `POST /users/sign_up` | Authentication |
| `rank.py` | `GET /rank/batch?puuids=csv` | Batch rank lookup (Redis-cached) |
| `live_game.py` | `GET /live-game/{riot_id}` | SSE live game stream |
| `champions.py` | `GET /champions/{id}` | Champion data |
| `ops.py` | `GET /health` | Health check |

### 2.8 Observability

- **Structured Logging**: `app.core.logging` enables JSON logging with `extra` context dictionary support (`logger.info("event", extra={...})`).
- **Metrics**: `increment_metric_safe` helper for tracking job success/failure rates, API status codes, and pipeline stage counts.

## 3. Frontend Architecture (Next.js/TypeScript)

### 3.1 Application Structure

- **Framework**: Next.js 16 with App Router and React 19
- **Language**: TypeScript 5 with strict type checking
- **Styling**: CSS Modules for component-scoped styles + global CSS with CSS custom properties (`--match-victory-bg`, `--match-text-blue`, etc.)
- **Charts**: recharts for Champion KDA history bar charts
- **Build System**: Next.js built-in bundler with Turbopack support

### 3.2 Routing & Pages

| Route | Page | Description |
|---|---|---|
| `/` | `page.tsx` | Search interface with optional auth |
| `/home` | `home/page.tsx` | Match results dashboard (auth flow) |
| `/riot-account/[riotId]` | `riot-account/[riotId]/page.tsx` | Search results view with pagination |
| `/auth` | `auth/` | Authentication pages |

### 3.3 Component Architecture

All components are folderized in `src/components/`, each with its own CSS module:

| Component | Files | Purpose |
|---|---|---|
| `MatchesTable/` | `MatchesTable.tsx`, `useMatchSelection.ts`, `useMatchDetailData.ts`, `constants.ts`, `SkeletonRows.tsx` | Table + tabs + pagination + detail data fetching |
| `MatchCard/` | `MatchCard.tsx`, `ItemSlot.tsx`, `Teams.tsx`, `ChampionKdaChart.tsx`, `match-card.utils.ts`, `types.ts` | Decomposed match detail card (~200-line orchestrator, `memo`-wrapped) |
| `MatchDetailPanel/` | Side overlay rendering `MatchCard` in expanded mode |
| `MatchRow/` | Individual match table row |
| `Pagination/` | Previous/Next + "Page X of Y" |
| `LiveGameCard/` | Live game display with SSE |
| `Auth/` | `AuthForm`, `SignInForm`, `SignUpForm` |
| `Header/`, `SubHeader/`, `SearchBar/`, `FeatureCard/` | Layout and UI primitives |

### 3.4 State Management & Data Flow

- **Session Management**: `sessionStorage`-backed `useSession` hook
- **Match Selection**: `useMatchSelection` hook — `selectedMatchId`, `handleRowClick`, `handleClosePanel`, `clearSelection`
- **Detail Data Fetching**: `useMatchDetailData` hook — fetches champion data, rank badges, and laning stats on match selection; uses functional updater pattern for state merging
- **Queue Filtering**: Client-side tab grouping via `GameQueueGroup` / `GameQueueMode` types in `src/lib/types/queue.ts`
- **Error Handling**: `useAppError(scope)` hook with `reportError`/`clearError`; page-level interception for context-specific messages

### 3.5 Networking & Caching

- **Typed API Client** (`src/lib/api.ts`): Generic `apiGet<T>` / `apiPost<T>` wrappers with base URL from environment
- **Client-Side Cache** (`src/lib/cache.ts`): In-memory LRU-like cache with TTL
- **Error Normalization** (`src/lib/errors/`):
  - `ApiError` class with `status`, `detail`, `riotStatus` fields
  - `buildApiErrorFromResponse` / `toApiError` for HTTP and plain error normalization
  - `formatApiError` — translates backend codes via `DETAIL_MESSAGES` lookup; handles `riot_api_failed` with `riotStatus` branching (404/429/other); HTTP status fallbacks
  - `useAppError(scope)` React hook — `{ errorMessage, reportError, clearError }`

- **Composition Pattern**:
  - `MatchPageShell` - Shared page layout (Header + SubHeader + SearchBar + error + children) used by `/home` and `/riot-account/[riotId]`
  - `AuthForm` - Shared form logic for sign in/up
  - `SignInForm` / `SignUpForm` - Specific implementations
  - `MatchCard` - Reusable match display component
- **Hydration Handling**:
  - `isHydrated` pattern to prevent hydration mismatches
  - Client-side only state initialization with `useEffect`
- **Type Safety**: Full TypeScript coverage with shared type definitions

### 3.6 Performance Optimizations

- **Code Splitting**: Automatic route-based code splitting via App Router
- **Memoization**: `MatchCard` and `Teams` wrapped in `React.memo`; selective `useMemo` for champion history grouping and date formatting
- **Selective Fetching**: Champion data fetched only for missing IDs; rank batch only fetches PUUIDs not already cached
- **Pagination**: Riot API sync gated to page 1; pages 2+ are DB-only (zero Riot API calls)
- **Effect Separation**: Search page splits account fetch (once per riotId) from matches fetch (per page change) to avoid redundant API calls

## 4. Infrastructure & DevOps

### 4.1 Deployment

- **Docker Compose** (`infra/compose/docker-compose.yml`): Orchestrates `api`, `worker`, `db`, and `redis` services
- **Makefile**: Simplified development commands (`api-dev`, `db-up`, `db-migrate`, `lint`, `test`)
- **Railway**: Deployed via `railway.json` + nixpacks builder
  - API Start Command: `entrypoint.sh` (Uvicorn only, no migrations at boot)
  - API Release Command: `release.sh` (runs `alembic upgrade head` as pre-deploy step)
  - Worker: Private service, no public domain, no HTTP healthcheck

### 4.2 Database Management

- **Alembic**: Async migration environment with Railway pre-deploy release step
- **Connection Pooling**: `asyncpg` with `pool_pre_ping=True` for long-running workers
- **Migrations**: `services/api/app/db/migrations/versions/` — latest: `20260305_0002_llm_pipeline_tables.py`

### 4.3 Testing

### 4.3 Testing

- **Backend**: pytest with `asyncio_mode = "auto"` in `services/api/tests/`
- **Test Coverage**: Riot API client retry, match fetch, state vector extraction (10 tests), action extraction (12 tests); 42/42 tests pass.
- **No frontend test suite** currently.

## 5. Key Updates

- **Riot API Client Evolution**: The client now includes a highly sophisticated, Redis-backed rate limiter that dynamically adapts to Riot's header responses.
- **Stateless Search**: The `/search` endpoint architecture supports instant-feedback lookups without requiring prior user registration.
- **Page-1 Correctness Hardening**: Match details are backfilled before initial page-1 list ordering to avoid stale first-load ordering when new matches were just upserted.
- **Timeline Warmup Refactor**: Timeline enqueue was flattened to direct router->service dispatch, replacing the extra wrapper layer.
- **LLM Service Stub**: A dedicated `league-llm` service structure exists, though currently minimal, indicating the architectural separation of concerns for future AI features.
- **Metric Instrumentation**: Added internal metric tracking (`worker_metrics.py`) for job reliability monitoring.

## 5. Design Decisions & Trade-offs

- **Client-side tab filtering**: Queue type filtering happens in the frontend, not the API. Some pages may show fewer items after filtering. Acceptable trade-off to avoid API complexity.
- **JSONB over normalized columns**: `game_info`, `features`, `action_detail` stored as JSONB for flexibility; structured columns added only for fields that need indexing.
- **No sub-minute interpolation**: State vectors use 1-minute resolution with nearest-frame snapping. The thesis confirms momentum effects are negligible (Markov assumption holds).
- **Legendary items only**: Action extraction focuses on 90+ legendary items for clearest strategic signal; component items and boots excluded.
- **Idempotent extraction**: `extract_match_timeline_job` checks for existing state vectors before processing; safe to re-enqueue.

## 6. Known Issues

- **Race condition**: `_get_or_create_match` and `upsert_user_from_riot` use non-atomic check-then-insert, causing `IntegrityError` under concurrency. Fix requires `INSERT ... ON CONFLICT`.

## 7. Roadmap

- **LLM Pipeline Steps 3–7**: Win probability model → ΔW scoring → aggregation → LLM prompt → recommendation storage
- **Wire timeline extraction**: Enqueue `extract_match_timeline_job` after `fetch_match_details_job` completes
- **Server-side queue filtering**: Move tab filtering to the API for more accurate pagination counts
- **Vector embeddings**: `pgvector` is enabled; wire up for semantic search capabilities
