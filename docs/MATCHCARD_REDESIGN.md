# MatchCard — Remaining Work

## Source of Truth for Participant Data

To prevent drift between Riot payload capabilities, frontend typing, and UI
rollout, use `docs/RIOT_API_PARTICIPANT_FIELDS.md` as the canonical source of
truth for participant fields and asset mappings.

Required alignment points:

- `league-web/src/lib/types/match.ts` (`Participant` typing coverage)
- `league-web/src/components/MatchCard.tsx` (field consumption in UI)
- `league-web/src/lib/constants/ddragon.ts` (spell/rune mapping parity)

When adding or changing MatchCard data usage, update this doc set together:

1. `docs/RIOT_API_PARTICIPANT_FIELDS.md` (field contract and priority)
2. `league-web/src/lib/types/match.ts` (typed contract)
3. `docs/MATCHCARD_REDESIGN.md` and `docs/app_state.md` (implementation status)

All core redesign steps (types, DDragon constants, match utilities, MatchCard UI, CSS) are fully implemented. This document tracks the remaining deferred features.

---

## Step 1 — Live Game Integration

Show a live game indicator when the searched summoner is currently in-game.

**Riot Endpoint:** `GET /lol/spectator/v5/active-games/by-summoner/{encryptedSummonerId}`

- Poll every 30 seconds (not continuously streaming — Riot doesn't support SSE on spectator).
- Cache TTL: 30 seconds. 404 = not in game.
- Separate `LiveGameCard` component — do not modify `MatchCard` for this.
- Use a WebSocket or server-sent events for the frontend polling to avoid repeated HTTP calls.

**Effort:** ~8–10 hours (new polling architecture, LiveGameCard component, spectator data parsing). Remains lowest priority.
