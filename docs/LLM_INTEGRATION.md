# LLM Pipeline Full-Stack Integration Plan

## Context

The 8-step LLM analysis pipeline (Ingest → Extract → Score → ΔW → Aggregate → Compare → Prompt LLM → Store) is fully implemented as backend infrastructure (160 tests pass), but has **zero API endpoints** and **zero frontend integration**. Users can only trigger it via CLI debug scripts. This plan connects it end-to-end so users can request and view AI coaching recommendations from the web UI.

---

## Design Decisions

1. **Trigger**: Replace `CompareButton` placeholder with an "AI Coach" button in SubHeader actions slot
2. **Champion selection**: Auto-detect most-played champion from loaded match history (V1 — no picker needed)
3. **Async flow**: POST enqueues ARQ job → frontend polls GET every 2s until result appears in DB (max 60s)
4. **Display**: Collapsible `AnalysisPanel` rendered between liveGame slot and warning in `MatchPageShell`
5. **Staleness**: POST short-circuits to cached result if analysis exists within last 24 hours

---

## Step 1: Backend — Response/Request Schemas

**New file:** `services/api/app/schemas/analysis.py`

- `AnalysisEnqueueRequest` — `{ champion_id: str, rank_tier: str | None }`
- `AnalysisEnqueueResponse` — `{ status: "enqueued" | "already_exists", analysis_id: UUID | None, champion_name: str }`
- `RecommendationResponse` — mirrors `Recommendation` from `llm_response_schema.py` (rank, title, current_choice, recommended_choice, delta_w_gap, explanation, category)
- `AnalysisResponse` — `{ id, riot_account_id, champion_name, rank_tier, match_count, recommendations[], overall_assessment, selection_bias_summary, model_name, created_at }`
  - `match_count` derived from `len(match_ids)`
  - `overall_assessment` and `selection_bias_summary` extracted from `output_payload`

---

## Step 2: Backend — Analysis Router

**New file:** `services/api/app/api/routers/analysis.py`

### `POST /riot-accounts/{riot_account_id}/analysis` → 202

1. Validate `riot_account_id` exists in DB
2. Resolve `champion_id` → `champion_name` via `get_champion_by_id` (existing)
3. Check for existing `LLMAnalysis` row for this account + champion created within 24h → return `"already_exists"` with `analysis_id`
4. Enqueue `llm_analysis_job` via `get_arq_pool()` with deterministic `_job_id = f"llm-{riot_account_id}-{champion_id}"` (prevents duplicates)
5. Return `"enqueued"`

### `GET /riot-accounts/{riot_account_id}/analysis?champion_name={name}` → 200

1. Query `LLMAnalysis` where `riot_account_id` and `champion_name` match, `ORDER BY created_at DESC LIMIT 1`
2. Return `AnalysisResponse` or `null` (frontend interprets null as "still processing")

**Reuse:** `get_session` dependency, `get_arq_pool()`, `HTTPException` with machine-readable detail codes

---

## Step 3: Register Router

**Edit:** `services/api/app/api/routers/__init__.py`
- Add `analysis` to imports
- Append `analysis.router` to `all_routers`

---

## Step 4: Frontend — Types

**New file:** `league-web/src/lib/types/analysis.ts`

```typescript
export type Recommendation = {
  rank: number;
  title: string;
  current_choice: string;
  recommended_choice: string;
  delta_w_gap: number;
  explanation: string;
  category: "item_purchase" | "objective_kill" | "selection_bias";
};

export type AnalysisResponse = {
  id: string;
  champion_name: string;
  rank_tier: string | null;
  match_count: number;
  recommendations: Recommendation[];
  overall_assessment: string | null;
  selection_bias_summary: string | null;
  model_name: string | null;
  created_at: string;
};

export type AnalysisEnqueueResponse = {
  status: "enqueued" | "already_exists";
  analysis_id: string | null;
  champion_name: string;
};
```

---

## Step 5: Frontend — Most-Played Champion Helper

**Edit:** `league-web/src/lib/match-utils.ts` (or new file if match-utils doesn't exist)

`getMostPlayedChampion(matches, matchDetails, puuid)` → `{ championId, championName, count } | null`

Iterates loaded match details, counts champion frequency for the target puuid, returns the top one.

---

## Step 6: Frontend — useAnalysis Hook

**New file:** `league-web/src/lib/hooks/useAnalysis.ts`

Following `useRank` pattern:

```typescript
export function useAnalysis(riotAccountId: string | null): {
  analysis: AnalysisResponse | null;
  isLoading: boolean;
  isPolling: boolean;
  error: string | null;
  requestAnalysis: (championId: number, championName: string) => Promise<void>;
  dismiss: () => void;
}
```

- `requestAnalysis()` → POST to enqueue, then poll GET every 2s (max 30 polls)
- If POST returns `"already_exists"` → fetch GET immediately, skip polling
- `dismiss()` → clear analysis state
- Error handling via `useAppError("analysis")`
- Timeout message: "Analysis is taking longer than expected. Try again later."

---

## Step 7: Frontend — AnalysisPanel Component

**New files:** `league-web/src/components/AnalysisPanel/AnalysisPanel.tsx` + `.module.css`

Structure:
- Header row: "AI Coach: {championName}" + rank tier badge + dismiss (X) button
- Overall assessment paragraph
- 3 recommendation cards:
  - Rank badge (#1, #2, #3)
  - Title
  - "Currently: {current_choice} → Recommended: {recommended_choice}"
  - ΔW gap indicator (formatted as percentage)
  - Category label (item / objective / bias)
  - Explanation text
- Selection bias summary (collapsible, if present)

Styled using existing CSS variables from the project.

---

## Step 8: Frontend — AnalysisButton Component

**New file:** `league-web/src/components/AnalysisButton/AnalysisButton.tsx` + `.module.css`

Replaces `CompareButton`. Goes in SubHeader `actions` slot.

- Default: "AI Coach" button (or "AI Coach: {championName}" if champion known)
- Loading: "Analyzing..." with spinner
- After result: toggles panel visibility
- Disabled when no `riotAccountId` or no champion data

---

## Step 9: Wire into MatchPageShell

**Edit:** `league-web/src/components/MatchPageShell/MatchPageShell.tsx`

Add optional `analysisPanel?: ReactNode` prop, rendered between `{liveGame}` and `{warning}`.

---

## Step 10: Wire into Riot Account Page

**Edit:** `league-web/src/app/riot-account/[riotId]/page.tsx`

1. Remove `CompareButton` import
2. Add `useAnalysis(account?.id)` hook
3. Compute `mostPlayedChampion` from `matches` + `matchDetails` + `account?.puuid`
4. Render `AnalysisButton` in SubHeader actions
5. Render `AnalysisPanel` via `analysisPanel` prop on `MatchPageShell`

**Delete:** `league-web/src/app/riot-account/[riotId]/CompareButton.tsx`

---

## Step 11: Wire into Home Page

**Edit:** `league-web/src/app/home/page.tsx`

Same pattern as step 10, using `riotAccountId` from the authenticated user session.

---

## Step 12: Backend Tests

**New file:** `services/api/tests/test_analysis_router.py`

- POST with valid champion → 202 enqueued
- POST with existing recent analysis → 202 already_exists
- POST with invalid riot_account_id → 404
- POST with invalid champion_id → 404
- GET with existing analysis → returns AnalysisResponse
- GET with no analysis → returns null
- Deterministic job_id prevents duplicate enqueue

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| No scored matches | Job returns `no_data` status, no row persisted. Polling times out → "Not enough data for analysis." |
| No OpenAI key | Job returns `skipped`. Same timeout → "Analysis unavailable." |
| Job already running | Deterministic `_job_id` prevents duplicate. POST returns 202, polling continues. |
| Parse failure | Job stores raw response in `output_payload`, `recommendations = []`. GET returns result with empty recommendations → UI shows assessment only. |
| 24h cache hit | POST returns `already_exists` → GET loads immediately, no polling. |

---

## Verification

1. `make test` — all existing 160 tests pass + new router tests
2. `make lint` — clean
3. `cd league-web && npm run lint` — clean
4. Manual E2E: start `make api-dev` + `make worker-dev` + `cd league-web && npm run dev`
   - Navigate to `/riot-account/{id}` with a player who has scored matches
   - Click "AI Coach" button
   - Observe polling → panel appears with 3 recommendations
   - Dismiss and re-click → cached result loads instantly

---

## Files Summary

| Action | File |
|--------|------|
| **Create** | `services/api/app/schemas/analysis.py` |
| **Create** | `services/api/app/api/routers/analysis.py` |
| **Edit** | `services/api/app/api/routers/__init__.py` |
| **Create** | `league-web/src/lib/types/analysis.ts` |
| **Create or Edit** | `league-web/src/lib/match-utils.ts` |
| **Create** | `league-web/src/lib/hooks/useAnalysis.ts` |
| **Create** | `league-web/src/components/AnalysisPanel/AnalysisPanel.tsx` + `.module.css` |
| **Create** | `league-web/src/components/AnalysisButton/AnalysisButton.tsx` + `.module.css` |
| **Edit** | `league-web/src/components/MatchPageShell/MatchPageShell.tsx` |
| **Edit** | `league-web/src/app/riot-account/[riotId]/page.tsx` |
| **Delete** | `league-web/src/app/riot-account/[riotId]/CompareButton.tsx` |
| **Edit** | `league-web/src/app/home/page.tsx` |
| **Create** | `services/api/tests/test_analysis_router.py` |
