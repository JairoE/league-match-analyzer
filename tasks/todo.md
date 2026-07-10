# TODO — LLM/RAG User-Facing Features

See `tasks/plan.md` for full task specs, acceptance criteria, and corrections.

## Phase 0

- [x] T0: tasks/plan.md + tasks/todo.md

## Phase A — AI Coach button

- [ ] A1: backend schemas + analysis router + registration
- [ ] A2: backend router tests (test_analysis_router.py)
- [ ] A3: frontend types + getMostPlayedChampion helper
- [ ] A4: useAnalysis hook (poll with useCache: false)
- [ ] A5: AnalysisPanel + AnalysisButton + MatchPageShell slot
- [ ] A6: wire both pages, delete CompareButton
- [ ] A7: Playwright e2e/analysis-flow.spec.ts
- [ ] Checkpoint A: make test && make lint, npm run lint, npm run test:e2e

## Phase B — Chatbot

- [ ] B1: OpenAIClient.stream_chat + delta accumulation + tests
- [ ] B2: chat tools (4) + cap_tool_result + tests
- [ ] B3: agentic loop + prompts + chat schemas + tests
- [ ] B4: chat router (SSE) + tests
- [ ] B5: sse.ts parser + chat types + useChat hook
- [ ] B6: ChatPanel drawer + ChatButton + page wiring
- [ ] B7: Playwright e2e/chat-flow.spec.ts
- [ ] Checkpoint B: all gates green

## Phase C — Eval harness

- [ ] C1: evals/ retrieval eval (RUN_EVALS=1 gated)
- [ ] C2: evals/judge.py LLM-as-judge + README
- [ ] Checkpoint C: all gates green; update docs/app_state.md + docs/LLM_PIPELINE_STATUS.md
