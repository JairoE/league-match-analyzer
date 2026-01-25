# League Match Analyzer

FastAPI + SQLModel backend for League of Legends match analysis, replacing the legacy Rails API.

---

## Project Structure

```
league-match-analyzer/
├── Makefile                 # Development commands
├── packages/
│   └── shared/              # Shared models, schemas, utilities
├── services/
│   ├── api/                 # FastAPI service
│   └── llm/                 # LLM worker service (ARQ)
├── infra/
│   └── compose/             # Docker Compose (Phase 1.5)
└── docs/                    # Migration plans and specs
```

---

## Recent Changes (Phase 1)

### Services Created

- **`services/api/`** — FastAPI service with async endpoints, structured logging, request ID middleware
- **`services/llm/`** — ARQ worker for background LLM jobs (embeddings, summarization)
- **`packages/shared/`** — Shared package for cross-service models and schemas

### Infrastructure

- Async SQLAlchemy engine with `asyncpg` driver
- Redis + ARQ wiring for background job queue
- Alembic migrations setup with async support
- pgvector extension enabled for future embeddings

### Configuration

- `pydantic-settings` for env-based configuration
- `.env.example` files for both services
- Makefile targets for common operations

---

## Prerequisites

- Python 3.11+
- PostgreSQL 14+ with pgvector extension
- Redis 7+

---

## Quick Start

### 1. Create Virtual Environment

```bash
cd league-match-analyzer
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
make install
```

Or manually:

```bash
pip install -e packages/shared
pip install -e services/api[dev]
pip install -e services/llm[dev]
```

### 3. Setup Database

**Option A — Manual:**

```bash
createdb league_api
psql league_api -c "CREATE EXTENSION IF NOT EXISTS vector"
```

**Option B — Docker (requires Phase 1.5):**

```bash
make db-up
```

### 4. Configure Environment

```bash
cp services/api/.env.example services/api/.env
cp services/llm/.env.example services/llm/.env
```

Edit `.env` files to match your local setup.

### 5. Run Migrations

```bash
make db-migrate
```

---

## Running Services

### API Service

Starts FastAPI with hot reload on `http://localhost:8000`.

```bash
make api-dev
```

Or manually:

```bash
cd services/api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Verify:**

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

**Endpoints:**

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `POST /users/sign_up` | User registration |
| `POST /users/sign_in` | User login |
| `GET /users/:id/matches` | User match history |
| `GET /matches/:id` | Match details |
| `GET /champions` | All champions |

---

### LLM Worker Service

Starts ARQ worker for background LLM jobs.

```bash
make llm-dev
```

Or manually:

```bash
cd services/llm
python main.py
```

**Logs:**

```
{'level': 'INFO', 'message': 'llm_worker_startup', ...}
```

The worker listens for jobs on Redis. Currently no jobs are defined (Phase 4+).

---

### Redis

Required for both services (caching + job queue).

```bash
# Via Homebrew
redis-server

# Or via Docker
docker run -d -p 6379:6379 redis:7
```

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Install all packages in dev mode |
| `make api-dev` | Start API with hot reload |
| `make llm-dev` | Start LLM worker |
| `make db-up` | Start Postgres + Redis (Docker) |
| `make db-down` | Stop Docker services |
| `make db-migrate` | Apply Alembic migrations |
| `make db-revision` | Generate new migration |
| `make lint` | Run ruff linter |
| `make test` | Run pytest |

---

## Environment Variables

### API Service (`services/api/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/league_api` | Async Postgres connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `RIOT_API_KEY` | `replace-me` | Riot Games API key |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `SERVICE_NAME` | `league-api` | Service identifier in logs |
| `SQL_ECHO` | `false` | Echo SQL queries |

### LLM Service (`services/llm/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/league_api` | Async Postgres connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `OPENAI_API_KEY` | `your-openai-api-key` | OpenAI API key |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

---

## Documentation

- [Migration Plan — Backend](docs/MIGRATION_PLAN_BACKEND.md)
- [Migration Plan — Frontend](docs/MIGRATION_PLAN_FRONTEND.md)
- [Database Setup](docs/DATABASE_SETUP.md)
- [Phase 0 Endpoints](docs/PHASE0_ENDPOINTS.md)
