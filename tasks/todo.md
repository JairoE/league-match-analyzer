# TODO — LLM/RAG User-Facing Features

See `tasks/plan.md` for full task specs, acceptance criteria, and corrections.

## Phase 0

- [x] T0: tasks/plan.md + tasks/todo.md

## Phase A — AI Coach button

- [x] A1: backend schemas + analysis router + registration
- [x] A2: backend router tests (test_analysis_router.py)
- [x] A3: frontend types + getMostPlayedChampion helper
- [x] A4: useAnalysis hook (poll with useCache: false)
- [x] A5: AnalysisPanel + AnalysisButton + MatchPageShell slot
- [x] A6: wire both pages, delete CompareButton
- [x] A7: Playwright e2e/analysis-flow.spec.ts
- [x] Checkpoint A: 191 backend tests, lint clean, 24/24 e2e (manual live-server E2E deferred)

## Phase B — Chatbot

- [x] B1: OpenAIClient.stream_chat + delta accumulation + tests
- [x] B2: chat tools (4) + cap_tool_result + tests
- [x] B3: agentic loop + prompts + chat schemas + tests
- [x] B4: chat router (SSE) + tests
- [x] B5: sse.ts parser + chat types + useChat hook
- [x] B6: ChatPanel drawer + ChatButton + page wiring
- [x] B7: Playwright e2e/chat-flow.spec.ts
- [x] Checkpoint B: 221 backend tests, lint clean, 27/27 e2e (real-key streaming smoke test deferred)

## Phase C — Eval harness

- [x] C1: evals/ retrieval eval (RUN_EVALS=1 gated)
- [x] C2: evals/judge.py LLM-as-judge + README
- [x] Checkpoint C: all gates green; docs/app_state.md + docs/LLM_PIPELINE_STATUS.md updated

## Deferred (needs live services / operator)

- [ ] Seed corpus: `make score-account-matches` + `make seed-rag-corpus` (5+ rows/champion)
- [ ] Manual smoke test with real OpenAI key (AI Coach click + chat streaming)
- [ ] `make evals` once corpus ≥ 10 rows
- [ ] SSE streaming smoke test on Railway after deploy
