# Backend Migration Plan (FastAPI + SQLModel + Postgres)

## Project Stack

- **Framework**: FastAPI (Async)
- **Database**: PostgreSQL with `pgvector` extension
- **ORM**: SQLModel (Pydantic + SQLAlchemy Core)
- **Caching/Queue**: Redis / ARQ
- **External API**: Riot Games API (handled via `cassiopeia` or custom async wrapper)

## Goals

- Replace Rails API with FastAPI + SQLModel.
- Keep endpoint behavior compatible with the existing frontend flow.
- Remove unsafe patterns (e.g., `eval`), store match data as JSONB.
- Add caching and rate limiting for Riot API calls.
 
 ---
 
 ## Phase 0 — Baseline
 
 - Document existing Rails endpoints and payloads:
  - `POST /users/sign_in`
  - `POST /users/sign_up`
  - `POST /fetch_user`
  - `GET /users/:id/fetch_rank`
  - `GET /users/:id/matches`
  - `GET /matches/:id`
  - `GET /champions`
  - `GET /champions/:id`
 - Save real example responses for validation.
- Phase 0 docs:
  - `docs/PHASE0_ENDPOINTS.md`
  - `docs/phase0-example-users-sign-in.json`
  - `docs/phase0-example-users-sign-up.json`
  - `docs/phase0-example-users-matches.json`
  - `docs/phase0-example-match.json`
  - `docs/phase0-example-champions.json`
 
 ---
 
## Phase 1 — Project Setup

- Create a `league-match-analyzer/services/api` FastAPI service with async endpoints.
- Create a `league-match-analyzer/services/llm` worker service for LLM jobs.
- Add a shared package at `league-match-analyzer/packages/shared`.
- Configure SQLModel with async SQLAlchemy engine + session in the API service.
- Enable Postgres extensions:
  - `pgvector`
- Add Redis + ARQ worker wiring for background jobs.
- Add request/response validation with Pydantic models.
- Add structured logging and request IDs.
- Add `pyproject.toml` for each service with pinned dependencies.
- Add `.env.example` files for `services/api` and `services/llm`.
- Initialize Alembic in `services/api/app/db/migrations/`.
- Document local database bootstrap:
  - Option A: `createdb league_api` (manual)
  - Option B: Docker init script via `docker-compose.yml`

---

## Phase 1.5 — Infrastructure and Tooling

- Create `infra/compose/docker-compose.yml`:
  - Postgres 16 with pgvector extension (use `pgvector/pgvector:pg16` image)
  - Redis 7
  - Volume mounts for data persistence
- Create Dockerfiles:
  - `services/api/Dockerfile`
  - `services/llm/Dockerfile`
- Add development scripts (Makefile or shell scripts):
  - `db-up` — start Postgres + Redis
  - `db-migrate` — run Alembic migrations
  - `api-dev` — start API with hot reload
  - `llm-dev` — start LLM worker
- Document `packages/shared` import strategy:
  - Use `pip install -e ../../packages/shared` from each service
  - Add shared package to each service's `pyproject.toml` as path dependency

---

## Phase 2 — Data Model
 
Create SQLModel models and Alembic migrations:
 
 ### User
 
- `id` UUID (PK)
- `summonerName` STRING (required)
- `riot_id` STRING (unique, required, `gameName#tagLine`)
- `puuid` STRING (unique, required)
- `profileIconId` INTEGER (nullable)
- `summonerLevel` INTEGER (nullable)
- `email` STRING (nullable)
 
 ### Match
 
- `id` UUID (PK)
- `game_id` STRING (unique)
- `game_info` JSONB (nullable, Riot match payload)
 
 ### UserMatch (join table)
 
 - `id` UUID (PK)
 - `userId` FK → User
 - `matchId` FK → Match
 
 ### Champion
 
- `id` UUID (PK)
- `champ_id` INTEGER (unique)
- `name` STRING
- `nickname` STRING (title)
- `image_url` STRING
 
 ### Associations

- User ⇄ Match via UserMatch (many-to-many)

### Migration Commands

- Generate migration: `alembic revision --autogenerate -m "description"`
- Apply migrations: `alembic upgrade head`
- Rollback: `alembic downgrade -1`

### Pydantic Schemas

Create request/response schemas alongside each model:

- `schemas/user.py` — `UserCreate`, `UserResponse`
- `schemas/match.py` — `MatchResponse`, `MatchListItem`
- `schemas/champion.py` — `ChampionResponse`

---

## Phase 3 — Endpoint Structure
 
Base: `/`
 
### Auth / User

`POST /users/sign_up`
 
 ```json
{"summonerName": "Faker#NA1", "email": "faker@example.com"}
 ```
 
`POST /users/sign_in`
 
 ```json
{"summonerName": "Faker#NA1", "email": "faker@example.com"}
 ```
 
 Response (both):
 
 ```json
 {
   "id": "uuid",
   "summonerName": "Faker",
  "riot_id": "Faker#NA1",
  "puuid": "riot-puuid",
  "profileIconId": 1234,
  "summonerLevel": 540,
  "email": "faker@example.com"
 }
 ```

`POST /fetch_user`

```json
{"summonerName": "Faker#NA1"}
```

Response: same as sign-up.

`GET /users/:id/fetch_rank`

Response: Riot ranked payload for the summoner.
 
 ### Matches
 
 `GET /users/:userId/matches`
 
 ```json
 [
   {
    "id": "uuid",
    "game_id": "123456789"
   }
 ]
 ```
 
 `GET /matches/:matchId`
 
 ```json
 {
  "metadata": {},
  "info": {}
 }
 ```
 
 ### Champions
 
 `GET /champions`
 
 ```json
 [
   {
    "champ_id": 266,
    "name": "Aatrox",
    "nickname": "the Darkin Blade",
    "image_url": "https://..."
   }
 ]
 ```
 
 `GET /champions/:champId`
 
 ```json
 {
  "champ_id": 266,
  "name": "Aatrox",
  "nickname": "the Darkin Blade",
  "image_url": "https://..."
 }
 ```
 
 ---
 
 ## Phase 4 — Riot API Integration
 
- Centralized Riot API client (async wrapper or `cassiopeia` adapter).
- Cache recent match lists and match details in Redis.
- Rate limit calls to comply with Riot API policy.
- Store API key in environment variables.
- Push fetch/aggregation work into ARQ jobs.
 
 ---
 
## Phase 5 — Cutover

- Run FastAPI alongside Rails API.
 - Verify endpoint parity and data shape.
 - Switch frontend base URL to new API.
 - Retire Rails.
 
 ---
 
## Target Layout

```
league-match-analyzer/
  Makefile
  services/
    api/
      pyproject.toml
      alembic.ini
      Dockerfile
      .env.example
      app/
        api/
          routers/
            auth.py
            users.py
            matches.py
            champions.py
        core/
          config.py
          logging.py
          middleware.py
        db/
          session.py
          init_db.py
          migrations/
            env.py
            versions/
        models/
          user.py
          match.py
          user_match.py
          champion.py
        schemas/
          user.py
          match.py
          champion.py
          views.py
        services/
          riot_client.py
          ddragon_client.py
          cache.py
          background_jobs.py
      main.py
    llm/
      pyproject.toml
      Dockerfile
      .env.example
      app/
        jobs/
        prompts/
        tools/
        workflows/
      main.py
  packages/
    shared/
      pyproject.toml
      __init__.py
      models/
      schemas/
      utils/
  infra/
    compose/
      docker-compose.yml
```
