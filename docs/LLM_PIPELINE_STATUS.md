# LLM Pipeline + RAG: Status & Integration Roadmap

**Last updated:** 2026-06-03
**Branch:** `claude-workflows-rag`

This document is the single source of truth for pipeline implementation status and what
remains before starting `docs/LLM_INTEGRATION.md`. It supersedes `docs/rag-design.md`
and `docs/LLM_RAG_COMPLIMENTARY.md`. The algorithmic spec (win probability model,
action ΔW framework, game state vectors, aggregation strategy) lives in
`docs/LLM_DATA_PIPELINE.md` — keep that doc for the runbook and deep theory.

---

## Pipeline Status

| Step | What | Status | Key files |
|------|------|--------|-----------|
| 1. Ingest | Fetch match + timeline from Riot API; cache timeline in Redis (1h TTL) | **Done** | `jobs/timeline_extraction.py` |
| 2. Extract | Per-minute state vectors + action events (legendary items, objectives) from timeline JSON | **Done** | `services/state_vector.py`, `services/action_extraction.py` |
| 1→2 Auto-wire | `fetch_match_details_job` auto-enqueues extraction; idempotent with deterministic `_job_id`; backfill script | **Done** | `services/enqueue_timeline_extraction.py`, `scripts/backfill_extraction.py` |
| 3. Score | Logistic regression win probability model trained from exported CSV | **Done** | `scripts/train_win_prob_model.py`, `services/win_prob_scoring.py` |
| 4. ΔW | `score_actions_job` computes pre/post win probability per action, persists `delta_w` | **Done** | `jobs/score_actions.py` |
| 5. Aggregate | Per-player action stats with K < 50 population fallback, optional champion + rank filters | **Done** | `services/action_aggregation.py` |
| 6. Compare | Rank summoner choices vs. population-optimal; detect selection bias (W(x) ≥ 0.55 + low ΔW) | **Done** | `services/action_comparison.py` |
| **6.5. Retrieve** | Embed query → cosine KNN over `llm_analysis` corpus → top-3 few-shot examples | **Done** | `services/rag_retrieval.py` |
| 7. Prompt LLM | Build system + user prompt with few-shot examples injected; call OpenAI | **Done** | `services/llm_prompt.py`, `jobs/llm_analysis.py` |
| 8. Store + Embed | Persist `LLMAnalysis`; generate and store embedding for future retrieval | **Done** | `jobs/llm_analysis.py`, migration `20260601_0004` |

---

## RAG Status

### Phase 1: Few-Shot Retrieval — Complete

All code implemented, lint-clean, 181 tests pass, verified end-to-end (1 corpus row seeded).

**What's in place:**

- `embedding vector(1536)` column + HNSW cosine index (`vector_cosine_ops`, m=16, ef_construction=64)
  on `llm_analysis` — migration `20260601_0004`
- `rag_retrieval.py`:
  - `build_embedding_text()` — encodes champion/rank/top-gaps/bias into a compact retrieval string
  - `retrieve_few_shot_examples()` — champion-filtered cosine KNN, fail-soft on empty corpus or DB error
  - `format_few_shot_examples()` — serializes results to prompt-friendly dicts
- `OpenAIClient.embed(text, model)` using `text-embedding-3-small` (1536 dims)
- Step 6.5 wired in `llm_analysis_job`: embed query → retrieve → inject into user prompt
- Post-persist: embedding generated and stored on every new `LLMAnalysis` row (Step 8)
- `build_user_prompt(few_shot_examples=...)` renders a `## Reference Examples` section;
  no-ops gracefully when corpus is empty
- Config flags: `rag_enabled` (default `True`), `rag_embedding_model`, `rag_few_shot_limit` (default 3)
- Backfill: `scripts/backfill_rag_embeddings.py` + `make backfill-rag-embeddings`
- Corpus seeding: `scripts/seed_rag_corpus.py` + `make seed-rag-corpus`

**Corpus status:** 1 row (Jhin/SILVER, 2026-06-03).

RAG returns 0 examples until ~5+ rows exist per champion. Quality improves meaningfully at ~50+ rows
per champion/rank bucket. The pipeline never aborts on an empty corpus.

**Why few-shot over standalone semantic search:**
Rejected standalone match-history embedding search because it has no real baseline (no keyword
search exists today), and the corpus is too small for meaningful precision@k metrics. The few-shot
route reuses existing `llm_analysis` payloads and pgvector infra, has a genuine baseline (the cold
prompt), and tells a cleaner story: *"RAG improves an existing ML+LLM pipeline's output quality."*

### Phase 2: Game Knowledge Grounding — Not started

Start when recommendations feel generic despite few-shot examples being injected.

Required work:
1. `game_knowledge` table — new model + migration; columns: `id`, `source`, `source_version`,
   `title`, `content`, `embedding vector(1536)`, `created_at`
2. Ingest pipeline:
   - Patch notes (Riot publishes at known URLs; parse + chunk by section)
   - Item descriptions (Data Dragon `item.json` already fetched by `load_item_name_map()`;
     extend to embed full passive/active text, not just names)
   - Champion synergies (community wiki or curated)
3. Step 6.5b: embed gap context → retrieve relevant knowledge chunks → inject as grounding
   in system or user prompt alongside few-shot examples

---

## Remaining Work Before `docs/LLM_INTEGRATION.md`

`LLM_INTEGRATION.md` adds an "AI Coach" button + `AnalysisPanel` to the web UI. The backend
pipeline is fully functional end-to-end. These items should be resolved first:

### Required

**1. Seed the corpus**

RAG is live but retrieving 0 examples. Seed at minimum 3–5 accounts × their top champions
to get ~5+ rows per champion and verify the full path works in the UI.

```bash
# Dry-run first (verifies accounts are in DB and matches are scored)
make seed-rag-corpus-dry ARGS='--from-file seeding_list.txt'

# Seed
make seed-rag-corpus ARGS='--from-file seeding_list.txt'

# Check coverage
make corpus-stats
```

**2. Ensure matches are scored before seeding**

`no_data` skip means scored match actions don't exist for the target champion. Run scoring
before seeding:

```bash
make account-match-stats RIOT_ID="name#NA1"        # check scored vs total
make score-account-matches RIOT_ID="name#NA1"      # score unscored matches
```

### Recommended (not blocking)

**3. Eval harness** (`evals/` directory)

Designed in `rag-design.md` Phase 1 but never built. Gives you the baseline cold-prompt number
and a post-RAG quality delta — the key portfolio story. Scope:

- ~30–50 hand-labeled cases from real `LLMAnalysis` records
- Programmatic ground truth: a retrieved example is *relevant* if it shares `champion_id` +
  `rank_tier` + dominant gap category with the query
- Metrics: precision@k, recall@k, MRR, latency p50/p95, cost per query (~80 lines, no library)
- `pytest evals/` entry point + timestamped JSON keyed by config hash (reproducible)
- LLM-as-judge rubric: relevance / factuality / completeness (1–5 each); calibrate against your
  own judgments on 10–20 cases

### Out of scope for integration (future)

- Phase 2 RAG (game knowledge grounding)
- Reranking experiments: cross-encoder or LLM-as-judge top-20 → top-3
- Metadata pre-filter by champion + rank before vector search
- DNN win probability model upgrade (needs 100K+ matches)

---

## Key Commands

```bash
# Corpus building
make seed-rag-corpus ARGS='--from-file seeding_list.txt'
make seed-rag-corpus-dry ARGS='--from-file seeding_list.txt'
make corpus-stats

# Match scoring (prerequisite for seeding)
make score-account-matches RIOT_ID="name#NA1"
make score-account-matches-dry RIOT_ID="name#NA1"
make account-match-stats RIOT_ID="name#NA1"

# Pipeline debug (steps 5-8)
make llm-analysis-debug RIOT_ID="name#NA1" CHAMPION=157 DRY_RUN=1
make aggregate-actions-debug RIOT_ID="name#NA1"
make compare-actions-debug RIOT_ID="name#NA1"

# Embedding backfill (for rows created before RAG was wired)
make backfill-rag-embeddings
make backfill-rag-embeddings-dry

# Verify DB state
docker exec league_postgres psql -U league -d league -c "\d llm_analysis"

# Gates
make test && make lint
cd league-web && npm run lint
```

---

## Open Nits (non-blocking, from verify-changes 2026-06-01)

| Severity | Location | Issue |
|----------|----------|-------|
| NOTE | `jobs/llm_analysis.py` | `OpenAIClient` instantiated 3×; `comparison.to_dict()` and `build_embedding_text()` each called twice with identical args — build once and reuse |
| NOTE | `jobs/llm_analysis.py` | HNSW index premature at current corpus size (harmless) |
| NOTE | `core/config.py` | `rag_enabled=True` by default means 2 embedding API calls per job before corpus is seeded |
