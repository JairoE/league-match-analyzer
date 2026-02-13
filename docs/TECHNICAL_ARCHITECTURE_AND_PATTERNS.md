# Technical Architecture & Design Patterns

**Last Updated:** February 13, 2026
**Scope:** Full codebase read of `league-match-analyzer` (FastAPI + Next.js + Infrastructure)

## Executive Summary

The `league-match-analyzer` is a high-performance, asynchronous full-stack application designed to ingest, analyze, and serve League of Legends match data. It leverages a modern Python backend (FastAPI, SQLModel, ARQ) and a Next.js frontend, orchestrated via Docker Compose.

Key architectural highlights include a robust **3-tier rate limiting system** for the Riot API, an **upsert-heavy synchronization strategy** that blends real-time user requests with background ingestion, and a **hybrid data model** using Relational + JSONB storage.

## 1. System Architecture

### 1.1 High-Level Components

*   **API Service (`league-api`)**: FastAPI application serving REST endpoints. Handles auth, data synchronization, and business logic.
*   **Worker Service (`league-worker`)**: ARQ (Redis-backed) worker process for background tasks (match ingestion, details fetching).
*   **LLM Service (`league-llm`)**: Dedicated service for AI operations (embeddings, RAG), currently skeletal/provisioned.
*   **Frontend (`league-web`)**: Next.js 16 application using App Router and React Server Components.
*   **Data Stores**:
    *   **PostgreSQL**: Primary data store with `pgvector` extension enabled.
    *   **Redis**: Caching, Rate Limiting counters, and Task Queue (ARQ).

### 1.2 Data Flow & Synchronization

The system employs a **"Stateless Lookup with Side-Effect Persistence"** pattern, particularly visible in the `/search` endpoints:

1.  **Request**: User searches for a Riot ID (`GameName#Tag`).
2.  **Live Fetch**: API client fetches Account, Summoner, and Match IDs directly from Riot API (ensuring freshness).
3.  **Idempotent Upsert**:
    *   `find_or_create_riot_account`: Upserts identity data.
    *   `upsert_matches_for_riot_account`: efficiently inserts new match IDs and links them to the account.
4.  **Hybrid Backfill**:
    *   **Inline**: For the specific matches requested, missing details are fetched immediately (`backfill_match_details_inline`) to unblock the UI.
    *   **Background**: A task is enqueued (`enqueue_details_background`) to fetch full details for all other matches asynchronously.

## 2. Backend Design Patterns (Python/FastAPI)

### 2.1 Riot API Integration (`app/services/riot_api_client.py`)

*   **Resilience**: Implements exponential backoff with jitter for network errors and 5xx responses.
*   **Rate Limiting Compliance**:
    *   **Custom Rate Limiter**: `RiotRateLimiter` (Redis-backed) implements the sliding window algorithm.
    *   **Dynamic Configuration**: Parses `X-App-Rate-Limit` and `X-Method-Rate-Limit` headers from every response to adjust limits in real-time.
    *   **Global Backoff**: Respects `Retry-After` headers globally across all workers.
*   **Async Context**: Designed as an async context manager (`async with RiotApiClient()`) for deterministic resource cleanup.

### 2.2 Background Jobs (`app/services/background_jobs.py`)

*   **Library**: `arq` (Async Redis Queue).
*   **Shared Context**: Workers initialize a shared `RiotApiClient` on startup to reuse connection pools and rate limiters.
*   **Job Types**:
    *   `fetch_riot_account_matches_job`: Pagination-aware match ID fetching.
    *   `fetch_match_details_job`: Batch fetching of match payloads.
    *   **Cron**: `sync_all_riot_accounts_matches` runs every 6 hours.

### 2.3 Database Modeling (`app/models`)

*   **Library**: `SQLModel` (SQLAlchemy + Pydantic).
*   **Hybrid Storage**:
    *   **Relational**: Core entities (`User`, `RiotAccount`, `Match`) have structured columns for indexing/querying.
    *   **Document**: `Match.game_info` uses `JSONB` to store the raw, schema-less Riot payload, allowing for flexibility and preventing schema drift.
    *   **Vector Ready**: Infrastructure includes `pgvector` dependencies, preparing `Match` models for future embedding columns.
*   **Many-to-Many**: `RiotAccountMatch` join table allows efficient querying of matches per user without data duplication.
*   **UUIDs**: Universally used for primary keys (`default_factory=uuid4`).

### 2.4 Observability

*   **Structured Logging**: `app.core.logging` enables JSON logging with `extra` context dictionary support (`logger.info("event", extra={...})`).
*   **Metrics**: `increment_metric_safe` helper for tracking job success/failure rates and API status codes.

## 3. Frontend Architecture (Next.js/TypeScript)

### 3.1 Networking & Caching

*   **Typed API Client** (`api.ts`):
    *   Generic wrappers (`apiGet<T>`, `apiPost<T>`) for type safety.
    *   **Client-Side Cache**: Simple in-memory LRU-like cache (`cache.ts`) with TTL to reduce redundant network calls during navigation.
*   **Session Management**: `UserSession` type and logic for handling authenticated state.

### 3.2 Component Design

*   **Hydration Handling**: `useEffect` hooks to manage client-side only state (session checks) and prevent hydration mismatches (`isHydrated` pattern).
*   **Forms**: Composition pattern separating `SignInForm` and `SignUpForm` logic.

## 4. Infrastructure & DevOps

### 4.1 Deployment

*   **Docker Compose**: Orchestrates `api`, `worker`, `db`, and `redis` services.
*   **Makefile**: providing simplified commands for development (`api-dev`, `worker-dev`, `db-migrate`).
*   **Railway**: Configured via `railway.json` using `nixpacks` builder for production deployment.

### 4.2 Database Management

*   **Alembic**: Async migration environment.
*   **Connection Pooling**: `asyncpg` with `pool_pre_ping=True` to handle dropped connections in long-running workers.

## 5. Key Updates from Previous Read

*   **Riot API Client Evolution**: The client now includes a highly sophisticated, Redis-backed rate limiter that dynamically adapts to Riot's header responses.
*   **Stateless Search**: The `/search` endpoint architecture has been refined to support instant-feedback lookups without requiring prior user registration.
*   **LLM Service Stub**: A dedicated `league-llm` service structure exists, though currently minimal, indicating the architectural separation of concerns for future AI features.
*   **Metric Instrumentation**: Added internal metric tracking (`worker_metrics.py`) for job reliability monitoring.

## 6. Future Roadmap Indicators

*   **Embeddings**: The presence of `pgvector` and the `Match.to_embedding_text()` method signals imminent implementation of vector search.
*   **LLM Agents**: The `league-llm` service is positioned to host the AI agents described in the project rules.

---
*Generated by Cursor Agent on 2026-02-13*
