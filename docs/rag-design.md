# RAG Design: Few-Shot Retrieval for the LLM Coaching Pipeline

**Status:** Proposed
**Goal:** Portfolio / interview artifact — a measurably better LLM coaching output, built
evals-first, with a story that shows engineering judgment rather than a generic
semantic-search demo.

---

## Problem statement

Today, **Step 7** of the LLM pipeline (`app/services/llm_prompt.py` →
`app/jobs/llm_analysis.py`) sends the model a cold prompt: a statistical gap summary
(ΔW gaps, action rankings, selection-bias flags) with **zero examples** of good output.
Every analysis is generated from scratch, which produces inconsistent tone/depth across
similar situations and never reuses the good recommendations already persisted in
`llm_analysis.output_payload`.

**RAG use case:** before Step 7, retrieve the 2-3 highest-quality prior `LLMAnalysis`
records for a similar champion + rank + gap pattern and inject them as **few-shot
examples**. This complements — does not replace — the win-probability ML model, which
remains the quantitative backbone (see [LLM_RAG_COMPLIMENTARY.md](LLM_RAG_COMPLIMENTARY.md)).

## Success criteria (define before building)

- A new analysis for `(champion, rank, dominant gap)` retrieves prior analyses that share
  **champion + rank tier + dominant gap category** in its top-k (programmatic relevance
  label).
- End-to-end coaching output scored by an LLM-as-judge rubric improves over the cold-prompt
  baseline on at least one dimension (relevance / factuality / completeness) with no
  regression on the others.
- The harness is reproducible: same config hash → same JSON results.

## Rejected alternative (the senior tell)

**Standalone semantic search over match history** ("find similar games", "patterns in my
losses"). Rejected because:

- It is a **net-new feature disconnected** from the existing pipeline.
- It has **no real baseline** — there is no keyword/SQL match-search today, so any
  pre-RAG number would be invented solely to beat.
- The corpus is small (~245 matches, ~1 user), so precision@k / recall@k would **saturate
  or measure noise**, making the headline metric misleading.

The few-shot route reuses existing infra (`LLMAnalysis` payloads,
[Match.to_embedding_text()](../services/api/app/models/match.py#L41), installed pgvector),
has a baseline that genuinely exists (today's cold prompt), and tells a stronger story:
*"I used RAG to improve an existing ML+LLM pipeline's output, measured on answer quality."*

---

## Plan (3 phases, ~5-7 days)

### Phase 1 — Eval harness first (Days 1-2)

Build the measurement scaffold **before** any retrieval.

- `evals/` directory with:
  - ~30-50 hand-labeled cases drawn from real `LLMAnalysis` records.
  - Hand-written metrics in ~80 lines (no library): **precision@k, recall@k, MRR,
    latency p50/p95, cost per query**. Writing them yourself keeps them explainable.
  - Programmatic ground truth for retrieval: a retrieved example is **relevant** if it
    shares `champion_id` + `rank_tier` + dominant gap category with the query.
  - `pytest evals/` entry point + results written to timestamped JSON keyed by a **config
    hash** so runs are comparable.
  - A markdown results-table generator (regenerated on every change).
- **Baseline run = today's cold Step-7 prompt.** This number already exists — capture it
  as the pre-RAG line in the results table.

**Artifact:** `evals/` harness + labeled set (or regeneration script) + a baseline results
file (cold-prompt numbers).

### Phase 2 — Baseline RAG: few-shot retrieval into Step 7 (Days 3-4)

Build the simplest retrieval that works. No reranking, no hybrid.

- **Add `embedding` vector column to `LLMAnalysis`** + Alembic migration with an IVFFlat
  or HNSW cosine index. ⚠️ **Ask before doing** — touches `app/models/llm_analysis.py`
  and `alembic/versions/` (AGENTS.md boundary).
- Embed at persist time (Step 8) using `text-embedding-3-small`. Document the choice:
  cheap, fast, 1536 dims. Add `embed()` to the `LLMClient` protocol in
  `app/services/llm_client.py`. ⚠️ Confirm whether this counts as a new dependency surface.
- One-time backfill script for existing rows where `embedding IS NULL`.
- Add **Step 6.5 retrieval** in `app/jobs/llm_analysis.py`: embed the comparison context,
  cosine top-k filtered to the same champion, return top-3.
- Inject into `build_user_prompt()` (`app/services/llm_prompt.py`) via an optional
  `few_shot_examples` parameter.
- Run the harness. Record as the RAG baseline (retrieval metrics + LLM-judge quality).

**Artifact:** Working few-shot pipeline + results table: cold-prompt vs few-shot.

### Phase 3 — Two measured experiments + writeup (Days 5-7)

Depth over breadth — pick **two**, not four. Each is hypothesis → experiment →
measurement → conclusion (keep the failures).

Candidates (choose 2):
- **Metadata pre-filter** by champion + rank before vector search.
- **Reranking** top-20 → top-3 (cross-encoder or LLM-as-judge), measure latency cost vs
  quality gain.
- **LLM-as-judge quality pass** on the end-to-end coaching output with a structured rubric
  (relevance / factuality / completeness, 1-5 each); spot-check 10-20 judgments against
  your own to calibrate.

**Artifact:** README section + `docs/rag-deep-dive.md` with the experiments log, results
table, 2-3 quotable numbers, and **one** forward-looking paragraph on productionization
(Redis embedding cache + hit rate, cost/query tracking, latency budget) — described, not
all built.

---

## Key files to touch

| File | Change |
|------|--------|
| `evals/` (new) | Harness, labeled set, metrics, results generator |
| `app/models/llm_analysis.py` | Add `embedding` vector column ⚠️ ask first |
| `alembic/versions/` (new) | Migration: vector column + cosine index ⚠️ ask first |
| `app/services/llm_client.py` | Add `embed()` to `LLMClient` protocol |
| `app/jobs/llm_analysis.py` | Step 6.5 retrieval; embed after Step 8 persist |
| `app/services/llm_prompt.py` | `build_user_prompt()` accepts `few_shot_examples` |
| `scripts/` (new) | One-time embedding backfill |

## Ask-before-doing (AGENTS.md boundaries)

- New `LLMAnalysis` model field.
- New Alembic migration.
- Confirm `openai` embeddings don't introduce an unwanted dependency surface.

Do not start coding these without sign-off.

## When to start

Per [LLM_RAG_COMPLIMENTARY.md](LLM_RAG_COMPLIMENTARY.md): few-shot retrieval is meaningful
once there are **~50+ `LLMAnalysis` records per champion/rank bucket**. If the corpus is
thinner than that, generate analyses first (or document the small-N honestly in the
writeup and treat the harness itself as the deliverable).

## Verification

- `make test` (backend) stays green; add eval-harness tests under `services/api` or a
  dedicated `evals/` target.
- `make lint` clean (pre-existing import-sort warnings acceptable).
- Reproducibility: run `pytest evals/` twice; identical JSON for a fixed config hash
  (embeddings cached or seeded).
- End-to-end: run `llm_analysis_job` for a known account/champion with and without
  retrieval; diff the two `output_payload`s and confirm the harness records a quality
  delta and a latency/cost delta.
