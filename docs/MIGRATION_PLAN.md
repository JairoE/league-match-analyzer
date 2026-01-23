 # Backend Migration Plan (Fastify + Sequelize + Postgres)
 
 ## Goals
 
 - Replace Rails API with Fastify + Sequelize.
 - Keep endpoint behavior compatible with the existing frontend flow.
 - Remove unsafe patterns (e.g., `eval`), store match data as JSONB.
 - Add caching and rate limiting for Riot API calls.
 
 ---
 
 ## Phase 0 — Baseline
 
 - Document existing Rails endpoints and payloads:
   - `POST /users/sign_in`
   - `POST /users/sign_up`
   - `GET /users/:id/matches`
   - `GET /matches/:id`
   - `GET /champions`
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
 
 - Create a new Fastify server.
 - Add core plugins:
   - `@fastify/cors`
   - `@fastify/env`
 - Add Sequelize and configure Postgres.
 - Add request validation (Zod or Ajv).
 
 ---
 
 ## Phase 2 — Data Model
 
 Create Sequelize models and migrations:
 
 ### User
 
 - `id` UUID (PK)
 - `summonerName` STRING
 - `email` STRING
 - `accountId` STRING (nullable)
 - `puuid` STRING (nullable)
 
 ### Match
 
 - `id` UUID (PK)
 - `gameId` STRING (unique)
 - `queueId` INTEGER (nullable)
 - `seasonId` INTEGER (nullable)
 - `gameCreation` DATE (nullable)
 - `matchInfo` JSONB (nullable)
 
 ### UserMatch (join table)
 
 - `id` UUID (PK)
 - `userId` FK → User
 - `matchId` FK → Match
 
 ### Champion
 
 - `id` UUID (PK)
 - `champId` INTEGER (unique)
 - `name` STRING
 - `title` STRING
 - `imageUrl` STRING
 
 ### Associations
 
 - User ⇄ Match via UserMatch (many-to-many)
 
 ---
 
 ## Phase 3 — Endpoint Structure
 
 Base: `/v1`
 
 ### Auth / User
 
 `POST /auth/sign-up`
 
 ```json
 {"summonerName": "Faker", "email": "faker@example.com"}
 ```
 
 `POST /auth/sign-in`
 
 ```json
 {"summonerName": "Faker", "email": "faker@example.com"}
 ```
 
 Response (both):
 
 ```json
 {
   "id": "uuid",
   "summonerName": "Faker",
   "email": "faker@example.com",
   "accountId": "riot-account-id"
 }
 ```
 
 ### Matches
 
 `GET /users/:userId/matches`
 
 ```json
 [
   {
     "matchId": "uuid",
     "gameId": "123456789",
     "queueId": 420,
     "gameCreation": "2026-01-15T18:12:04.000Z"
   }
 ]
 ```
 
 `GET /matches/:matchId`
 
 ```json
 {
   "matchId": "uuid",
   "gameId": "123456789",
   "matchInfo": {"metadata": {}, "info": {}}
 }
 ```
 
 ### Champions
 
 `GET /champions`
 
 ```json
 [
   {
     "champId": 266,
     "name": "Aatrox",
     "title": "the Darkin Blade",
     "imageUrl": "https://..."
   }
 ]
 ```
 
 `GET /champions/:champId`
 
 ```json
 {
   "champId": 266,
   "name": "Aatrox",
   "title": "the Darkin Blade",
   "imageUrl": "https://..."
 }
 ```
 
 ---
 
 ## Phase 4 — Riot API Integration
 
 - Centralized Riot API client.
 - Cache recent match lists and match details.
 - Rate limit calls to comply with Riot API policy.
 - Store API key in environment variables.
 
 ---
 
 ## Phase 5 — Cutover
 
 - Run Fastify API alongside Rails API.
 - Verify endpoint parity and data shape.
 - Switch frontend base URL to new API.
 - Retire Rails.
 
 ---
 
 ## Target Layout
 
 ```
 league-api/
   src/
     routes/
       auth.js
       users.js
       matches.js
       champions.js
     models/
       User.js
       Match.js
       UserMatch.js
       Champion.js
       index.js
     services/
       riotClient.js
       cache.js
     plugins/
       db.js
       cors.js
     server.js
   .env
 ```
