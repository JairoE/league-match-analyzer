# Ticket: Fix race in match/user upserts

## Problem

`_get_or_create_match` and `upsert_user_from_riot` use a non-atomic check-then-insert pattern. Under concurrent requests, both calls can insert and the second fails on unique constraints (`Match.game_id`, `User.puuid`, `User.riot_id`), returning 500 for valid requests.

## Evidence

- `services/api/app/services/match_sync.py`: `_get_or_create_match` selects then inserts.
- `services/api/app/services/riot_user_upsert.py`: `upsert_user_from_riot` selects then inserts.
- Unique constraints in `services/api/app/models/match.py` and `services/api/app/models/user.py`.

## Fix

- Use `INSERT ... ON CONFLICT DO NOTHING` (or `DO UPDATE`) and then `SELECT`.
- `Match`: upsert by `game_id`.
- `User`: upsert by `puuid` (and update `riot_id` + profile fields).
- Also harden `_ensure_user_match` with `ON CONFLICT DO NOTHING` on `(user_id, match_id)`.

## Why It Works

The insert becomes atomic under concurrency, removing the race window that triggers `IntegrityError`.

## Acceptance Criteria

- No 500s on concurrent sign-in or match sync.
- Idempotent results under concurrent requests.
- No duplicate rows for the same `game_id`, `puuid`, or `riot_id`.

## Test Plan

- Run two concurrent sign-in requests for the same Riot ID; both return 200, one user row exists.
- Run two concurrent match syncs for the same `match_id`; both return 200, one match row exists.
