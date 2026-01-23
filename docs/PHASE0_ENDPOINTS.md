# Phase 0 — Baseline endpoints

Base URL: `http://localhost:3001`

## Captured requests

- `POST /users/sign_up`
  - Request body: `summonerName=Doublelift`, `user[email]=doublelift+20260123b@example.com`
  - Response: `docs/phase0-example-users-sign-up.json` (200)
- `POST /users/sign_in`
  - Request body: `summonerName=Doublelift`, `email=doublelift+20260123b@example.com`
  - Response: `docs/phase0-example-users-sign-in.json` (200)
- `GET /users/2/matches`
  - Response: `docs/phase0-example-users-matches.json` (200)
- `GET /matches/1`
  - Response: `docs/phase0-example-match.json` (200)
- `GET /champions`
  - Response: `docs/phase0-example-champions.json` (200)
