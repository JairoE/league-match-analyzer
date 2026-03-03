# AGENTS.md

## Role

You are a full-stack engineer on this codebase. You write Python (FastAPI) on the backend and TypeScript (Next.js) on the frontend. You run tests and lint before finishing any task.

---

## Architecture

Monorepo with three main components:

| Service | Location | Tech | Dev Port |
|---------|----------|------|----------|
| **FastAPI Backend** | `services/api/` | Python 3.11+, FastAPI, SQLModel, SQLAlchemy 2.0 async, Pydantic v2, ARQ, pgvector | 8000 |
| **Next.js Frontend** | `league-web/` | Next.js 16, React 19, TypeScript 5 | 3000 |
| **LLM Worker** (stub) | `services/llm/` | Python, ARQ | N/A |

Infrastructure (`infra/compose/docker-compose.yml`): PostgreSQL 16 (pgvector) on port 5432, Redis 7 on port 6379.

Key directories:
- `services/api/app/api/routers/` — FastAPI route handlers
- `services/api/app/services/` — business logic
- `services/api/app/models/` — SQLModel ORM models
- `services/api/tests/` — pytest test suite
- `league-web/src/app/` — Next.js App Router pages
- `league-web/src/lib/errors/` — unified error handling (`types.ts`, `parse-api-error.ts`, `format-api-error.ts`, `error-store.tsx`)

---

## Commands

### Backend

```bash
make install          # install Python deps in editable mode (.venv)
make db-up            # start Postgres + Redis containers
make db-down          # stop containers
make db-migrate       # run Alembic migrations
make api-dev          # start API with hot reload (port 8000)
make lint             # ruff check services/api services/llm
make test             # pytest services/api services/llm

# Run a single test file
pytest services/api/tests/test_riot_api_client_retry.py

# Run a single test case
pytest services/api/tests/test_riot_api_client_retry.py::test_name
```

### Frontend

```bash
cd league-web && npm install    # install deps
cd league-web && npm run dev    # start dev server (port 3000)
cd league-web && npm run lint   # ESLint + Prettier check
cd league-web && npm run build  # production build
```

### Startup sequence

1. `sudo dockerd &>/tmp/dockerd.log &` (wait ~3s)
2. `cd infra/compose && sudo docker compose up -d` (wait ~5s)
3. `cd services/api && ../../.venv/bin/alembic upgrade head`
4. Copy `services/api/.env.example` → `services/api/.env`; set `RIOT_API_KEY` if available
5. `.venv/bin/uvicorn --app-dir services/api main:app --reload --host 0.0.0.0 --port 8000`
6. `cd league-web && npm run dev` (separate process)

---

## Code Style

### Python (backend)

- Line length: **100 characters** (ruff enforces: E, F, I, UP rules)
- Target: Python 3.11+; include `from __future__ import annotations` at top
- All functions must have type hints on parameters and return values
- Use `async def` / `await` throughout — no sync blocking calls
- Structured logging: `logger.info("event_name", extra={"key": value})`
- Docstrings: Google-style with Args/Returns sections

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.champion import Champion

logger = get_logger("league_api.services.champions")


async def list_champions(session: AsyncSession) -> list[Champion]:
    """List all champions in the catalog.

    Args:
        session: Async database session.

    Returns:
        Champion records ordered by name.
    """
    logger.info("list_champions_start")
    result = await session.execute(select(Champion).order_by(Champion.name))
    champions = list(result.scalars().all())
    logger.info("list_champions_done", extra={"count": len(champions)})
    return champions
```

### TypeScript (frontend)

- Print width: **80 characters** (Prettier enforces this)
- Double quotes, ES5 trailing commas, no bracket spacing: `{foo}` not `{ foo }`
- Always use `type` keyword for type-only imports
- `"use client"` at the top of any client component
- `export default function` for page/component exports

```typescript
"use client";

import {useCallback, useReducer} from "react";
import type {ApiError} from "./types";

type ErrorAction =
  | {type: "set"; scope: string; error: ApiError}
  | {type: "clear"; scope: string};

export function useErrorReducer() {
  const [state, dispatch] = useReducer(errorReducer, {});
  const clearError = useCallback(
    (scope: string) => dispatch({type: "clear", scope}),
    []
  );
  return {state, clearError};
}
```

---

## Git Workflow

**Branch naming:**

| Prefix | Use |
|--------|-----|
| `frontend-N-description` | Frontend feature/fix (e.g. `frontend-4-error-handling`) |
| `backend-N-description` | Backend feature/fix |
| `hot-patch-N` | Urgent hotfix |
| `docs-description` | Documentation only |

**Commit messages** — conventional commits, lowercase:

```
feat: add summoner search to home page
fix: clear stale auth error on form mount
refactor: extract error formatting to format-api-error.ts
style: update MatchCard layout spacing
docs: update request flow diagram
```

---

## Testing

- Backend tests live in `services/api/tests/`
- All tests are async; `asyncio_mode = "auto"` is set in `pyproject.toml` so no decorator needed
- Use `monkeypatch` for dependency injection, `caplog` for log assertions
- No frontend test suite currently exists

Before finishing any task, run `make test` and `make lint` (backend) and `npm run lint` (frontend). Fix any new failures — pre-existing ruff import-sort warnings are acceptable noise.

---

## Boundaries

✅ **Always do:**
- Run `make lint` and `make test` after backend changes
- Run `npm run lint` after frontend changes
- Use `make install` (editable install) — never `pip install .`
- Use the `useAppError(scope)` hook for all frontend error handling; never surface raw error objects to the UI
- Add type hints to all new Python functions

⚠️ **Ask before doing:**
- Creating or modifying Alembic migrations (`services/api/alembic/versions/`)
- Changing database models (`services/api/app/models/`)
- Adding new npm or Python packages
- Modifying Docker Compose or infrastructure config

🚫 **Never do:**
- Commit `.env` files or any file containing secrets / API keys
- Call `pip install .` (non-editable) — it goes stale as you edit code
- Add synchronous blocking I/O in FastAPI route handlers or services
- Bypass lint with `# noqa` or `// eslint-disable` without an explanatory comment

---

## Non-obvious Gotchas

- **Docker-in-Docker**: This cloud VM runs inside Firecracker. Docker requires `fuse-overlayfs` storage driver and `iptables-legacy`. The update script handles this.
- **`python3.12-venv`**: System Python doesn't ship `ensurepip`; the update script installs `python3.12-venv` to enable `python3 -m venv`.
- **Virtual environment path**: The Makefile hardcodes `.venv/bin/`. Always create the venv at `/workspace/.venv`.
- **Editable installs matter**: Always use `make install` (`pip install -e`). ARQ and other tools resolve imports from the installed package; a non-editable install goes stale as you edit code.
- **Riot API key**: Without `RIOT_API_KEY` in `services/api/.env`, search endpoints return errors. Health check, champion catalog, and auth pages work without it. Champions auto-seed from Data Dragon on startup.
- **Frontend env**: `league-web/.env.local` must contain `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`.
- **Pre-existing lint issues**: `make lint` reports pre-existing import-sort and line-length warnings. These are not blocking and not your responsibility to fix unless you touch that code.
