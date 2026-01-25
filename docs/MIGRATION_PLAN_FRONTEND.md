# Frontend Migration Plan (Next.js + Fetch + Cache)

## Goals

- Replace the legacy React SPA with Next.js (App Router).
- Use native `fetch` plus a small cache utility for client-side data fetching.
- Preserve existing user flow: sign in/up → fetch matches → render cards.
- Keep API surface compatible with the new Fastify backend.

---

## Phase 0 — Baseline

- Capture current UI behavior and routes:
  - `/` (sign in / sign up)
  - `/home` (user dashboard with match cards)
- Save example API responses for:
  - `POST /auth/sign-in`
  - `POST /auth/sign-up`
  - `GET /users/:userId/matches`
  - `GET /matches/:matchId`
  - `GET /champions`

---

## Phase 1 — Project Setup

- Create `league-web` with Next.js + TypeScript.
- Add a small `fetch` wrapper and cache helper.
- Configure environment variables:
  - `NEXT_PUBLIC_API_BASE_URL`

---

## Phase 2 — App Pages

- Build the sign in / sign up page:
  - Input fields: summoner name, email.
  - Submit to `POST /auth/sign-in` or `POST /auth/sign-up`.
  - Store signed-in user in client state (or session storage).
- Build the home page:
  - Fetch match list with `fetch` + cache helper.
  - Render match cards with minimal information.
  - Fetch match detail on demand (detail route or lazy fetch).
- Build champion data usage:
  - Preload champions with cached fetch to map IDs to images/names.

---

## Phase 3 — API Wiring

- Replace all direct `fetch` calls with a shared fetch wrapper.
- Add centralized API helper:
  - Handles base URL.
  - Adds JSON headers.
  - Handles errors consistently.
  - Uses in-memory cache with TTL for read endpoints.

---

## Phase 4 — Cutover

- Point frontend to the new backend via `NEXT_PUBLIC_API_BASE_URL`.
- Validate:
  - Sign in/up works.
  - Matches list loads and cards render.
  - Match details show correctly.
  - Champion assets and data load.
- Remove Rails API dependencies.

---

## Target Layout

```
league-web/
  src/
    app/
      page.tsx
      home/
        page.tsx
    components/
      SignInForm.tsx
      SignUpForm.tsx
      MatchCard.tsx
    lib/
      api.ts
      cache.ts
```

---

## Fetch + Cache Usage Example

```tsx
const cache = new Map<string, {expiresAt: number; value: any}>();
const TTL_MS = 60_000;

export async function cachedFetch<T>(url: string): Promise<T> {
  const cached = cache.get(url);
  if (cached && cached.expiresAt > Date.now()) return cached.value as T;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  const data = (await res.json()) as T;
  cache.set(url, {expiresAt: Date.now() + TTL_MS, value: data});
  return data;
}

// usage inside a component:
// useEffect(() => { cachedFetch(`/v1/users/${userId}/matches`)... }, [userId])
```
