# Railway API Service Deployment Guide

Final deployment configuration for `services/api` on Railway, based on monorepo setup with shared packages.

---

## Architecture Decisions

### 1. Configuration Management: Dashboard Over Files

**Decision:** Configure services via Railway Dashboard, NOT `railway.toml` files.

**Rationale:**

- Monorepo with multiple services (API + LLM)
- Single `railway.toml` at repo root causes conflicts between services
- Dashboard config provides per-service isolation
- Easier to manage different deployment strategies per service

**Trade-off:** Configuration not in version control, but clearer service separation.

---

## Railway Service Configuration

### Root Directory

**Setting:** `/` (monorepo root)

**Critical:** Must be root, not `services/api/`, because Dockerfile needs access to `packages/shared/`.

**Location:** Railway Dashboard → Service Settings → Root Directory

---

### Build Configuration

**Builder:** Dockerfile

**Dockerfile Path:** `services/api/Dockerfile`

**Watch Paths:** `services/api/**,packages/shared/**`

**Location:** Railway Dashboard → Settings → Build

**Why Watch Paths Matter:** Triggers rebuild only when API or shared package changes, not on LLM changes.

---

### Deploy Configuration

**Start Command:** `/workspace/services/api/entrypoint.sh`

**Health Check Path:** `/health`

**Health Check Timeout:** 100 seconds

**Restart Policy:** On failure

**Location:** Railway Dashboard → Settings → Deploy

---

## Database Setup: Supabase (Not Railway Postgres)

### Why Supabase?

**Railway's PostgreSQL does not include pgvector extension** by default. Extension files not available on Railway's managed Postgres instances.

**Supabase provides:**

- PostgreSQL with pgvector pre-installed
- Free tier suitable for development
- SQL editor for extension management
- Reliable connection pooling

### Connection Configuration

**Supabase Connection String Format:**

```
postgresql://postgres.[project-ref]:[password]@aws-0-us-west-1.pooler.supabase.com:6543/postgres
```

**Required Modification for FastAPI/SQLModel:**

```
postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-us-west-1.pooler.supabase.com:6543/postgres
```

**Key Change:** Add `+asyncpg` after `postgresql` for async driver support.

**Connection Mode:** Use Session mode (port 6543) for Railway, not Transaction mode.

### Enable pgvector

**In Supabase SQL Editor:**

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

**Verify:**

```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```

---

## Environment Variables

### Railway Variables Tab

Configure these in Railway Dashboard → Service → Variables:

```bash
# Database (Supabase connection string with +asyncpg)
DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[password]@[host]:6543/postgres

# Redis (Railway auto-generates when you add Redis service)
REDIS_URL=redis://[host]:[port]

# Riot API (get from developer.riotgames.com)
RIOT_API_KEY=RGAPI-your-production-key

# Logging
LOG_LEVEL=INFO
SERVICE_NAME=league-api
SQL_ECHO=false

# CORS (Frontend domain)
CORS_ALLOW_ORIGINS=https://your-frontend.vercel.app
```

**Note:** `PORT` is automatically injected by Railway - don't add it manually.

---

## Migration Strategy

### Automatic Migrations on Deploy

**Implementation:** `entrypoint.sh` runs migrations before starting API.

**Dockerfile:**

```dockerfile
COPY services/api/entrypoint.sh /workspace/services/api/entrypoint.sh
RUN chmod +x /workspace/services/api/entrypoint.sh
CMD ["/workspace/services/api/entrypoint.sh"]
```

**entrypoint.sh:**

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
cd /workspace/services/api
alembic upgrade head

echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### Idempotency

**Alembic migrations are idempotent:**

- No new migrations → Checks and exits instantly (< 1 second)
- New migrations → Applies only unapplied migrations
- Safe to run on every deployment

### Local Development

**Local `make api-dev` does NOT run migrations automatically.**

**Run manually when needed:**

```bash
make db-migrate
```

**Keeps local development fast, production deployments automated.**

---

## Port Configuration

### Railway's PORT Variable

**Railway injects `$PORT` environment variable** - typically 3000-9000 range.

**entrypoint.sh handles this:**

```bash
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

**Behavior:**

- Railway: Uses `$PORT` (dynamic)
- Local Docker: Defaults to 8000

**Do NOT hardcode port 8000** - Railway requires dynamic port binding.

---

## Deployment Workflow

### Initial Deployment

1. **Create Railway Project** from GitHub repo
2. **Configure Service Settings:**
   - Root Directory: `/`
   - Builder: Dockerfile
   - Dockerfile Path: `services/api/Dockerfile`
   - Start Command: `/workspace/services/api/entrypoint.sh`
3. **Add Supabase Database:**
   - Create Supabase project
   - Enable pgvector extension
   - Add `DATABASE_URL` to Railway variables (with `+asyncpg`)
4. **Add Redis:**
   - Railway: New → Database → Redis
   - Auto-generates `REDIS_URL`
5. **Add Environment Variables:**
   - `RIOT_API_KEY`
   - `LOG_LEVEL`
   - `CORS_ALLOW_ORIGINS`
6. **Deploy:**
   - Push to main branch
   - Railway auto-deploys

### Continuous Deployment

**Every merge to main:**

1. Railway detects changes (via watch paths)
2. Builds Docker image
3. Starts container
4. `entrypoint.sh` runs migrations
5. API starts and accepts traffic
6. Health check verifies `/health` endpoint

**No manual intervention required.**

---

## Verification Steps

### Post-Deployment Health Check

```bash
curl https://your-api.up.railway.app/health
# Expected: {"status": "ok"}
```

### Check Migrations in Logs

Look for in Railway logs:

```
Running database migrations...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
Starting FastAPI application...
INFO:     Started server process [1]
INFO:     Uvicorn running on http://0.0.0.0:XXXX
```

### Test Champion Seeding

```bash
curl https://your-api.up.railway.app/champions | jq 'length'
# Expected: 169 (or current champion count)
```

### Verify pgvector

**In Supabase SQL Editor:**

```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

---

## Common Issues & Solutions

### Issue: "Error creating build plan with Railpack"

**Cause:** Railway can't find Dockerfile.

**Solution:**

- Verify Root Directory is `/` (not `services/api/`)
- Verify Dockerfile Path is `services/api/Dockerfile`
- Check Settings → Build configuration

### Issue: "asyncpg connection error"

**Cause:** `DATABASE_URL` uses `postgresql://` instead of `postgresql+asyncpg://`.

**Solution:** Add `+asyncpg` to connection string in Railway variables.

### Issue: "Extension vector not available"

**Cause:** Using Railway's PostgreSQL (no pgvector support).

**Solution:** Switch to Supabase for PostgreSQL with pgvector.

### Issue: "Port binding error"

**Cause:** Hardcoded port 8000 in entrypoint.sh.

**Solution:** Use `${PORT:-8000}` to read Railway's dynamic port.

### Issue: "Cannot find packages/shared"

**Cause:** Root Directory not set to `/`.

**Solution:** Set Root Directory to monorepo root (`/`).

### Issue: "Migrations not running"

**Cause:** `startCommand` in railway.toml overriding Dockerfile CMD.

**Solution:** Remove railway.toml entirely, configure via dashboard.

---

## File Structure Reference

```
league-match-analyzer/
├── packages/
│   └── shared/              # Shared models/schemas
│       ├── __init__.py
│       └── pyproject.toml
├── services/
│   ├── api/
│   │   ├── app/             # FastAPI application
│   │   ├── Dockerfile       # Multi-stage build with shared package
│   │   ├── entrypoint.sh    # Migrations + start command
│   │   ├── alembic.ini      # Migration config
│   │   ├── main.py          # FastAPI entry point
│   │   └── pyproject.toml   # Dependencies (includes shared package)
│   └── llm/                 # LLM worker (separate Railway service)
└── docs/
    └── RAILWAY_API_DEPLOYMENT.md  # This file
```

---

## Future: LLM Service Deployment

**When deploying `services/llm` separately:**

1. **Create new Railway service** from same GitHub repo
2. **Configure independently:**
   - Root Directory: `/`
   - Dockerfile Path: `services/llm/Dockerfile`
   - Watch Paths: `services/llm/**,packages/shared/**`
3. **Share database/redis variables** between services
4. **No config file conflicts** - each service configured via dashboard

---

## Related Documentation

- [README.md](../README.md) - Project overview and local development
- [MIGRATION_PLAN_BACKEND.md](./MIGRATION_PLAN_BACKEND.md) - Backend migration strategy
- [DATABASE_SETUP.md](./DATABASE_SETUP.md) - Local database setup
- [SHARED_PACKAGE.md](./SHARED_PACKAGE.md) - Shared package architecture

---

## Summary: Deployment Checklist

- [ ] Root Directory set to `/` in Railway
- [ ] Dockerfile Path: `services/api/Dockerfile`
- [ ] Start Command: `/workspace/services/api/entrypoint.sh`
- [ ] Watch Paths: `services/api/**,packages/shared/**`
- [ ] Supabase PostgreSQL provisioned with pgvector
- [ ] DATABASE_URL uses `postgresql+asyncpg://` prefix
- [ ] Redis added and REDIS_URL auto-generated
- [ ] RIOT_API_KEY environment variable set
- [ ] CORS_ALLOW_ORIGINS configured for frontend
- [ ] Health check path: `/health`
- [ ] entrypoint.sh uses `${PORT:-8000}` for dynamic port
- [ ] No railway.toml file (configure via dashboard only)

**Deployment Status:** Ready for production after checklist completion.
