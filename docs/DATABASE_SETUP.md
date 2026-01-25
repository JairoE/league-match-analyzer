# Database Setup

Two options for bootstrapping the local PostgreSQL database.

---

## Option A: Manual Setup

Create the database manually using `createdb`:

```bash
createdb league_api
```

Connect and enable pgvector:

```bash
psql league_api -c "CREATE EXTENSION IF NOT EXISTS vector"
```

---

## Option B: Docker Compose

Use the docker-compose file in `infra/compose/`:

```bash
cd infra/compose
docker compose up -d
```

This starts:
- PostgreSQL 16 with pgvector (`localhost:5432`)
- Redis 7 (`localhost:6379`)

The init script automatically enables the `vector` extension.

---

## Environment Variables

Copy the example env file and adjust if needed:

```bash
cp services/api/.env.example services/api/.env
```

Default connection string:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/league_api
```

---

## Running Migrations

From `services/api/`:

```bash
# Generate a new migration
alembic revision --autogenerate -m "add user table"

# Apply all migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

---

## Verifying Setup

Start the API and hit the health endpoint:

```bash
cd services/api
uvicorn main:app --reload
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```
