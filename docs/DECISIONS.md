# Decisions

Light ADR log for migration decisions.

## Log

- 2026-01-21: Initialized decisions log for backend migration.

## Entry Template

- YYYY-MM-DD: <Decision> because <Reason>. Alternatives: <A/B>.

## Entries

- 2026-01-21: Migrated Rails API to Fastify + Sequelize + Postgres because we need a lighter Node stack aligned with the new backend plan. Alternatives: stay on Rails, migrate to Express.

- 2026-01-26: Finish Migration to Python FastAPI. Created a ticket to address concurrency
