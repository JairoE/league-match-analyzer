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
