# RAG Eval Harness

Measures the quality of the few-shot retrieval step (pipeline step 6.5) with
programmatic retrieval metrics and an LLM-as-judge rubric. Kept out of the
normal test suite: `make test` never runs anything here.

## Prerequisites

- Postgres up with migrations applied: `make db-up && make db-migrate`
- A seeded corpus of **10+ embedded `llm_analysis` rows** — check with
  `make corpus-stats`, seed with `make seed-rag-corpus` (score matches first:
  `make score-account-matches RIOT_ID=...`)
- `OPENAI_API_KEY` in `services/api/.env` (judge eval only)

## Running

```bash
make evals                      # both evals, verbose
RUN_EVALS=1 pytest evals/       # same thing directly
pytest evals/                   # ungated: only the pure-metric unit tests run
```

Everything degrades to a `skip` with an actionable message when the DB is
down, the corpus is too small, or the API key is missing.

## What gets measured

### `test_retrieval_eval.py` — leave-one-out retrieval metrics

Every embedded `llm_analysis` row takes a turn as the query (its stored
embedding is reused — no embedding spend). Ground truth is programmatic: a
retrieved example is **relevant** when it shares champion, rank tier, and
dominant improvement-gap category with the query (per
`docs/LLM_PIPELINE_STATUS.md`).

Reported: `precision@k`, `recall@k`, `MRR` (k = `rag_few_shot_limit`),
retrieval latency p50/p95 (ms), and estimated embedding cost per query.

### `test_judge_eval.py` — LLM-as-judge rubric

Samples up to 10 queries, retrieves their few-shot sets, and has the LLM
score each set 1–5 on **relevance / factuality / completeness**. Per-case
scores and rationales are stored alongside the aggregates.

## Results

Written to `evals/results/<utc-timestamp>_<config-hash>.json` (gitignored).
The hash covers the eval config (k, models, relevance definition), so runs
with identical configs are directly comparable across time — the intended
use is tracking the metric deltas as the corpus grows and as prompt/RAG
changes land.

## Calibrating the judge

Before trusting judge aggregates:

1. Run the judge eval once and open the newest `*_judge*` results file.
2. For 10–20 cases, score relevance/factuality/completeness yourself
   *before* reading the judge's scores and rationale.
3. Compare. If your scores diverge from the judge's by more than ±1 on an
   axis, tighten that axis's wording in `JUDGE_SYSTEM_PROMPT` (add anchors:
   what a 2 looks like vs a 4) and re-run.
4. Re-check calibration whenever the judge model (`llm_model_name`) changes.
