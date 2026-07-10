# Plan: Complete the LLM/RAG User-Facing Features (AI Coach + Chatbot + Evals)

## Context

The 8-step LLM analysis pipeline + RAG few-shot retrieval (step 6.5) is fully built and tested
on the backend (181 tests), but has **zero HTTP endpoints and zero frontend integration** — it is
only reachable via CLI scripts. The remaining work to complete the product idea is:

- **Feature A — "AI Coach" button**: user clicks a button → analysis job runs → recommendations
  panel appears. Fully spec'd in `docs/LLM_INTEGRATION.md` (authoritative; corrections below).
- **Feature B — Chatbot**: user chats about their games. No spec existed; designed here per
  user decisions: **stateless** (no DB models/migrations), **SSE token streaming**,
  **LLM tool calling** for grounding.
- **Feature C — Eval harness** (`evals/`): retrieval metrics + LLM-as-judge, per
  `docs/LLM_PIPELINE_STATUS.md`.

Out of plan scope (user deselected): corpus seeding — remains an operational prerequisite
(`make score-account-matches`, `make seed-rag-corpus`, `make corpus-stats`) noted where relevant.

**First step after approval**: write this plan to `tasks/plan.md` and the task list to
`tasks/todo.md` (couldn't be written during plan mode).

---

## Verified corrections to `docs/LLM_INTEGRATION.md`

1. **`champion_id: int`, not `str`** — `get_champion_by_id(session, champ_id: int)`
   (`services/champions.py:28`); convert to `str(champion_id)` when enqueueing
   `llm_analysis_job` (it takes the numeric ID as a string).
2. **Reuse `resolve_riot_account_identifier`** (`services/riot_accounts.py:87`) for 404
   semantics — don't hand-roll UUID parsing.
3. **Day-bucket the deterministic job id**: `f"llm-{riot_account_id}-{champion_id}-{date}"`.
   ARQ reserves completed job ids for ~1h (`keep_result`); a failed `no_data` run would
   silently swallow retries. When `enqueue_job` returns `None`, still return 202 "enqueued".
4. **Polling must bypass the frontend GET cache** — `apiGet` caches GETs by default
   (`api.ts:38`); `useAnalysis` poll loop must pass `{useCache: false}` or the first `null`
   gets cached and polling never resolves. Most likely silent bug in the spec.
5. **Defensive `output_payload` extraction** — on `parse_error` runs payload is `{"raw": ...}`;
   use `.get()` with type checks; response fields `str | None`.
6. **24h cache check must be tz-aware** — compare against `datetime.now(UTC) - timedelta(hours=24)`.
7. **`getMostPlayedChampion(matchDetails, puuid)`** — `matchDetails` is
   `Record<string, MatchDetail>`; reuse `getParticipantByPuuid` (`match-utils.ts:194`);
   the `matches` array param in the spec is unnecessary.
8. **Destructure `rank` from `useRank`** on both pages to send `rank_tier` in the POST.
9. **Demo mode guard** — `resolveMock` returns `{}` for unknown routes; hide/disable
   AnalysisButton and ChatButton when `isDemoMode()`; re-run `demo-mode-flow.spec.ts`.
10. **Poll GET with the `champion_name` returned by POST** (backend `Champion.name` is the
    source of truth on both sides), not the frontend's Riot `championName`.

---

## Feature B design (chatbot)

### Transport
`POST /riot-accounts/{riot_account_id}/chat/stream` → `StreamingResponse(text/event-stream)`
with the `live_game.py` headers (`Cache-Control: no-cache`, `X-Accel-Buffering: no`).
Client uses **fetch + ReadableStream SSE parsing** (EventSource is GET-only; query-string
transcripts hit URL limits and leak into logs; server-side token handoff would violate
statelessness; WebSocket is overkill for one-request-one-answer).

### Request schema (`app/schemas/chat.py`)
```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    champion_focus: str | None = None
```
Last message must be `role="user"` → 422 otherwise. Account resolved (404) before streaming.

### SSE event protocol
| Event | Data | Purpose |
|---|---|---|
| `token` | `{"text": "..."}` | Answer text delta |
| `tool_call` | `{"name", "label"}` | UI shows "Looking up your match stats…" |
| `tool_result` | `{"name", "ok"}` | Clears activity indicator |
| `done` | `{"finish_reason", "rounds"}` | Terminal success |
| `error` | `{"detail": "chat_failed"}` | Terminal failure |

### Agentic loop — new package `app/services/chat/`
- `tools.py` — each tool = Pydantic args model + async executor
  `(session, riot_account, args) -> dict` + UI `label`; `to_openai_schema()` from
  `model_json_schema()`; registry `CHAT_TOOLS`. Four tools, all reusing existing services:
  1. `get_player_profile()` — riot_id, rank_tier, analyzed champions (no puuid in output).
  2. `get_latest_analysis(champion_name?)` — latest `LLMAnalysis` row (recommendations,
     assessment, bias summary; excludes payloads/embedding).
  3. `get_action_stats(champion_name?, rank_tier?)` — resolve name→champ_id via `Champion`
     (case-insensitive), run `aggregate_action_stats_for_player` + `compare_action_stats`,
     item names via `load_item_name_map()`; trimmed: top 5 gaps, top 3 bias flags,
     top 5 ranked actions per group.
  4. `list_recent_matches(limit=5, max 10)` — via `list_matches_for_riot_account`; per-match
     `{champion, win, k/d/a, cs, duration, queue, timestamp}` from `game_info` participants.
  - Excluded deliberately: RAG `retrieve_few_shot_examples` (corpus is other players'
    analyses — wrong grounding for "your games" chat).
- `loop.py` — `run_chat_turn(session, riot_account, messages, champion_focus) ->
  AsyncIterator[ChatEvent]`. Max 3 tool rounds, ≤2 tool executions/round; final round forces
  `tool_choice="none"`; tool exceptions → `{"error": "tool_failed"}` result, never a crashed
  stream; forwards only the last 12 transcript messages.
- `prompts.py` — coach persona; grounding rules (only claim what tools returned; suggest
  running AI Coach when no data); ΔW interpretation; ≤~250 words; never output puuid/IDs.
- Guards: tool results capped via `cap_tool_result(payload, max_chars=4000)`;
  `max_tokens=700`, `temperature=0.4`.

### `OpenAIClient.stream_chat` (`services/llm_client.py`; `complete()`/`embed()` untouched)
```python
async def stream_chat(self, messages, tools=None, tool_choice=None,
                      max_tokens=700, temperature=0.4) -> AsyncIterator[ChatStreamChunk]
```
`ChatStreamChunk(kind: "token"|"tool_calls"|"finish", ...)`. Content deltas yielded
immediately; tool-call deltas accumulated by index in a pure, unit-testable helper
`accumulate_tool_call_delta(state, delta)` and yielded aggregated at finish.

### Frontend
- `src/lib/sse.ts` — hand-rolled `parseSseStream(body): AsyncGenerator<{event, data}>`.
- `src/lib/types/chat.ts`, `src/lib/hooks/useChat.ts` — fetch POST + stream parse; state
  `{messages, isStreaming, toolActivity}`; `useAppError("chat")`; AbortController on
  unmount/account change; disabled in demo mode.
- `src/components/ChatPanel/` — fixed-position right-side drawer (keeps page diffs ~10 lines,
  no new MatchPageShell slot) + `ChatButton` ("Ask Coach") in SubHeader `actions` on both
  pages. Transcript lives in page-level hook → survives drawer close, discarded on navigation.

---

## Task list

Sizes: S ≈ ≤1h, M ≈ 1–3h. Gates: `make test`, `make lint`, `cd league-web && npm run lint`,
`npm run test:e2e`.

### Phase 0
- **T0 (S)**: Write `tasks/plan.md` (this plan) + `tasks/todo.md` (checklist). Deps: none.

### Phase A — AI Coach button (vertical slice: backend → hook → UI → E2E)
- **A1 (M)** Backend schemas + router + registration. Create
  `services/api/app/schemas/analysis.py`, `services/api/app/api/routers/analysis.py`;
  edit `routers/__init__.py`. Per LLM_INTEGRATION.md Steps 1–3 with corrections 1–6.
  *Accept*: POST valid → 202 `{status:"enqueued", champion_name}`; <24h row →
  `already_exists` + analysis_id; 404 unknown account/champion; GET → latest
  `AnalysisResponse` or `null`. *Verify*: `make lint`.
- **A2 (M)** Backend tests `services/api/tests/test_analysis_router.py` — direct handler
  calls, monkeypatched `get_arq_pool` (assert `_job_id`), fake session/rows. All 7 spec
  cases + `enqueue_job → None` still 202. Deps: A1. *Verify*: `make test && make lint`.
- **A3 (S)** Frontend types `src/lib/types/analysis.ts` + `getMostPlayedChampion` in
  `src/lib/match-utils.ts` (correction 7). Deps: none (parallel with A1).
  *Verify*: `npm run lint`.
- **A4 (M)** `src/lib/hooks/useAnalysis.ts` — POST enqueue; poll GET every 2s max 30 polls
  with `{useCache: false}` (correction 4); `already_exists` → immediate GET; timeout message;
  `useAppError("analysis")`. Deps: A1, A3. *Accept*: idle→requesting→polling→done/timeout;
  no cached-null bug. *Verify*: `npm run lint`.
- **A5 (M)** `src/components/AnalysisPanel/` + `src/components/AnalysisButton/` +
  `MatchPageShell` gets `analysisPanel?: ReactNode` rendered between `{liveGame}` and
  warning. Handles 0–3 recommendations (parse_error rows), dismissible; button disabled
  when no account/champion or demo mode. Deps: A4. *Verify*: `npm run lint`.
- **A6 (M)** Wire `src/app/riot-account/[riotId]/page.tsx` + `src/app/home/page.tsx`;
  destructure `rank` from `useRank` (correction 8); **delete** `CompareButton.tsx`.
  Deps: A5. *Verify*: `npm run lint` + manual flow per spec Verification section.
- **A7 (M)** Playwright `e2e/analysis-flow.spec.ts` + `mockAnalysisRoutes(page)` helper
  (GET returns `null` N times then fixture — counter in route handler). Cases: happy path,
  cached path, timeout path; `demo-mode-flow.spec.ts` still green. Deps: A6.
  *Verify*: `npm run test:e2e`.

**Checkpoint A**: all four gates green + manual E2E (`make api-dev` + worker + `npm run dev`,
click AI Coach on an account with scored matches → panel with recommendations; re-click →
instant cached result). Human review before Phase B.

### Phase B — Chatbot
- **B1 (M)** `OpenAIClient.stream_chat` + `ChatStreamChunk` + pure
  `accumulate_tool_call_delta`; tests `test_llm_client_stream.py` with fake chunk iterators
  (content-only, split tool-arg deltas, multi-tool). Deps: none.
  *Accept*: `complete()`/`embed()` untouched. *Verify*: `make test && make lint`.
- **B2 (M)** `app/services/chat/tools.py` — 4 tools + `cap_tool_result` + OpenAI schema
  gen; tests `test_chat_tools.py` (fake sessions/rows). Deps: none (parallel with B1).
  *Accept*: valid function specs; every executor returns JSON-safe dict ≤4000 chars;
  missing data → `{"message": ...}` not exceptions. *Verify*: `make test && make lint`.
- **B3 (M)** `chat/loop.py` + `chat/prompts.py` + `app/schemas/chat.py`; tests
  `test_chat_loop.py` (scripted fake client: round 1 tool_calls → round 2 tokens; exact
  event sequence; max-rounds forces `tool_choice="none"`; tool exception → `ok:false` and
  loop continues; 12-message window). Deps: B1, B2. *Verify*: `make test && make lint`.
- **B4 (S)** `app/api/routers/chat.py` + registration; tests `test_chat_router.py`
  (iterate `body_iterator`, assert SSE framing + terminal `done`; 404; last-message-not-user
  → 422; generator exception → `error` event). Deps: B3. *Verify*: `make test && make lint`.
- **B5 (M)** `src/lib/sse.ts` + `src/lib/types/chat.ts` + `src/lib/hooks/useChat.ts`.
  Deps: B4 (contract). *Accept*: incremental append; abort on unmount leaves no dangling
  state. *Verify*: `npm run lint`.
- **B6 (M)** `src/components/ChatPanel/` drawer + ChatButton; wire both pages (button next
  to AnalysisButton in SubHeader actions). Deps: B5, A6. *Accept*: open/close preserves
  transcript; tool-activity line during `tool_call`; input disabled while streaming; hidden
  in demo mode. *Verify*: `npm run lint` + manual with real key.
- **B7 (M)** Playwright `e2e/chat-flow.spec.ts` + `mockChatStream(page, events)` helper
  fulfilling `**/chat/stream` with a raw SSE body. Cases: send → reply rendered with
  tool activity having appeared; error event → error surface. Deps: B6.
  *Verify*: `npm run test:e2e`.

**Checkpoint B**: all gates green + manual streaming smoke test against real OpenAI key
(and on Railway if deployed — SSE headers already proven by live_game).

### Phase C — Eval harness (independent; requires seeded corpus — operational prereq)
- **C1 (M)** `evals/` retrieval eval: leave-one-out over real `LLMAnalysis` rows; query =
  `build_embedding_text()` of held-out row (reuse stored embedding); ground truth = shares
  champion + rank_tier + dominant gap category; precision@k / recall@k / MRR
  (k=`rag_few_shot_limit`), latency p50/p95, cost/query; timestamped JSON keyed by config
  hash in `evals/results/`. Gated behind `RUN_EVALS=1` so `make test` stays hermetic; skips
  gracefully below ~10 corpus rows. Deps: none. *Verify*: `RUN_EVALS=1 pytest evals/`
  produces results JSON; ungated `make test` unaffected.
- **C2 (M)** `evals/judge.py` LLM-as-judge (relevance/factuality/completeness 1–5 via
  existing `OpenAIClient.complete` json mode); merge into results JSON; `evals/README.md`
  with calibration procedure. Deps: C1. *Verify*: gated run + `make lint`.

**Checkpoint C / final**: `make test && make lint`, `npm run lint`, `npm run test:e2e` all
green; update `docs/app_state.md` + `docs/LLM_PIPELINE_STATUS.md` statuses.

---

## Risks & mitigations
| Risk | Mitigation |
|---|---|
| Polling never resolves for `no_data`/`skipped`/`llm_error` (no status column, no row) | 60s timeout + actionable message; day-bucketed job id allows retry |
| `apiGet` cache poisons polling | `{useCache: false}` (correction 4); covered by A2/A4 criteria + E2E timeout test |
| Proxy buffering breaks SSE in prod | Reuse exact live_game headers (proven on Railway); smoke test at Checkpoint B |
| Tool-call delta accumulation bugs | Pure helper + dedicated unit tests; `json.loads` in try/except → tool-error result |
| Chat cost blowout | Server-enforced caps: ≤20 msgs, 12-msg window, ≤3 rounds, ≤2 execs/round, 4000-char results, max_tokens=700, gpt-4o-mini |
| Demo mode regressions | Buttons hidden via `isDemoMode()`; `demo-mode-flow.spec.ts` re-run at both checkpoints |
| Eval misleading on tiny corpus | Skip below ~10 rows with clear message; seeding is a documented prereq |

## Assumptions (flag if wrong)
- 24h analysis cache key = account + champion (not rank_tier), matching job persistence.
- `evals/` at repo root, gated by `RUN_EVALS=1` (not in default pytest path).
- No auth/rate limiting on chat — consistent with every existing route in this portfolio app.
