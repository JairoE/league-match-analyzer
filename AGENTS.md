# AGENTS.md

## Cursor Cloud specific instructions

### Architecture

Monorepo with three main components:

| Service | Location | Tech | Dev Port |
|---------|----------|------|----------|
| **FastAPI Backend** | `services/api/` | Python 3.11+, FastAPI, SQLModel, Alembic | 8000 |
| **Next.js Frontend** | `league-web/` | Next.js 16, React 19, TypeScript | 3000 |
| **LLM Worker** (stub) | `services/llm/` | Python, ARQ | N/A |

Infrastructure (Docker Compose at `infra/compose/docker-compose.yml`): PostgreSQL 16 (pgvector) on port 5432, Redis 7 on port 6379.

### Common commands

See `Makefile` for the full list. Key commands:

- `make install` — install Python deps in editable mode (uses `.venv`)
- `make db-up` / `make db-down` — start/stop Postgres + Redis containers
- `make db-migrate` — run Alembic migrations
- `make api-dev` — start API with hot reload
- `make lint` / `make test` — ruff lint and pytest
- Frontend: `cd league-web && npm install && npm run dev`
- Frontend lint: `cd league-web && npm run lint`

### Startup sequence (after update script has run)

1. Start Docker daemon: `sudo dockerd &>/tmp/dockerd.log &` (wait ~3s)
2. Start infrastructure: `cd infra/compose && sudo docker compose up -d` (wait ~5s for health checks)
3. Run migrations: `cd services/api && ../../.venv/bin/alembic upgrade head`
4. Configure env: copy `services/api/.env.example` to `services/api/.env` if missing; set `RIOT_API_KEY` if available
5. Start API: `.venv/bin/uvicorn --app-dir services/api main:app --reload --host 0.0.0.0 --port 8000`
6. Start frontend: `cd league-web && npm run dev` (separate process)

### Non-obvious gotchas

- **Docker-in-Docker**: This cloud VM runs inside a Firecracker VM. Docker requires `fuse-overlayfs` storage driver and `iptables-legacy`. The update script handles Docker installation and configuration.
- **`python3.12-venv`**: The system Python 3.12 does not ship with `ensurepip`; the update script installs `python3.12-venv` to enable `python3 -m venv`.
- **Virtual environment path**: The Makefile hardcodes `.venv/bin/` paths for `uvicorn`, `alembic`, and `arq`. Always create the venv at `/workspace/.venv`.
- **Editable installs matter**: Always use `make install` (which uses `pip install -e`) rather than `pip install .`. ARQ and other tools resolve imports from the installed package, and a non-editable install goes stale as you edit code.
- **Riot API key**: Without a valid `RIOT_API_KEY` in `services/api/.env`, searches return errors. The rest of the app (health check, champion catalog, auth pages) works without it. Champions auto-seed from Data Dragon on API startup.
- **Pre-existing lint issues**: `make lint` (ruff) reports pre-existing import sorting and line-length warnings. These are in the existing codebase and not blocking.
- **Frontend `.env.local`**: Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` to point the frontend at the local API.
