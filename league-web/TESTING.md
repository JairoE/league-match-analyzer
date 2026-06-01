# Testing

## Philosophy

100% test coverage is the key to great vibe coding. Tests let you move fast, trust your instincts, and ship with confidence — without them, vibe coding is just yolo coding. With tests, it's a superpower.

## Framework

**Playwright** v1.59.1 — end-to-end browser tests for the Next.js frontend.

## How to run

```bash
# Run all E2E tests (starts dev server automatically)
npm run test:e2e

# Watch mode with Playwright UI
npm run test:e2e:ui

# Run with visible browser (debug)
npm run test:e2e:headed

# Run a single file
npx playwright test e2e/match-card-chart.spec.ts
```

## Test layers

**E2E (`e2e/`)** — Browser-based tests against the running Next.js app. Each test mocks the FastAPI backend via `page.route()` so no backend is required.

- `matches-table-tabs.spec.ts` — Queue group tab filtering (S2 useTransition) + summary stats correctness (S5 matchDetails stability)
- `matches-table-pagination.spec.ts` — Pagination page changes via useTransition (S2)
- `match-card-chart.spec.ts` — ChampionKdaChart dynamic import: skeleton → chart (S1)
- `live-game-slot.spec.ts` — LiveGameSlot dynamic import + SSE state handling (S3)

## Fixtures and mocks

`e2e/fixtures/matches.ts` — Typed mock API responses: `PAGE_1_RESPONSE`, `PAGE_2_RESPONSE`, `ACCOUNT_RESPONSE`. The fixture covers 4 queue types (ranked solo, normal, ARAM, and a second ranked) to enable multi-tab tests.

`e2e/helpers.ts` — `mockRiotAccountRoutes(page)` wires up all API intercepts for the riot-account page.

## Conventions

- Tests are in `e2e/` at the top of `league-web/`
- File naming: `{feature}.spec.ts`
- Each `describe` block maps to one behavioral change (S1–S5) with a comment
- Use `page.route('**/{path}**', ...)` wildcards so tests work regardless of `NEXT_PUBLIC_API_BASE_URL`
- Always add `page.on("pageerror")` to JS-error-check tests
- When writing new functions, write a corresponding test
- When fixing a bug, write a regression test
- When adding a conditional, write tests for both paths
