# App State

**Last Updated:** 2026-08-05
**Branch:** `fix/ai-coach-picker-and-recent-match-scoring`
**Status:** FIXES COMPLETE AND GREEN — but NOT re-reviewed, NOT merged, NOT
pushed (no upstream, no PR). Adversarial review confirmed 10 findings (6 medium,
4 low, 0 critical) against 14 refuted; 8 were fixed and 2 deferred deliberately.
Verification: backend 257 passed + ruff clean; frontend lint 0 errors (1
pre-existing warning in untouched `AuthForm.tsx`) + 39/39 Playwright E2E passed.
The fixes are themselves unreviewed code and the original review loop never
converged — see Blockers.

## Current Phase

**Post-review fixes on `fix/ai-coach-picker-and-recent-match-scoring` (2026-08-05).**

The branch (3 commits ahead of `main`, 0 behind) extracts+scores newly-ingested
matches so recent champions become AI Coach-eligible, moves the champion picker
into `AiCoachCard`, and re-polls eligibility after a refresh.

### Adversarial review result (2026-08-05)

10 confirmed / 14 refuted. **Coverage is incomplete** — finder rounds 1–3 ran
(11 → 8 → 5 fresh findings, still confirming 2 in round 3), but rounds 4–5 died
on a monthly spend limit and the loop counted those empty results as "dry", so
the run terminated on the limit rather than on exhausting the search.

Headline: the branch's own claim was only partly delivered. The re-poll never
armed on a first search (the case where the picker is *guaranteed* to start
empty), and `search.py:134` — the one ingest site the AI Coach page's Refresh
button actually routes through — had zero test coverage.

### Fixes landed and diff-reviewed

- **Frontend hooks.** `useAnalysisChampions.ts`: re-poll now arms on
  `accountBecameKnown || refreshedSameAccount` (was refresh-only, so first
  search never re-polled); the `catch` path now reschedules (a single transient
  502 previously ended the chain permanently); the stop condition is a
  set-difference on `champion_id` rather than `next.length > baselineCount`, so
  a same-length reorder is no longer mistaken for "nothing new".
  `useAiCoach.ts`: `handleAnalysisClick` now pins
  `setPickedChampionId(selectedChampion.champion_id)` before requesting, so a
  re-poll reorder can no longer silently discard an open/in-flight analysis.
- **Backend coverage.** New `services/api/tests/test_search_router_refresh.py`
  covers the refresh and `after > 0` ("see more") branches by task identity
  (not by patching the enqueue helpers). Mutation-checked: commenting out
  `search.py:134` fails 2 of 3 tests; restoring passes all 3.
- **Backend service.** `enqueue_timeline_extraction.py`: the DB block and
  `get_arq_pool()` are now guarded (an unguarded raise propagated out of the
  ASGI app after the response body was flushed, tearing down the keepalive
  connection and skipping tasks queued behind it); `enqueue_job`'s return is
  captured so ARQ dedupe rejections count as `deduped` rather than inflating
  `enqueued`; the `game_info` gate is now
  `isnot(None) AND cast(..., String) != "null"`, matching `riot_sync.py` —
  JSONB persists Python `None` as JSON `'null'`, not SQL NULL.
  `background_jobs.py`: `extract_match_timeline_job` gets `keep_result=10`,
  because it returns error *dicts* rather than raising, so a failed extraction
  was an ARQ success whose retained result blocked re-enqueue for a full hour.
- **Caption.** `AiCoachCard` claimed "full ranked history" but no queue filter
  exists anywhere in the pipeline; corrected to "full scored match history".
- **E2E regressions.** Three new specs in `analysis-flow.spec.ts` (first-search
  re-poll, transient-failure recovery, analysis surviving a reorder), each
  verified non-vacuous by running them against a worktree at `33cfcc5` where
  all three fail.

### Verified during review (no fix needed)

`useAppError` is referentially stable — provider callbacks are
`useCallback(..., [])` and the scoped wrappers depend only on those plus a
constant `scope`. Unrelated re-renders do not re-run the effect, so pending
re-poll timers survive.

### Deferred deliberately

- **Timeline-cache race** (low/efficiency): extraction jobs are enqueued
  alongside `fetch_timeline_cache_job` for the same ids and mostly lose the
  race, re-fetching ~1MB timelines themselves (~61 Riot calls per refresh vs
  ~41). Needs a scheduling design call — return enqueued ids so they are
  excluded from the cache-warm job, `_defer_by` the extraction jobs, or a
  per-match Redis `SET NX` lock. Not a mechanical edit.
- **"See more" re-poll**: `loadMoreMatches` never bumps `refreshIndex`, so the
  `after > 0` ingest branch gets no re-poll. Needs an `ingestIndex` threaded
  through `useMatchList` → both pages. Lower value (nobody is waiting on a
  champion there).

### Prior phase — agent workflow improvements (`agent-workflow-improvements`, 2026-07-22)

Two features shipped on that branch:

- **Auto-chain scoring.** `extract_match_timeline_job` now enqueues
  `score_actions_job` (`_job_id=score-actions:auto:{match_id}`) as its final
  step, *after* `session.commit()`, so newly ingested matches get `delta_w`
  populated without the manual `make score-account-matches` backfill. Best-effort:
  missing Redis context and enqueue failures are logged, metered
  (`jobs.score_actions.enqueue_failed{reason=no_redis|enqueue_error}`), and
  swallowed so they never fail extraction. Auto id is namespaced apart from the
  manual script id (`score-actions:v0:{id}`) so a manual retry is never deduped
  against a no-model auto-skip. Older matches and no-model skips still use the
  manual backfill.
- **`get_champion_insights` chat tool.** When a player has no personal data on a
  champion (or asks generally / how to improve), the chatbot can pull coaching
  insights from AI Coach analyses of *other* similar players via RAG (embed →
  cosine KNN → trimmed few-shot). Provenance is enforced in both the tool result
  and the system prompt so the model never presents others' data as the player's
  own. All failure branches (RAG disabled / no key / unknown champion / embed
  failure / no examples) return graceful messages.

Also on this branch: `docs/app_state.md` was split — historical changelog moved to
`docs/app_state_archive.md`, leaving this file current-state only; and
`docs/LLM_DATA_PIPELINE.md` Step 4 updated to document the auto-chain.

### Review fix applied (2026-07-22)

- Enqueue exception path in `_enqueue_scoring_job` now emits
  `jobs.score_actions.enqueue_failed{reason=enqueue_error}` for observability
  parity with the no-redis path; `test_enqueue_scoring_job_swallows_enqueue_errors`
  asserts it fires.

### Prior phase — durable cross-champion AI Coach (`codex/durable-ai-coach`, 2026-07-14)

The champion picker comes from full-history, account-specific scored actions
rather than paginated match details. Empty historical rank buckets fall back to
champion-only aggregation while live rank remains coaching context, and persisted
match ids are scoped to the selected champion. The eligibility API reports scored
match/action and corpus counts.

### RAG architecture (complete)

- **Step 6.5**: embed query → cosine KNN in pgvector → inject top-3 as `## Reference Examples` in user prompt
- **Post-persist**: generate + store embedding on new `LLMAnalysis` rows so corpus grows automatically
- **Cold start**: empty corpus returns `[]`, pipeline never aborts; RAG activates meaningfully at ~5+ rows per champion, quality improves at ~50+ per champion/rank bucket
- **Seeding**: `make seed-rag-corpus ARGS='--from-file seeding_list.txt'` or `--entry "name#NA1:157"`
- **Corpus now**: 38 embedded rows, including 6 Alistar rows after the live result

### verify-changes findings (2026-06-01, RAG branch — all non-blocking)

- **WARN** — `20260601_0004_rag_embedding_column.py:16-26`: dead `try/except ImportError` fallback `Vector` type. `pgvector` is a hard runtime dep; shim is dead code. Import `Vector` directly; delete ~11 lines.
- **NOTE** — `jobs/llm_analysis.py`: `OpenAIClient` instantiated 3×, `comparison.to_dict()` called 3×, `build_embedding_text(...)` computed twice with identical args. Build once and reuse.
- **NOTE** — HNSW index (`vector_cosine_ops`, m=16/ef=64) is premature-but-harmless at current corpus size.
- **NOTE** — `rag_enabled=True` by default means 2 embedding calls per job before the corpus is seeded.

## Blockers

- **Adversarial review coverage is incomplete.** Rounds 4–5 of the find→refute
  loop never ran (monthly spend limit), and the loop miscounted those failures
  as "dry" rounds. Round 3 was still confirming findings, so the branch has NOT
  been searched to exhaustion. Re-run before merge.
- **The fixes are unreviewed code.** Eight findings were fixed across 6 files
  this session and have not been through a review pass of their own.
- No code blockers. The in-app browser controller rejected a localhost reload,
  so the final manual click was not performed. The equivalent live POST/poll
  path, persisted response, and browser E2E flow all pass.
- Known flaky test (pre-existing, not this branch): `live-game-slot.spec.ts` "Retry button triggers a new SSE connection" occasionally fails in full-suite runs; passes in isolation and on re-run.
- Operational note: Railway dashboard must run `release.sh` as the API service's pre-deploy/release command (unchanged from 2026-03-04).

### Security posture (accepted for now, reviewed 2026-07-12)

The `POST /riot-accounts/{id}/analysis` and `POST /riot-accounts/{id}/chat/stream`
endpoints spend OpenAI tokens with **no authentication or per-IP rate limiting**, consistent
with every other route in this portfolio app. Guards in place: chat caps concurrency at 4
streams (`MAX_CONCURRENT_CHAT_STREAMS`, best-effort 429 `chat_busy`); analysis dedupes per
`(account, champion, day)` via the deterministic ARQ job id; per-turn token caps
(≤3 tool rounds, 12-message window, `max_tokens=700`, gpt-4o-mini). Accepted as-is —
iterating champions/accounts remains an unbounded token-spend path. If this ever goes properly
public, add per-IP rate limiting and a spend guard, and make the chat semaphore acquire
non-blocking so the 429 fails fast under a check-then-acquire race.

## Next Steps

1. Commit the fixes as separate conventional commits (`fix:` for the four
   backend fixes, `fix:` for the hook fixes, `test:` for the new coverage,
   `fix:` for the caption).
2. **Re-run `/adversarial-review` on the fixes** — they are unreviewed code,
   and the original loop never converged (see Blockers). Pin finder agents to
   `model: 'sonnet'`, `effort: 'medium'` per the routing rule in
   `~/.claude/CLAUDE.md`; the first run left them unpinned on the session model
   and burned ~2.5M tokens across 39 agents.
3. Decide the two deferred items (timeline-cache race; "see more" re-poll) —
   fix or file as follow-up tickets.
4. Push `fix/ai-coach-picker-and-recent-match-scoring` and open a PR targeting
   `main`. No upstream is configured yet.

### Open product question

The AI Coach caption claimed "full ranked history" but no queue filter exists
anywhere in the pipeline. This session took the proportionate fix (correct the
copy to match behavior). If ranked-only was the actual product intent, the real
fix is a backend queue filter — `&type=ranked`/`queue=420` in
`fetch_match_ids_by_puuid`, plus queueId predicates in `analysis_champions.py`
and `action_aggregation.py` — which is a behavioral change that would also
shrink the eligible-champion list.

## Recent Changes (2026-07-13 — durable cross-champion AI Coach fix)

### What changed

- Added shared rank fallback for the worker and debug script. An empty requested
  rank bucket retries without rank filtering; fallback use is logged and metered.
- Scoped analysis `match_ids` to the account participant and selected champion,
  applying historical rank only when rank-specific aggregation succeeded.
- Added `GET /riot-accounts/{id}/analysis/champions`, backed by full-history
  account-specific scored actions and embedded corpus counts.
- Replaced loaded-page champion inference with the eligibility endpoint on both
  match pages. Loading/empty states disable AI Coach, failures use
  `useAppError`, and switching clears stale analysis panels.
- Preserved `keep_result=10` and added direct regression coverage.

### Verification

- `make test`: 232 passed, 2 skipped. `make lint`: clean. Frontend lint: no
  errors (one pre-existing `AuthForm` hook warning).
- Playwright: 34/34 after merging `origin/main`, including 9/9 AI Coach tests
  with Alistar id 12, all three seeded champion choices, unscored-champion
  exclusion, stale-panel clearing, formatted eligibility errors, empty
  eligibility, retries, and account switching.
- Live BRONZE debug: rank fallback produced 5 aggregates, 1 comparison group,
  and 3 opportunities.
- Live eligibility: Lux 15, Alistar 12, Blitzcrank 6, Vel'Koz 1 scored matches;
  Alistar had 35 scored actions and 5 pre-existing embedded corpus examples.
- Live worktree worker persisted analysis `979cb40b-cf2b-4ddc-8bc4-bd000dced397`
  with rank context BRONZE and 3 recommendations. Direct DB verification found
  12 persisted matches, all 12 Alistar, all 12 with scored account-player actions.
- Manual in-app click remains unperformed because the browser controller blocked
  localhost navigation; the running worktree services and tab are available for
  a user-driven visual check.

## Recent Changes (2026-07-12 — Claude Code workflow audit + tooling fixes; no app code changes)

- **What changed:** No application code, tests, or product docs. Session audited recent Claude Code transcripts across projects and applied workflow fixes:
  - `.claude/hooks/end-checklist.sh` hardened (here and in content-creator-video): fails open when `docs/app_state.md` is absent at the resolved cwd (this pathspec bug made the hook block every Stop regardless of state), and allows Stop on read-only sessions (fully clean tree). Commit-recency window retained.
  - `.claude/commands/{SUMMARIZE,GENERATE_PR_DESCRIPTION,UPDATE_APP_STATE,UPDATE_DOCS}.md` gained `model: sonnet` frontmatter (cheaper model for mechanical commands; also applied in content-creator-video).
  - `AGENTS.md` gained a shell-cwd gotcha and a "Session checkpointing" section (checkpoint via /UPDATE_APP_STATE + fresh session instead of auto-compaction).
  - Consolidated permission allow-lists staged for user review in the session scratchpad (`proposed-global-settings.json`, `proposed-project-settings.local.json`) — direct settings.json writes are permission-gated.
- **Current phase:** unchanged — `chat` branch stable, ready for PR.
- **Blockers:** none new.
- **Next steps:** unchanged; plus: user to review/apply the staged permission consolidations.

## Recent Changes (2026-07-13 — champion picker, retry fix, corpus seeded, `chat`)

### What changed

- **Diagnosis of the "AI Coach: Blitzcrank error" on `jairopractor#NA1`** — NOT rank-related
  (the same BRONZE account already had a working Lux analysis; the dry-run pipeline built a
  full Blitzcrank comparison). Root cause: one transient OpenAI failure (`llm_error`, no row
  persisted) whose day-bucketed deterministic job id stayed reserved for ARQ's default 1h
  `keep_result`, silently swallowing every retry into a 60s polling timeout.
- **`services/api/app/services/background_jobs.py`** (`83520f6`): register the job as
  `func(llm_analysis_job, keep_result=10)` — the id frees ~10s after completion so retries
  work, while in-flight dedup of concurrent clicks is preserved. **Worker restart required**
  to pick this up (`make worker-dev`).
- **Champion picker** (`b040d60`): `AnalysisButton` now renders a `<select>` of all champions
  from loaded match history (via new `getPlayedChampions()` in `match-utils.ts`, most-played
  first, replacing `getMostPlayedChampion`). `useAnalysis` tracks `requestedChampionId` and
  clears stale panels when a new request starts; the button toggles "Hide" only when the open
  panel matches the selected champion. Wired on both pages; chat `championFocus` follows the
  selection. New E2E: pick a non-most-played champion, analyze, switch back (29 total).
- **Corpus seeded (operational)**: 36 embedded `llm_analysis` rows — 5 distinct accounts each
  for Brand, Blitzcrank, Zac, Teemo, Alistar, Lux, Vel'Koz (+1 Jhin). RAG retrieval now
  returns real few-shot examples for those champions.
- **Verified live**: POST/GET `/riot-accounts/{jairopractor}/analysis` for champion 53 and 99
  both return `already_exists` → full panels (3 recommendations, 38 matches each).

### Tests / lint

Backend 223 passed / lint clean; frontend lint + build clean; Playwright 29/29.
(Superseded by the 2026-07-13 ship pass above: 224 backend, 32/32 Playwright.)

### Blockers

Running ARQ worker still has the old 1h `keep_result` until restarted.

### Next steps

Restart worker; finish the smoke-test walkthrough (chat streaming on a seeded account); open PR.

## Recent Changes (2026-07-13 — simplify + ship pass, PR #47 finalized, `chat`)

### What changed

Ran `/code-simplify` then `/ship` (parallel code-reviewer + security-auditor + test-engineer)
over the branch. Verdict: **GO** — zero Critical/High findings across all three reports.
Commits `b1962d5`…`1cb9a3e`, all pushed to PR #47 (title/body refreshed to match the shipped
champion-picker behavior):

- **Simplify** (`b1962d5`): extracted `league-web/src/lib/hooks/useAiCoach.ts` — both match
  pages carried identical ~40-line AI Coach wiring (picker state, most-played fallback,
  panel-open invariant, click handler). Same pattern as `useMatchList`/`useRank`. Only
  substantive finding of a full scan of the feature diff; the rest was already clean.
- **Test infra** (`10229d8`): `playwright.config.ts` port is overridable via `E2E_PORT`.
  Found the hard way: `reuseExistingServer` silently tested a **foreign dev server** on :3000
  belonging to the `codex/durable-ai-coach` worktree (`/private/tmp/league-match-analyzer-
durable-ai-coach`) — 4 bogus failures. Local runs: `E2E_PORT=3100 npm run test:e2e`.
- **Review fixes** (`e5a287b`, `27698c2`): registration test pins `llm_analysis_job` name +
  `keep_result_s=10` (reverting the fix can no longer pass silently); stale job-id comment in
  `analysis.py` refreshed; `useAiCoach` now resets a picked champion on account change
  (carried over across client-side navigation before).
- **Security hardening** (`21fb56c`, from audit — both Low/Info): `champion_focus` gets a
  champion-name character allowlist (blocks newline directive smuggling into the system
  prompt); `rank_tier` bounded at 32 chars. Audit confirmed: tools strictly account-scoped,
  no SSE frame injection, no SQLi, no secret leakage, XSS-safe rendering.
- **E2E coverage** (`1cb9a3e`, from test-engineer gaps): error path + retry, empty champion
  list (picker hidden/button disabled), account switch mid-poll abandons the polling loop
  (helpers now yield a distinct account id per riot id), picker locked while analyzing.

### Tests / lint

Backend **224** passed / lint clean; frontend lint + build clean; Playwright **32/32**
(known pre-existing live-game flake passes in isolation).

### Blockers

None new. Running ARQ worker still needs a restart for `keep_result=10` (any deploy does it).

### Next steps

Merge PR #47; finish chat-streaming smoke walkthrough in the browser; `make evals`; decide
whether to reconcile with the parallel `codex/durable-ai-coach` branch (its picker sources
from account eligibility instead of loaded match history).

## Recent Changes (2026-07-12 — five-axis code review of AI Coach + chat, `chat`)

### What changed

Ran the `code-review-and-quality` skill across correctness/readability/architecture/security/
performance, using a second independent reviewer subagent for fresh eyes. No Critical findings.
Verified correct: chat tool data-scoping (no cross-player leak — every executor filters by
`account.id`/`account.puuid`), the OpenAI tool-calling protocol, SQL parameterization, no
secrets/PII in logs, analysis polling races, SSE disconnect/session handling. Fixes applied
(commits `d8f8652`, `135bcf8`):

- **Bug — empty assistant turn 422-bricked the conversation** (`league-web/src/lib/hooks/useChat.ts`). An empty completion (`done` with no tokens) left an assistant bubble with `content: ""`; sending it back on the next turn failed backend validation (`ChatMessage.content` `min_length=1`) → 422 → every later message failed, unrecoverable without an account switch. Now strips empty assistant messages from outgoing history and replaces a blank completed bubble with a fallback. Added E2E regression `chat-flow.spec.ts` "empty completion recovers…". Also capped the chat input at the backend's 4000-char limit.
- **Perf — item-name-map cache** (`services/api/app/jobs/llm_analysis.py`). `load_item_name_map()` now caches Data Dragon's ~1MB `item.json` in-process for 6h (falls back to last good cache on failure), so the analysis job and the chat `get_action_stats` tool stop re-fetching it per call.
- **Docs — security posture** recorded in the Blockers section: the analysis + chat endpoints spend OpenAI tokens with no auth/rate-limiting (accepted for this portfolio app), with the follow-ups to add if they go public.

Deferred per owner decision: no per-IP rate limiting / spend guard (accepted as-is); no
frontend unit-test runner for the SSE parser + hooks (kept E2E-only coverage). Noted-but-not-
actioned nits: semaphore fast-429 raciness (concurrency still correctly capped at 4),
interim-round tokens dropped from model context (rare), `champion_focus` raw interpolation
(64-char, own-data-only), `sse.ts` LF-only framing.

### Current phase / status

STABLE — see top of file. Branch ready for PR at 22 commits.

### Blockers

None new. See the top-level Blockers section (live-services smoke test still pending; one
pre-existing flaky live-game E2E).

### Next steps

Unchanged — see the top-level Next Steps (open PR, seed corpus, real-key smoke test, `make evals`).

## Recent Changes (2026-07-11 — review hardening of chat stream, `chat`)

### What changed

Adversarial review of the branch diff surfaced three chat issues; all fixed in commit `3258fff`:

- **`services/api/app/services/chat/loop.py`** — the forced-text final round sent `tool_choice="none"` without `tools`, which the OpenAI API rejects with a 400. Any conversation using all 3 tool rounds would have ended in a user-visible error instead of an answer. Fix: always send `tools`; `tool_choice="none"` on the final round forces the text answer.
- **`services/api/app/schemas/chat.py`** — `champion_focus` was an unbounded string interpolated into the system prompt (token-cost amplifier + attacker-controlled system-prompt block). Now capped at 64 chars (champion-name sized).
- **`services/api/app/api/routers/chat.py`** — chat is the first endpoint converting anonymous HTTP directly into synchronous LLM spend. Added a per-process cap of 4 concurrent streams (`asyncio.Semaphore`); saturated requests get 429 `chat_busy`, the slot releases when the stream drains. Broader auth/per-user rate limiting remains a documented non-goal, consistent with the rest of the API.

### Tests / lint

- 2 new tests (`test_chat_request_rejects_oversized_champion_focus`, `test_chat_stream_busy_returns_429_and_recovers`) + updated max-rounds loop assertion. Backend: **223 passed, 2 skipped**; `make lint` clean; Playwright 27/27.

### Next steps

- Unchanged from below (PR, corpus seeding, real-key smoke test, `make evals`).

## Recent Changes (2026-07-10 — LLM UI integration: AI Coach + Coach Chat + evals, `chat`)

### What changed

- **AI Coach (Feature A, per `docs/LLM_INTEGRATION.md` + `tasks/plan.md` corrections)**
  - `services/api/app/schemas/analysis.py` + `app/api/routers/analysis.py`: `POST /riot-accounts/{id}/analysis` (202; resolves account via `resolve_riot_account_identifier`, champion via `get_champion_by_id`; 24h tz-aware cache short-circuit → `already_exists`; day-bucketed deterministic `_job_id` `llm-{account}-{champ}-{date}` so failed runs can retry next day; `enqueue_job → None` still 202) and `GET ...?champion_name=` (latest row shaped defensively — `parse_error` rows with `{"raw": ...}` payloads return null summaries, invalid recommendation dicts are skipped, never 500).
  - `league-web/src/lib/hooks/useAnalysis.ts`: POST → poll GET every 2s (max 30) **with `{useCache: false}`** (apiGet caches GETs by default — a cached `null` would never resolve); `already_exists` → immediate GET; 60s timeout message; `useAppError("analysis")`; runId ref invalidates in-flight polls on account switch.
  - `AnalysisPanel` (recommendation cards, ΔW as percentage, collapsible bias notes, dismiss) + `AnalysisButton` (auto-targets most-played champion via new `getMostPlayedChampion(matchDetails, puuid)` in `match-utils.ts`) wired into `/home` and `/riot-account/[riotId]` via new `MatchPageShell.analysisPanel` slot. `CompareButton` deleted. Buttons hidden in demo mode.
- **Coach Chat (Feature B — stateless, SSE streaming, tool calling)**
  - `OpenAIClient.stream_chat()` (`llm_client.py`): streamed chat completions; content deltas yielded immediately, tool-call deltas accumulated by index in pure `accumulate_tool_call_delta`.
  - `app/services/chat/`: `tools.py` (4 tools reusing existing services — `get_player_profile`, `get_latest_analysis`, `get_action_stats` (aggregate+compare, trimmed), `list_recent_matches`; Pydantic args → OpenAI schemas; `cap_tool_result` 4000-char cap; missing data → `{"message": ...}` never exceptions), `loop.py` (`run_chat_turn`: ≤3 tool rounds, ≤2 executions/round, 12-message window, final round forces `tool_choice="none"`, tool failures become readable error results), `prompts.py` (coach persona + grounding rules, no PII echo).
  - `app/api/routers/chat.py`: `POST /riot-accounts/{id}/chat/stream` → SSE (`token`/`tool_call`/`tool_result`/`done`/`error`), live_game headers; 404/422/503 raised before streaming; generator opens its own DB session (request session may close before a StreamingResponse drains).
  - Frontend: `src/lib/sse.ts` (hand-rolled POST-compatible SSE parser), `useChat.ts` (transcript state, streaming append into a placeholder assistant bubble, tool-activity label, AbortController on unmount/account switch, ≤20-message history), `ChatPanel` fixed drawer + `ChatButton` ("Ask Coach") on both pages; transcript survives drawer close, discarded on navigation.
- **Eval harness (Feature C)**: `evals/` — leave-one-out retrieval eval (precision@k/recall@k/MRR, latency p50/p95, est. cost/query; relevance = same champion + rank + dominant gap category) + LLM-as-judge (relevance/factuality/completeness 1–5, calibration procedure in `evals/README.md`). Gated behind `RUN_EVALS=1` (`make evals`); skips gracefully on missing DB/key/corpus (<10 rows). Pure metric/judge-parsing unit tests run ungated. Results → `evals/results/<ts>_<confighash>.json` (gitignored).
- **Plan artifacts**: `tasks/plan.md`, `tasks/todo.md`.

### Tests / lint

- Backend: **221 passed, 2 skipped** (40 new: analysis router 10, stream client 8, chat tools 11, chat loop 7, chat router 5 — minus overlaps); `make lint` clean.
- Frontend: lint clean (pre-existing AuthForm warning only); production build clean; Playwright **27/27** (3 new analysis-flow, 3 new chat-flow; chat E2E streams timed SSE chunks via a fetch override to test real incremental behavior).
- E2E caught one real bug pre-commit: `useAppError.errorMessage` returns `""` (not null) when clear, which made the AI Coach button mount in "Hide" state — normalized in `useAnalysis`/`useChat`.

## Recent Changes (2026-06-03 — TECHNICAL_ARCHITECTURE Next.js sync)

### What changed

- **`docs/TECHNICAL_ARCHITECTURE_AND_PATTERNS.md`**: brought frontend section in line with `frontend-enhancements` branch reality.
  - **§3.3**: added `LiveGameSlot/` and `DynamicImportBoundary` to component table.
  - **§3.6**: replaced generic perf bullets with S1–S5 ( `next/dynamic`, `useTransition`, React Compiler, stable `matchDetails`, chunk error recovery).
  - **§3.7** (new): Next.js features leveraged today vs. not yet used; documents client-first SPA-on-Next rendering model and highest-ROI future wins (Server Components, server `fetch`, Route Handlers, `generateMetadata`, streaming, parallel routes, full `next/image`).
  - **§4.3**: Playwright E2E (22 tests, 4 specs) replaces stale "no frontend test suite" note.
  - **§5 / §7**: frontend perf key update; server-data-layer roadmap item.

### Current phase / status

STABLE — docs-only change; no application code modified.

### Blockers

None.

### Next steps

- Ship `frontend-enhancements` PR (code already landed on branch; doc now describes it).
- Future: Server Components migration per §3.7 when prioritizing frontend TTFB / bundle size.

### Tests / lint

Not applicable (markdown only).

---

## Recent Changes (2026-06-03 — dead Vector shim removed + docs finalized, `claude-workflows-rag`)

### What changed

- **`services/api/app/db/migrations/versions/20260601_0004_rag_embedding_column.py`**: removed dead `try/except ImportError` shim (~11 lines). `Vector` now imports directly from `pgvector.sqlalchemy`. This was the only WARN from verify-changes. Lint clean.
- **`docs/LLM_PIPELINE_STATUS.md`**: removed completed "Remove dead Vector shim" item from Recommended section; removed WARN row from Open Nits table; renumbered Eval harness from item 4 → item 3.
- **Safe-to-delete docs identified**: `docs/rag-design.md` and `docs/LLM_RAG_COMPLIMENTARY.md` are fully superseded by `docs/LLM_PIPELINE_STATUS.md`.

### Key files

- `services/api/app/db/migrations/versions/20260601_0004_rag_embedding_column.py`
- `docs/LLM_PIPELINE_STATUS.md`

### Tests / lint

- `ruff check services/api/app/db/migrations/versions/20260601_0004_rag_embedding_column.py` — clean.

---

## Recent Changes (2026-06-03 — unified pipeline status doc, `claude-workflows-rag`)

### What changed

- **`docs/LLM_PIPELINE_STATUS.md`** (new): unified status and integration roadmap doc. Supersedes `docs/rag-design.md` and `docs/LLM_RAG_COMPLIMENTARY.md`. Covers: full pipeline status table (Steps 1–8 + 6.5), Phase 1 RAG complete with corpus status, Phase 2 not-started, the two required items before LLM_INTEGRATION.md, eval harness scope, open nits table from verify-changes.
- **Corpus verified end-to-end**: `make seed-rag-corpus` ran successfully for Jhin/SILVER; `make corpus-stats` confirmed 1 `LLMAnalysis` row with `with_embedding = 1`.
- **Diagnosed `no_data` skip**: root cause documented — the account exists in DB but the target champion's matches have no scored actions (`delta_w IS NULL` in `match_action`). Fix: `make score-account-matches RIOT_ID=...` before seeding.

### Key files

- `docs/LLM_PIPELINE_STATUS.md` (new — replaces `rag-design.md` and `LLM_RAG_COMPLIMENTARY.md`)

### Tests / lint

- No code changes this session. No lint or test re-run needed.

---

## Recent Changes (2026-06-03 — RAG corpus seeding tooling, `claude-workflows-rag`)

### What changed

- **`scripts/seed_rag_corpus.py`** (new): batch corpus seeding script. Accepts `--entry RIOT_ID:CHAMPION_ID` (repeatable) or `--from-file file.txt` (one entry per line, `#` comments). Calls `llm_analysis_job({}, ...)` directly (ARQ ctx is unused) — runs the full pipeline steps 5→8 including post-persist embedding storage, so every successful run adds an embeddable row to the corpus. Per-entry error handling: skips entries whose account is not yet in DB with an actionable message. Prints a summary table (succeeded / skipped / failed) and the `corpus-stats` query to check coverage.
- **`Makefile`** (3 new targets):
  - `make seed-rag-corpus ARGS='--entry "name#NA1:157"'` — run corpus seeding
  - `make seed-rag-corpus-dry ARGS='...'` — dry-run: resolves accounts, prints plan, no LLM calls or DB writes
  - `make corpus-stats` — shows `champion_name / rank_tier / total / with_embedding` grouped by champion from `llm_analysis`
- **Docker service name clarified**: docker-compose service is `postgres` (container `league_postgres`), not `db`. The `\d llm_analysis` verification command must use `docker exec league_postgres psql ...`, not `docker compose exec db`.

### Key files

- `scripts/seed_rag_corpus.py`
- `Makefile` (seed-rag-corpus, seed-rag-corpus-dry, corpus-stats targets)

### Tests / lint

- No new tests (seeding script is a thin CLI wrapper around `llm_analysis_job` which already has full test coverage including RAG paths).
- `ruff check scripts/seed_rag_corpus.py` — clean.

---

## Recent Changes (2026-06-01 — RAG few-shot retrieval, `claude-workflows-rag`)

### What changed (Phase 2 of `docs/rag-design.md`)

- **Schema**: nullable `vector(1536)` `embedding` column on `llm_analysis` + HNSW cosine index (`ix_llm_analysis_embedding_hnsw`, m=16/ef_construction=64). Migration `20260601_0004` (revises `20260316_0003`); runs `CREATE EXTENSION IF NOT EXISTS vector`. Model: `embedding: list[float] | None` via `pgvector.sqlalchemy.Vector` (`models/llm_analysis.py`).
- **Embeddings**: `OpenAIClient.embed(text, model="text-embedding-3-small")` (`services/llm_client.py`).
- **Retrieval service** (`services/rag_retrieval.py`): `build_embedding_text()` (compact champion/rank/gaps/bias single-line text), `retrieve_few_shot_examples()` (champion-filtered cosine KNN, fail-soft → `[]`), `format_few_shot_examples()` (prompt-friendly dicts).
- **Prompt** (`services/llm_prompt.py`): `build_user_prompt(..., few_shot_examples=...)` renders a `## Reference Examples` section before the Player Profile; no-ops on empty.
- **Pipeline** (`jobs/llm_analysis.py`): new Step 6.5 (embed query → retrieve → inject) and a post-persist embedding store; both gated by `rag_enabled` + `openai_api_key` and wrapped fail-soft.
- **Config** (`core/config.py`): `rag_enabled=True`, `rag_embedding_model="text-embedding-3-small"`, `rag_few_shot_limit=3`.
- **Backfill**: `scripts/backfill_rag_embeddings.py` (`--batch-size`, `--dry-run`) + Makefile targets `backfill-rag-embeddings` / `backfill-rag-embeddings-dry`.
- **Design doc**: `docs/rag-design.md` (Proposed) — problem, rejected standalone-search alternative, phased plan.

### Tests / lint

- New `test_rag_retrieval.py` (17 tests) + additions to `test_llm_client.py` (embed), `test_llm_prompt.py` (few-shot injection), `test_llm_analysis_job.py` (injection + fail-soft). Touched files: 47 passed.
- `make lint` clean; `make test` → **181 passed, 2 skipped**. No new dependencies (`pgvector>=0.3.6`, `openai>=1.58.0` pre-declared).
- Not run: migration up/down round-trip (no DB container up).

### Note on the prior verify-changes caveat

- The 2026-06-01 scale-verification entry below recorded that `/verify-changes` had been authored but **never actually invoked**. It has now been run end-to-end for real on this branch (Phase 1 dependency gate + Phase 4 lint/test executed against live tooling, not a manual stand-in), partially resolving prior Next Step 9. Phase 5 (`--deep` subagents) was not used (default fast run).

## Recent Changes (2026-06-01 — scale & maintainability verification)

### What changed

- **New reusable workflow command**: `.claude/commands/verify-changes.md`. Invoke as `/verify-changes [base-ref] [--deep]`. It diffs a branch against a base ref and gates it on two bars — (1) **scale-appropriate** (no unneeded deps; optimizations justified at current scale) and (2) **maintainable** (not overengineered) — by orchestrating the agent-skills (`code-simplification`, `code-review-and-quality`, `performance-optimization`) plus an explicit dependency-hygiene gate and a lint/build/e2e integrity check. `--deep` fans out to the `code-reviewer` + `test-engineer` subagents.
- **Authored the command but did not actually invoke it.** The GO-WITH-NITS verdict below is from a **manual review performed by hand** (real `git diff` + file reads + reasoning) that _mirrors_ the workflow's phases — NOT from running `/verify-changes` or its agent-skills (`code-simplification`, `code-review-and-quality`, `performance-optimization`). Phase 4 (lint/build/e2e) and Phase 5 (`--deep` subagents) were not run. The findings are evidence-based, but the workflow itself is unvalidated end-to-end.

### Findings (verify-changes, 2026-06-01)

- **Dependencies** — 3 new deps, all **devDependencies**, **zero new runtime/bundle deps**. `@playwright/test ^1.59.0` justified (real E2E suite). The two React Compiler packages (`babel-plugin-react-compiler`, `eslint-plugin-react-compiler`, both `^19.1.0-rc.2`) power S4 annotation mode on 3 files — **WARN** on caret-on-RC pin (non-reproducible); **NOTE** marginal ROI at current scale (contained, removable).
- **Overengineering** — only real flag is `e2e/fixtures/matches.ts` (255 lines): fixtures carry detail (`perks`, damage/CS totals, summoner-spell IDs) and repeated ally/enemy blocks that no spec asserts. Everything else (`e2e/helpers.ts`, `DynamicImportBoundary.tsx` at 35 lines, `LiveGameSlot.tsx`, `playwright.config.ts`) is lean; deterministic anchors used throughout (no arbitrary timeouts); conditional paths branch-tested.
- **Performance at scale** — S1/S3 code-splitting (recharts, `LiveGameCard`) and S5 `matchDetails` reference stability all **Justified**; S4 React Compiler annotation **borderline but not harmful** (opt-in, removable).

### Tests / lint

- Not re-run this session (static review per the request's focus). Recorded status stands: lint clean (pre-existing `AuthForm.tsx` exhaustive-deps warning only); 22/22 E2E green as of 2026-05-30.

## Recent Changes (2026-05-27, frontend-enhancements — React perf S1–S5 + Playwright E2E)

### What changed

- **S1 — Code-split `ChampionKdaChart`** via `next/dynamic` (`ssr:false`); recharts ships only when a match with 2+ point KDA history is expanded. New `MatchCard/ChartSkeleton.tsx` placeholder + `components/common/DynamicImportBoundary.tsx` error boundary with a `resetKey` prop so transient chunk-load failures don't permanently break the UI.
- **S2 — `useTransition`** wired into `MatchesTable` pagination and queue-tab switches; stale render stays visible while the next page/filter computes, click feedback stays instant.
- **S3 — Code-split `LiveGameSlot`** via `next/dynamic`; the `LiveGameCard` chunk only loads when SSE reports an in-game state. Idle / `not_in_game` / error renders are pure status UI.
- **S4 — React Compiler annotation mode (`"use memo"`)** opted-in on `MatchesTable`, `home` page, and `riot-account/[riotId]` page (per-file rather than repo-wide).
- **S5 — Stable `matchDetails` reference** in `useMatchList`. Removed the `matchDetailsRef` / `loadedDetailCount` gate; `setMatchDetails` now returns `prev` when content is unchanged, and the polling seeding effect only merges entries genuinely absent from `prev`. Stops `matchSummaryStats` / `championHistoryByMatchId` memos from re-running every 3-second poll tick.

### Config + follow-up fixes

- **`next.config.ts`**: `reactCompiler` moved to top-level (stable in Next.js 16; staying under `experimental` triggered a startup warning + risked silent fallback).
- **`useMatchList` polling tick fix**: the seeding effect was overwriting existing entries with freshly-deserialized objects every poll, churning `matchDetails` references. Now only merges entries absent from `prev`.

### Playwright E2E suite (`league-web/e2e/`)

- 22 tests across 4 specs:
  - `matches-table-tabs.spec.ts` — queue tab filtering (S2) + summary stats W/L correctness (S5 regression).
  - `matches-table-pagination.spec.ts` — Next/Previous via `useTransition` (S2).
  - `match-card-chart.spec.ts` — dynamic chart load, skeleton→chart transition, `DynamicImportBoundary` `resetKey` recovery (S1).
  - `live-game-slot.spec.ts` — dynamic `LiveGameSlot` with SSE `not_in_game` / error / retry flows (S3).
- Typed fixtures in `e2e/fixtures/matches.ts` cover Ranked Solo, Normal Draft, and ARAM queue types with multi-champion history data.
- Mocks use `page.route()` wildcards — no backend required to run tests (`cd league-web && npm run test:e2e`).
- Locator hardening fixes: `data-testid="tab-bar"` on the tab bar to scope tab-click locators away from row cells with the same accessible name; `exact: true` on pagination button locators so `Next` no longer matches the Next.js Dev Tools button.

### Staged-but-uncommitted (test stability + doc clarification)

- New `gotoAccountAndWait(page)` helper in `e2e/helpers.ts` — navigates to the riot-account page and awaits the first "Ranked Solo" cell.
- `live-game-slot.spec.ts`: removed `waitForTimeout(500/2000)` calls. Retry test now uses `Promise.all([page.waitForRequest(...), click])`; "no account loaded" test waits on the deterministic page-error copy "No search results for the summoner …"; error-state test asserts the "Please try again." copy.
- `match-card-chart.spec.ts`: collapsed three overlapping expansion tests into one combined "expand → chart loads → SVG renders" test. Single-game (Lux/ARAM) no-chart test now anchors on close-button visibility instead of `waitForTimeout(1000)`.
- `matches-table-pagination.spec.ts`: merged the standalone "no JS errors during navigation" assertion into the "Next navigates to page 2" test (single `pageerror` listener); reused `gotoAccountAndWait`.
- `matches-table-tabs.spec.ts`: added a `queueLabelCells(page)` helper because `MatchRow` renders `<tr role="button">`, overriding the implicit row role — rows are now counted via the first cell. Removed the redundant "switch back to All" test.
- `docs/TECHNICAL_ARCHITECTURE_AND_PATTERNS.md`: clarified that `isHydrated` is a workaround for client-only `sessionStorage` reads on `"use client"` routes, not a Next.js feature. Notes the cookie-migration path that would let those routes render server-side and remove the pattern.

### Key files

- `league-web/next.config.ts`
- `league-web/src/components/MatchesTable/MatchesTable.tsx` (useTransition, `data-testid="tab-bar"`, `"use memo"`)
- `league-web/src/components/MatchCard/{MatchCard.tsx, ChartSkeleton.tsx, MatchCard.module.css}`
- `league-web/src/components/common/DynamicImportBoundary.tsx` (new)
- `league-web/src/components/LiveGameSlot/LiveGameSlot.tsx` (dynamic import)
- `league-web/src/lib/hooks/useMatchList.ts` (S5 reference stabilization + poll-tick merge fix)
- `league-web/src/app/{home,riot-account/[riotId]}/page.tsx` (`"use memo"`)
- `league-web/playwright.config.ts`, `league-web/TESTING.md`, `league-web/e2e/` (suite + fixtures)

### Tests / lint

- Frontend lint clean; backend untouched (still 160/160).

---

## What's Built

### Backend (FastAPI + ARQ)

- **Search flow**: `GET /search/{riot_id}/matches` — account resolved from DB first; Riot called for account only on first sync (account not in DB). Match IDs fetched from Riot on first sync, `?refresh=true` (page 1), or see more (`after>0`). Supports `?page=N&limit=N&refresh=true`.
- **Auth match flow**: `GET /riot-accounts/{id}/matches` — paginated match list from DB; Riot match IDs only when `?refresh=true` (page 1) or see more (`after>0`).
- **Pagination schema**: `PaginatedMatchList` wraps `data` + `PaginationMeta` (page, limit, total, last_page, stale, stale_reason). On 429 during page-1 sync, endpoints fall back to DB and return cached data with `stale=true`.
- **Auth flow**: `POST /users/sign_in`, `POST /users/sign_up` — optional user authentication.
- **Riot API Client**: Redis-backed sliding-window rate limiter with dynamic header parsing and exponential backoff.
- **Background jobs**: `fetch_match_details_job` (batch → auto-enqueues `extract_match_timeline_job`), `extract_match_timeline_job` (state vector + action extraction), `score_actions_job` (ΔW scoring), `llm_analysis_job` (steps 5→8 orchestration, `keep_result=10`), `fetch_timeline_cache_job` (timeline warmup), `sync_all_riot_accounts_matches` (cron every 6h).
- **Data model**: `RiotAccount`, `Match` (with `game_info` JSONB), `RiotAccountMatch` join table. `pgvector` extension enabled.
- **Observability**: Structured JSON logging, `increment_metric_safe` metric helper.
- **AI Coach / RAG pipeline**: 8-step pipeline (ingest → extract → score → aggregate → compare → prompt → LLM call → persist), with Step 6.5 RAG few-shot retrieval. See `docs/LLM_PIPELINE_STATUS.md` and `docs/LLM_DATA_PIPELINE.md`.
- **Coach Chat**: stateless SSE streaming, tool-calling loop (`app/services/chat/`) with 4 tools (`get_player_profile`, `get_latest_analysis`, `get_action_stats`, `list_recent_matches`), all strictly account-scoped.
- **Eval harness**: `evals/` — retrieval + LLM-as-judge metrics, gated behind `RUN_EVALS=1` (`make evals`).

### Frontend (Next.js 16)

- **Pages**: `/` (search + optional auth), `/home` (match results dashboard), `/riot-account/[riotId]` (search results view).
- **API client**: `src/lib/api.ts` — typed `apiGet<T>` / `apiPost<T>` wrappers.
- **Client cache**: `src/lib/cache.ts` — in-memory LRU-like cache with TTL.
- **Session management**: `sessionStorage`-backed `useSession` hook.
- **Match history UX**:
  - `MatchesTable` replaces card-grid history on `/home` and `/riot-account/[riotId]`.
  - Table uses sticky headers, queue-group tabs, row-level selection, and skeleton states.
  - Right-side detail overlay (`MatchDetailPanel`) renders `MatchCard` in `expanded` mode.
  - Queue type modeling is centralized in `src/lib/types/queue.ts` with coarse tab grouping (`GameQueueGroup`) and granular row labels (`GameQueueMode`).
- **Match card**: `MatchCard` is decomposed into `ItemSlot`, `Teams`, `ChampionKdaChart`, `match-card.utils.ts`, and `types.ts` within `MatchCard/`. The main file is a ~200-line orchestrator, `memo`-wrapped at export.
- **Pagination**: Reusable `Pagination` component with Previous/Next buttons, "Page X of Y", total count. Hidden when single page. Wired into `MatchesTable` via optional `paginationMeta`/`onPageChange` props. "See more" load-more button appended on the last page for inline accumulation without losing context.
- **Rank in header**: `useRank(riotAccountId, { refreshIndex })` fetches `GET /riot-accounts/{id}/fetch_rank` and returns `{ rank, rankSubtitle }`. Used on `/home` and `/riot-account/[riotId]`.
- **Live game**: `useLiveGameWhenReady` gates a single-attempt SSE connection on match list readiness; `LiveGameSlot` renders live/not_in_game/error/connecting states with a retry action.
- **AI Coach**: `useAiCoach` hook (shared by both match pages) wraps champion picker state, most-played fallback, panel-open invariant, and the analyze click handler; resets picked champion on account switch. `useAnalysis` polls `POST/GET /riot-accounts/{id}/analysis` with cache-busting GETs.
- **Coach Chat**: `useChat` + hand-rolled SSE parser (`src/lib/sse.ts`) drive a streaming transcript in `ChatPanel`/`ChatButton`; AbortController on unmount/account switch, ≤20-message history, strips empty assistant turns before resend.
- **Error handling** (`src/lib/errors/`):
  - `ApiError` class with `status`, `detail`, `riotStatus` fields.
  - `buildApiErrorFromResponse` / `toApiError` for normalising HTTP and plain errors.
  - `formatApiError` — translates backend codes via `DETAIL_MESSAGES` lookup table; handles `riot_api_failed` with `riotStatus` branching (404/429/other); HTTP status fallbacks for unknown codes; no misleading "Network error" prefix on non-HTTP errors.
  - `useAppError(scope)` React hook — `{ errorMessage, reportError, clearError }`.
  - Call sites use `reportError(err)` for general errors; intercept before `reportError` when a page-level context string (e.g. summoner name) is needed.
- **Perf**: code-split `ChampionKdaChart` and `LiveGameSlot` via `next/dynamic`; `useTransition` on table pagination/tab switches; React Compiler annotation mode on `MatchesTable` and both page components; stable `matchDetails` reference in `useMatchList` to avoid re-renders on polling ticks.

### Infrastructure

- Docker Compose: `api`, `worker`, `db`, `redis`.
- Railway deployment via `railway.json` + nixpacks. API starts Uvicorn immediately on boot; `release.sh` runs `alembic upgrade head` as the pre-deploy/release step (must be configured in the Railway dashboard).
- Alembic async migrations.

---

## Request Flow Summary

```
User → Search (Riot ID) → GET /search/{riot_id}/matches?page=1
  → find_or_create_riot_account (DB upsert)
  → Rate limit check (Redis)
  → Fetch match IDs (Riot API)
  → Upsert match IDs (DB, ON CONFLICT DO NOTHING)
  → Pre-query backfill of missing game_info (Riot API, max_fetch=limit)
  → Return paginated match list + meta

User → Page 2+ → GET /search/{riot_id}/matches?page=N
  → Resolve riot account from DB (no Riot API)
  → Return paginated match list + meta

Background (async, route-level BackgroundTasks → ARQ):
  → enqueue_missing_timeline_jobs → fetch_timeline_cache_job → Redis cache `timeline:{match_id}`
  → fetch_match_details_job → extract_match_timeline_job → score_actions_job (ΔW scoring)

AI Coach:
  → POST /riot-accounts/{id}/analysis → llm_analysis_job (aggregate → compare → RAG retrieve → prompt → LLM → persist)
  → Frontend polls GET .../analysis every 2s until a row exists (or already_exists short-circuits)

Coach Chat:
  → POST /riot-accounts/{id}/chat/stream → SSE (token/tool_call/tool_result/done/error)
  → Tool loop: ≤3 rounds, ≤2 tool executions/round, account-scoped tools only

Optional:
  → Sign In/Up → POST /users/sign_in → Validate (DB) → Save session
```

---

## Open Tickets

None open. The last tracked ticket (race condition in `_get_or_create_match` / `upsert_user_from_riot`) was resolved via `INSERT ... ON CONFLICT DO NOTHING` — see [`docs/app_state_archive.md`](app_state_archive.md) session 15 (2026-03-06) for detail.
