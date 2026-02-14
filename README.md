# League Match Analyzer

A full-stack League of Legends match analysis platform with AI-powered insights, real-time match tracking, and comprehensive performance analytics.

**Live Application:** https://league-match-analyzer.vercel.app/

- currently needs a daily riot api key, contact @jairoE to update on the backend

---

## What It Does

- **Match History Tracking**: View detailed match history for any League of Legends summoner
- **Performance Analytics**: Deep dive into KDA, CS/min, damage share, vision score, and more
- **Champion Insights**: Champion-specific performance metrics and build recommendations
- **On-demand Sync**: Fetches from Riot on request and persists results for reuse
- **LLM-Powered Analysis**: Semantic search and natural language queries over match data (upcoming)

---

## Architecture Overview

### Frontend — Next.js on Vercel

**Deployment:** https://league-match-analyzer.vercel.app/

**Stack:**

- **Framework**: Next.js 16 (App Router) with TypeScript
- **Styling**: CSS Modules + global CSS (no Tailwind currently)
- **Data Fetching**: Native `fetch` with in-memory TTL cache
- **State Management**: Session storage for user state
- **Hosting**: Vercel (automatic deployments from `main` branch)

**Key Features:**

- `/` — Sign in/up flow
- `/home` — Matches dashboard with card-based UI
- Client-side caching for champion data and match details
- Responsive design optimized for desktop and mobile

**Environment Variables:**

```bash
NEXT_PUBLIC_API_BASE_URL=https://league-match-analyzer-production.up.railway.app
```

### Backend — FastAPI on Railway

**Deployment:** https://league-match-analyzer-production.up.railway.app

**Stack:**

- **API Framework**: FastAPI (async) with Uvicorn
- **Database**: PostgreSQL 16 with `pgvector` extension (hosted on Supabase)
- **Cache/Queue**: Redis 7 (available; caching/queueing not wired into request flows yet)
- **ORM**: SQLModel models + SQLAlchemy `AsyncSession` (SQLAlchemy 2.x)
- **Migrations**: Alembic with async engine support
- **Background Jobs**: ARQ worker for match ingestion + scheduled sync, plus in-process `asyncio` tasks (champion seeding)
- **Validation**: Pydantic v2 + pydantic-settings
- **HTTP Client**: httpx (async)
- **Language**: Python 3.11+

**Infrastructure:**

- **API Hosting**: Railway (automatic deployments from `main` branch)
- **Database**: Supabase PostgreSQL with pgvector for semantic search
- **Redis**: Railway Redis service (available; caching/job queue wiring in progress)
- **Migrations**: Auto-run on deployment via `entrypoint.sh`

**Key Features:**

- Async-first architecture for high concurrency
- Riot API integration via `httpx` (no caching/rate limiting implemented yet)
- Champion auto-seeding on startup via Data Dragon
- Background tasks for champion seed/reset via `asyncio.create_task`
- Structured logging with request ID tracking
- CORS-enabled for Vercel frontend

**Production Environment:**

- `DATABASE_URL`: Supabase PostgreSQL (Session mode, port 5432)
- `REDIS_URL`: Railway Redis service
- `RIOT_API_KEY`: Production Riot API key
- `CORS_ALLOW_ORIGINS`: Vercel frontend URL

---

## Local Development

### Prerequisites

- **Git** — version control
- **Make** — used to run all development commands via the `Makefile`
- **Python 3.11+** — backend runtime
- **Node.js 20.9+** — frontend runtime (required by Next.js 16)
- **Docker Desktop** — local Postgres + Redis containers
- **Bun** (optional) — for helper scripts in `scripts/`

**Install via Homebrew:**

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Git and Make come with Xcode Command Line Tools
xcode-select --install

# Install Python 3.11
brew install python@3.11

# Install Node.js (LTS)
brew install node

# Install Docker Desktop
brew install --cask docker
# Then open Docker Desktop from Applications and complete setup

# (Optional) Install Bun
brew install oven-sh/bun/bun
```

**Verify your setup:**

```bash
git --version        # any recent version
make --version       # GNU Make 3.81+
python3.11 --version # 3.11.x
node --version       # v20.9+
docker --version     # any recent version
```

### Running the Frontend Locally

```bash
cd league-web
npm install
npm run dev
```

Open `http://localhost:3000`.

**Configure API endpoint in `league-web/.env.local`:**

```bash
# Point to local API
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Or point to production API
NEXT_PUBLIC_API_BASE_URL=https://league-match-analyzer-production.up.railway.app
```

### Running the Backend Locally

**1. Create Virtual Environment:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

**2. Install Dependencies:**

```bash
make install
```

**3. Start Database + Redis:**

```bash
make db-up
```

**4. Configure Environment:**

```bash
cp services/api/.env.example services/api/.env
```

Edit `services/api/.env` with your Riot API key.

**5. Run Migrations:**

```bash
make db-migrate
```

**6. Start API:**

```bash
make api-dev
```

API will be available at `http://localhost:8000`.

**Verify:**

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

**7. Start Background Worker (separate terminal):**

The ARQ worker handles background match ingestion and scheduled sync jobs. It requires Redis to be running (started in step 3).

```bash
cd services/api
../../.venv/bin/arq app.services.background_jobs.WorkerSettings
```

You should see output like:

```
Starting worker for 2 functions: fetch_user_matches_job, fetch_match_details_job
redis_version=7.x.x mem_usage=...
```

The worker starts a cron job (`sync_all_users_matches`) on startup that enqueues match sync for all users. On-demand jobs are enqueued by the API when users sign in or request match refreshes.

> **Troubleshooting: Worker starts with wrong/stale functions**
>
> If the worker output shows unexpected function names (e.g. old functions that no longer exist in the codebase), the installed `app` package in site-packages is stale. The `app/` package is installed as a Python package via `pyproject.toml`, and ARQ resolves imports from the **installed** copy, not your local source files.
>
> Fix by reinstalling in editable mode (from the repo root):
>
> ```bash
> .venv/bin/pip install --no-cache-dir -e services/api[dev]
> ```
>
> The `-e` flag creates a symlink so future code changes are picked up without reinstalling. The `--no-cache-dir` flag prevents pip from reusing a cached wheel from an older build.
>
> **Always use `make install` (which uses `-e`) instead of `pip install .`** when setting up the project. A bare `pip install .` copies a snapshot of the code into site-packages, which goes stale as you edit.

---

## Development Tooling

- **Docker Compose**: Postgres + Redis for local dev
- **Makefile**: Common development commands
- **Bun scripts**: Helper scripts in `scripts/`
- **Ruff**: Python linting and formatting
- **Pytest**: Test suite
- **Alembic CLI**: Database schema migrations
- **Uvicorn**: FastAPI development server with hot reload

---

## Monorepo Structure

```
league-match-analyzer/
├── Makefile                 # Development commands
├── packages/
│   └── shared/              # Shared models, schemas, utilities
│       ├── __init__.py
│       └── pyproject.toml
├── services/
│   ├── api/                 # FastAPI service
│   │   ├── app/             # Application code
│   │   ├── Dockerfile       # Multi-stage build
│   │   ├── entrypoint.sh    # Migrations + startup
│   │   ├── alembic.ini      # Migration config
│   │   └── pyproject.toml   # Dependencies
│   └── llm/                 # LLM worker service (ARQ)
│       ├── main.py          # Worker entry point
│       └── pyproject.toml   # Dependencies
├── league-web/              # Next.js frontend
│   ├── src/
│   │   ├── app/             # App Router pages
│   │   ├── components/      # React components
│   │   └── lib/             # API client and utilities
│   ├── package.json
│   └── next.config.js
├── infra/
│   └── compose/             # Docker Compose for local dev
├── docs/                    # Deployment and migration docs
└── scripts/                 # Bun helper scripts
```

---

## Recent Updates

### Production Deployment ✅

- **Frontend deployed to Vercel** — Automatic deployments from `main`
- **Backend deployed to Railway** — Connected to Supabase PostgreSQL + Railway Redis
- **Automatic migrations** — `entrypoint.sh` runs Alembic migrations on deploy
- **Health checks enabled** — `/health` endpoint for Railway monitoring

### Infrastructure

- Supabase PostgreSQL with `pgvector` extension (Session pooler, port 5432)
- Railway Redis (configured; caching/job queue wiring in progress)
- CORS configured for Vercel frontend
- Structured logging with request ID tracking

### Data & Features

- Champion catalog auto-seeds from Data Dragon on startup
- Match history fetching with Riot API integration
- User sign-in/up flows; frontend stores the returned user in `sessionStorage`
- ARQ worker with match ingestion jobs (`fetch_user_matches_job`, `fetch_match_details_job`) and scheduled sync (`sync_all_users_matches`)

---

## API Endpoints

**Base URL (Production):** `https://league-match-analyzer-production.up.railway.app`

| Endpoint                      | Method | Description                     |
| ----------------------------- | ------ | ------------------------------- |
| `/health`                     | GET    | Health check                    |
| `/users/sign_up`              | POST   | User registration               |
| `/users/sign_in`              | POST   | User authentication             |
| `/fetch_user`                 | POST   | Fetch/create user profile       |
| `/users/{user_id}/fetch_rank` | GET    | Fetch ranked data for a user    |
| `/users/{user_id}/matches`    | GET    | User match history (up to 20)   |
| `/matches/{match_id}`         | GET    | Detailed match data             |
| `/champions`                  | GET    | All champions                   |
| `/champions/{champ_id}`       | GET    | Champion metadata by ID         |
| `/reset/champions`            | POST   | Schedule clear+reseed champions |
| `/reset/champions/{champ_id}` | POST   | Schedule reseed one champion    |

**Authentication:** Stateless API; the frontend persists the returned user in `sessionStorage`

**Rate Limiting / Caching:** Not implemented yet in the Riot client; Redis is present for future caching/queueing

---

## Services Architecture

### API Service (`services/api/`)

FastAPI application with async endpoints:

- Riot API integration via `httpx`
- Data Dragon client for champion metadata
- Auto-seeding of champion catalog on startup
- Structured logging with request ID middleware
- CORS configuration for frontend

### Background Worker (`services/api/`)

ARQ worker for match data ingestion and scheduled syncing:

- `fetch_user_matches_job` — Fetches match IDs from Riot API for a user
- `fetch_match_details_job` — Batch-fetches match detail payloads from Riot API
- `sync_all_users_matches` — Cron job that enqueues match sync for all users
- Redis-backed job queue

### LLM Worker Service (`services/llm/`)

ARQ worker for future AI background tasks:

- Embedding generation for semantic search (planned)
- Match summarization and insights (planned)
- Natural language query processing (planned)
- Redis-backed job queue (configured)

---

## Testing and Quality

```bash
# Run linter
make lint

# Run test suite
make test

# Run specific test file
pytest services/api/tests/test_users.py
```

---

## Makefile Commands

| Command            | Description                                 |
| ------------------ | ------------------------------------------- |
| `make install`     | Install all packages in editable (dev) mode |
| `make api-dev`     | Start API with hot reload                   |
| `make worker-dev`  | Start ARQ background worker                 |
| `make llm-dev`     | Start LLM worker                            |
| `make db-up`       | Start Postgres + Redis (Docker)             |
| `make db-down`     | Stop Docker services                        |
| `make db-migrate`  | Apply Alembic migrations                    |
| `make db-revision` | Generate new migration                      |
| `make lint`        | Run ruff linter                             |
| `make test`        | Run pytest                                  |

### Monitoring & Debugging

**Quick Status Check:**

```bash
# See all Redis keys
docker exec league_redis redis-cli KEYS '*'

# Watch Redis in real-time (Ctrl+C to stop)
docker exec league_redis redis-cli MONITOR

# Check worker logs
# (Run this in the terminal where worker-dev is running)
```

**Check Job Queue:**

```bash
# Get all keys with counts
docker exec league_redis redis-cli --scan --pattern '*'

# Get specific job queue info
docker exec league_redis redis-cli LLEN arq:queue

# See job results (if any)
docker exec league_redis redis-cli KEYS 'arq:result:*'
```

**PostgreSQL Database Monitoring:**

```bash
# Connect to PostgreSQL database
docker exec -it league_postgres psql -U league -d league

# Quick connection check (one-liner)
docker exec league_postgres psql -U league -d league -c "SELECT version();"

# List all tables with row counts
docker exec league_postgres psql -U league -d league -c "
  SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    (SELECT count(*) FROM (SELECT 1 FROM pg_class WHERE relname = tablename LIMIT 1) s) as exists
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY tablename;
"

# Check table row counts (fast estimate)
docker exec league_postgres psql -U league -d league -c "
  SELECT
    relname AS table_name,
    n_live_tup AS row_count
  FROM pg_stat_user_tables
  ORDER BY n_live_tup DESC;
"

# View active database connections
docker exec league_postgres psql -U league -d league -c "
  SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    query_start,
    LEFT(query, 50) as query
  FROM pg_stat_activity
  WHERE datname = 'league';
"

# Check specific table contents (example: user table)
docker exec league_postgres psql -U league -d league -c "SELECT * FROM \"user\" LIMIT 10;"

# Check user table with specific columns
docker exec league_postgres psql -U league -d league -c "SELECT id, summoner_name, riot_id, puuid FROM \"user\" LIMIT 10;"

# Check match table
docker exec league_postgres psql -U league -d league -c "SELECT id, game_id, game_start_timestamp FROM match LIMIT 10;"

# Check champion table
docker exec league_postgres psql -U league -d league -c "SELECT id, champ_id, name, nickname FROM champion LIMIT 10;"

# View table schema
docker exec league_postgres psql -U league -d league -c "\d+ \"user\""
docker exec league_postgres psql -U league -d league -c "\d+ match"
docker exec league_postgres psql -U league -d league -c "\d+ champion"

# Check Alembic migration history
docker exec league_postgres psql -U league -d league -c "SELECT * FROM alembic_version;"
```

**Database Performance:**

```bash
# Check database size
docker exec league_postgres psql -U league -d league -c "
  SELECT
    pg_database.datname,
    pg_size_pretty(pg_database_size(pg_database.datname)) AS size
  FROM pg_database
  WHERE datname = 'league';
"

# Check table sizes with indexes
docker exec league_postgres psql -U league -d league -c "
  SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS indexes_size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Check for slow queries (if pg_stat_statements is enabled)
docker exec league_postgres psql -U league -d league -c "
  SELECT
    calls,
    mean_exec_time::numeric(10,2) as avg_ms,
    max_exec_time::numeric(10,2) as max_ms,
    LEFT(query, 80) as query
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"
```

## Deployment

### Frontend (Vercel)

**Live URL:** https://league-match-analyzer.vercel.app/

**Configuration:**

- Auto-deploys from `main` branch
- Build command: `npm run build`
- Output directory: `.next`
- Environment variable: `NEXT_PUBLIC_API_BASE_URL`

### Backend (Railway)

**Live API:** https://league-match-analyzer-production.up.railway.app

**Configuration:**

- Auto-deploys from `main` branch
- Dockerfile path: `services/api/Dockerfile`
- Root directory: `/` (monorepo root)
- Health check: `/health`
- Automatic migrations via `entrypoint.sh`

**Infrastructure:**

- **Database:** Supabase PostgreSQL with pgvector extension
- **Cache/Queue:** Railway Redis service
- **Connection Mode:** Session pooler (port 5432, not transaction mode)

**See [Railway Deployment Guide](docs/RAILWAY_API_DEPLOYMENT.md) for detailed configuration.**

---

## Environment Variables

### Production (Railway + Vercel)

**Frontend (Vercel):**

```bash
NEXT_PUBLIC_API_BASE_URL=https://league-match-analyzer-production.up.railway.app
```

**Backend (Railway):**

```bash
DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[password]@aws-0-us-west-2.pooler.supabase.com:5432/postgres
REDIS_URL=redis://[railway-host]:[port]  # Auto-generated by Railway
RIOT_API_KEY=RGAPI-your-production-key
LOG_LEVEL=INFO
SERVICE_NAME=league-api
SQL_ECHO=false
CORS_ALLOW_ORIGINS=https://league-match-analyzer.vercel.app
```

### Local Development

**API Service (`services/api/.env`):**

| Variable             | Default                                                    | Description                |
| -------------------- | ---------------------------------------------------------- | -------------------------- |
| `DATABASE_URL`       | `postgresql+asyncpg://league:league@localhost:5432/league` | Async Postgres connection  |
| `REDIS_URL`          | `redis://localhost:6379/0`                                 | Redis connection           |
| `RIOT_API_KEY`       | `replace-me`                                               | Riot Games API key         |
| `LOG_LEVEL`          | `INFO`                                                     | Logging verbosity          |
| `SERVICE_NAME`       | `league-api`                                               | Service identifier in logs |
| `SQL_ECHO`           | `false`                                                    | Echo SQL queries           |
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000`                                    | Frontend URL for CORS      |

**LLM Service (`services/llm/.env`):**

| Variable         | Default                                                    | Description               |
| ---------------- | ---------------------------------------------------------- | ------------------------- |
| `DATABASE_URL`   | `postgresql+asyncpg://league:league@localhost:5432/league` | Async Postgres connection |
| `REDIS_URL`      | `redis://localhost:6379/0`                                 | Redis connection          |
| `OPENAI_API_KEY` | `your-openai-api-key`                                      | OpenAI API key            |
| `LOG_LEVEL`      | `INFO`                                                     | Logging verbosity         |

---

## Future Features

### Planned Enhancements

- **LLM-Powered Insights**: Natural language queries over match history using semantic search
- **Vector Embeddings**: Match context embeddings for similarity search and recommendations
- **Advanced Analytics**: Percentile rankings, trend analysis, and performance predictions
- **Real-time Match Tracking**: Live game updates and play-by-play analysis
- **Champion Build Recommendations**: AI-driven item build suggestions based on match context
- **Queue-Driven Architecture**: Move Riot API calls from request handlers to background jobs
- **Cache Optimization**: Tiered caching strategy (hot/warm/cold paths)
- **Rate Limit Management**: Advanced rate limit handling with backoff strategies

### Architecture Improvements

- Background job processing for all Riot API calls
- `/reset/{resource}` pattern for all database tables
- Enhanced logging and observability
- GraphQL API layer (optional)
- Websocket support for real-time updates

---

## Documentation

### Deployment Guides

- [Railway API Deployment](docs/RAILWAY_API_DEPLOYMENT.md) — Complete Railway deployment configuration (Supabase + Railway)
- [Migration Plan — Backend](docs/MIGRATION_PLAN_BACKEND.md) — Backend migration strategy
- [Migration Plan — Frontend](docs/MIGRATION_PLAN_FRONTEND.md) — Frontend architecture

### Development Docs

- [Database Setup](docs/DATABASE_SETUP.md) — Local database configuration
- [Phase 0 Endpoints](docs/PHASE0_ENDPOINTS.md) — API endpoint specifications

### Important Notes

- **Supabase Connection**: Use **Session pooler (port 5432)**, not Transaction pooler (port 6543)
- **Database URL Format**: Must include `+asyncpg` suffix: `postgresql+asyncpg://...`
- **Railway Root Directory**: Set to `/` (monorepo root), not `services/api/`
- **Dockerfile Path**: `services/api/Dockerfile` (relative to root)

---

## Contributing

This is an active development project. Key areas for contribution:

- LLM integration and semantic search
- Performance optimization
- API endpoint expansion
- Frontend UI/UX improvements
- Documentation and testing

**Development Workflow:**

1. Fork and clone the repository
2. Create a feature branch
3. Run tests: `make test`
4. Submit pull request to `main`

**Code Quality:**

- Run `make lint` before committing
- Follow existing code structure and patterns
- Add tests for new features
- Update documentation as needed

---

## License

This project is for educational and portfolio purposes.

**Riot Games:** League of Legends and all related content are trademarks of Riot Games, Inc.
