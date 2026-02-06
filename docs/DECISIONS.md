# Decisions

Light ADR log for migration decisions.

## Log

- 2026-01-21: Initialized decisions log for backend migration.

## Entry Template

- YYYY-MM-DD: <Decision> because <Reason>. Alternatives: <A/B>.

## Entries

- 2026-01-21: Migrated Rails API to Fastify + Sequelize + Postgres because we need a lighter Node stack aligned with the new backend plan. Alternatives: stay on Rails, migrate to Express.

- 2026-01-26: Finish Migration to Python FastAPI. Created a ticket to address concurrency
- 2026-01-26: Implemented Next.js Phase 2 UI (auth + home dashboard) with session storage, cached fetches, and per-card champion loads because the frontend needed parity with the legacy flow. Alternatives: keep the SPA, delay UI until backend is fully finalized.
- 2026-01-26: Standardized light/dark theming via CSS tokens to keep visual parity across macOS modes because the previous UI only looked correct in dark mode. Alternatives: hardcode light theme, add a manual theme toggle.
- 2026-01-26: Added frontend run instructions to the root README because developers need a single entry point for local setup. Alternatives: keep docs in `league-web/README.md` only.
- 2026-02-04: Analyzed MatchCard UI redesign requirements from screenshot. Documented three match states (Defeat/Remake/Victory as enum), complete data availability matrix, and modular component architecture because current implementation only shows basic stats. Key finding: 90% of needed data (items, spells, perks, champion level) is already in Riot API responses but TypeScript types are incomplete. Created comprehensive docs: MATCHCARD_REDESIGN_SUMMARY.md (overview), MATCHCARD_UI_REDESIGN.md (detailed analysis), RIOT_API_PARTICIPANT_FIELDS.md (100+ field reference), MATCHCARD_ACTION_PLAN.md (implementation steps). Alternatives: keep current simple card, add data incrementally without restructuring.
- 2026-02-05: Added `game_start_timestamp` (BigInteger, indexed, nullable) to the Match model and exposed it on `MatchResponse`/`MatchListItem` schemas because matches need chronological ordering and the frontend needs display timestamps. Extracted from `info.gameStartTimestamp` in the Riot payload during `fetch_match_detail`. Alternatives: parse timestamp from `game_id` string, rely solely on DB insertion order.
- 2026-02-05: Changed `list_matches_for_user` ordering from `UserMatch.id` (insertion order) to `Match.game_start_timestamp DESC NULLS LAST` because insertion order doesn't reflect actual play order when matches are backfilled out of sequence. Alternatives: order by `game_id` (lexicographic, fragile), add a `created_at` column.
- 2026-02-05: Added game start date/time display and game mode label to MatchCard because the card previously only showed match ID with no temporal context. Used `toLocaleDateString`/`toLocaleTimeString` with memoized derivation from the new `game_start_timestamp` field. Alternatives: use a date library (dayjs/date-fns), format server-side.
- 2026-02-06: Implemented lazy backfill of `game_start_timestamp` in `fetch_match_detail` because existing cached matches have the timestamp inside the JSONB `game_info` but a NULL column value. On cache hit with a NULL column, the timestamp is extracted from `info.gameStartTimestamp` and persisted. Alternatives: run a one-time migration script, add a separate backfill migration (also added for bulk coverage).
- 2026-02-06: Switched match detail loading from batch (`Promise.all` then single `setMatchDetails`) to progressive streaming because the previous approach blocked the UI until all 20 detail fetches completed. Now each fetch writes to a shared `useRef` buffer that flushes to state every 100ms, so cards render as data arrives. Alternatives: sequential fetching, server-side aggregation endpoint.
- 2026-02-06: Used `useRef` as a write buffer instead of calling `setMatchDetails` per fetch because batching avoids up to 20 rapid re-renders. The 100ms interval coalesces results into a few state updates. Alternatives: individual `setState` per response, `useReducer` with queued actions.
- 2026-02-06: Added `isActive` guard before writing to `pendingDetailsRef` because in-flight API calls from a cleaned-up effect could pollute the shared ref and cause stale match details to briefly appear after a refresh. The guard ensures only the current effect's responses reach state. Alternatives: use an `AbortController` per effect (heavier), scope the buffer inside `loadDetails` instead of a ref (loses cross-tick accumulation).
