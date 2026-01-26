# Migration Verification and Start Plan

## Verification Notes

### Backend Plan
- The API shapes align with the frontend flow and are consistent across endpoints.
- Edgecases to account for during implementation:
  - Prevent duplicate user-match links by enforcing a unique `(userId, matchId)` constraint.
  - Add indexes for `gameId`, `userId`, and `champId` to keep list endpoints fast.
  - Add pagination parameters to `GET /users/:userId/matches` to avoid unbounded lists.
  - Normalize "sign in" vs "sign up" by returning the same shape and status codes.
  - Handle Riot API failures with explicit retry/backoff and 429 detection.
  - Log request IDs and Riot API latency for observability.

### Frontend Plan
- The flow matches the backend API contract and keeps the UI simple.
- Edgecases to account for during implementation:
  - Add "use client" for forms and data-fetching components that use `useEffect`.
  - Store user session in session storage and restore it on refresh.
  - Add loading and error states for all requests (auth, matches, match detail).
  - Guard against missing champion data when mapping IDs to images.
  - Cache invalidation should be time-based and include a manual refresh path.
  - Preserve current auth endpoints (`/users/sign_in`, `/users/sign_up`) or add aliases.
  - Support rank fetch (`/users/:userId/fetch_rank`) for header stats.
  - Match detail responses must include v5 fields (`info`, `participants`, `teams`).
  - Champion fetch is per-card (`/champions/:championId`) rather than full list.

## Where to Begin

## Ordered Migration Sequence
1. Backend Phase 0 (only if baseline responses are missing): capture current API responses and fixtures to avoid drift.
2. Backend Phase 1 — project setup: app skeleton, env, and routing to unblock modeling.
3. Backend data layer: schema, constraints, indexes, and migrations for stable queries.
4. Backend external client: Riot API client with retries, backoff, and logging for observability.
5. Backend endpoints: auth, users/matches, matches, champions to stabilize the API contract.
6. Backend tests: contract, integration, DB constraints to lock behavior.
7. Frontend Phase 1 — project setup: routing, API base URL, shared client aligned to backend.
8. Frontend auth flow: sign-in/up and session storage restore to establish user state.
9. Frontend data flows: matches list, match detail, champions map for core UI.
10. Frontend UX states: loading/error, cache TTL, manual refresh for resilience.
11. Frontend tests: component, data fetch, E2E for end-to-end validation.

### Backend
- Start at **Phase 1 — Project Setup**.
- Reason: it unblocks data modeling, migrations, and the API client structure.
- Do Phase 0 only if baseline responses are not already captured.

### Frontend
- Start at **Phase 1 — Project Setup** after backend routing structure is defined.
- Reason: the shared API surface (`/v1`, auth, matches, champions) needs to be stable.
- If the backend API base URL is already known, you can start Phase 1 in parallel.
 - Include session storage hydration and match v5 normalization in initial scaffolding.

## Testing Plan

### Backend
- Contract tests for each endpoint:
  - `POST /auth/sign-in` and `POST /auth/sign-up` return identical shapes.
  - `GET /users/:userId/matches` supports pagination and stable ordering.
  - `GET /matches/:matchId` returns `matchInfo` JSONB with correct types.
  - `GET /champions` and `GET /champions/:champId` handle 404 correctly.
- Integration tests for Riot API client:
  - 429 handling, retries, and cache hits.
  - Timeout behavior and fallback responses.
- Database tests:
  - Unique constraints and indexes enforce expected behavior.

### Frontend
- Component tests for forms:
  - Validation for empty fields and error display on API failure.
  - Session storage restore on reload.
- Data fetch tests:
  - Cache TTL behavior and manual refresh.
  - Loading and error state rendering.
- End-to-end flow:
  - Sign up → fetch matches → open match detail.
  - Champions load before match cards render images.
