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
