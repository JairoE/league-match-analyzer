# Shared Riot Account Access (Post-Migration)

## Goal
Allow one signed-in user to view `user_matches` for other Riot accounts without duplicating Riot identity in `users`.

## Core Idea
Separate app users from Riot accounts, then grant access through a join table.

## Data Model
- `users`
  - App identity: email, auth metadata
- `riot_accounts`
  - Riot identity: `riot_id`, `puuid`, profile data
- `user_riot_accounts`
  - Access mapping: `user_id`, `riot_account_id`, `role` (optional)
- `user_matches`
  - Match data linked to `riot_account_id`

## Relationships
- `users` to `riot_accounts`: many-to-many via `user_riot_accounts`
- `riot_accounts` to `user_matches`: one-to-many

## Migration Outline
1. Create `riot_accounts` table with unique `riot_id` and `puuid`.
2. Create `user_riot_accounts` join table with unique `[user_id, riot_account_id]`.
3. Add `riot_account_id` to `user_matches`.
4. Backfill:
   - Map `users.riot_id` or `users.puuid` to `riot_accounts`.
   - Map existing `user_matches.user_id` to `user_matches.riot_account_id`.
5. Update code paths to use `riot_accounts`.
6. Optionally remove Riot fields from `users`.

## Access Rules
- A user can view matches for any `riot_account` they are linked to.
- Linking is explicit in `user_riot_accounts`.
- Authorization checks should join through `user_riot_accounts`.

## API Flow (High Level)
- Sign in:
  - Find or create `user` by email.
  - Find or create `riot_account` by `riot_id` or `puuid`.
  - Ensure `user_riot_accounts` entry.
- Fetch matches:
  - Verify access via `user_riot_accounts`.
  - Query `user_matches` by `riot_account_id`.

## Benefits
- Prevents duplicate Riot identities.
- Enables shared viewing without breaking uniqueness constraints.
- Clear ownership and permissions.
