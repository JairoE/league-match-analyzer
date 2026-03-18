# RAG as a Complement to the ML Pipeline

## Context

The LLM data pipeline (steps 1-8) is complete. It uses a **win probability ML model** to produce quantitative ΔW scores, then feeds structured gap analysis to an LLM for natural language recommendations. This doc outlines how **Retrieval-Augmented Generation (RAG)** can complement — not replace — the existing ML pipeline to improve LLM output quality in Step 7.

## Two Different Kinds of "Vectors"

The pipeline already produces vectors, but they serve a fundamentally different purpose from RAG embeddings:

| | Game State Vectors (Steps 2-4) | RAG Embeddings (proposed for Step 7) |
|---|---|---|
| **What** | Hand-crafted feature dicts (~90 numeric fields per minute) | Dense float arrays (768-1536 dims) from a language model |
| **How made** | Deterministic extraction from Riot timeline JSON | Neural network encodes text into semantic space |
| **Purpose** | Input to win probability model → produces ΔW | Similarity search → retrieves relevant past analyses |
| **Storage** | `match_state_vector.features` (JSONB) | New pgvector column on `llm_analysis` |
| **Query** | Exact lookup by match + minute | Nearest-neighbor cosine similarity |

**The ML model answers:** "How much did buying Kraken Slayer shift win probability?"
**RAG answers:** "What did the LLM recommend last time a Gold Yasuo had this same gap pattern?"

These are complementary — the ML model produces the quantitative signal, RAG improves how the LLM interprets and explains that signal.

## What RAG Would Improve

### Problem: Cold Prompting

Today, Step 7 sends the LLM a statistical summary (ΔW gaps, rankings, bias flags) with zero examples of good output. The LLM generates recommendations from scratch every time, leading to:

- **Inconsistent tone and depth** across analyses for similar situations
- **No learning from prior analyses** — good recommendations are persisted in `llm_analysis` but never reused
- **Generic explanations** — the LLM lacks game-knowledge grounding for *why* an item is statistically better

### Solution: Two RAG Use Cases

#### 1. Few-Shot Example Retrieval (high ROI, near-term)

Embed past `LLMAnalysis` outputs. When a new analysis runs for "Yasuo / GOLD / item builds", retrieve the 2-3 highest-quality prior analyses for similar champion+rank+action_type combos and inject them as few-shot examples in the user prompt.

**What this gives you:**
- Consistent recommendation structure and depth
- The LLM sees concrete examples of good output to pattern-match against
- Quality improves over time as the corpus grows

**Data source:** Already exists — `llm_analysis.output_payload` and `llm_analysis.recommendations` are persisted in Step 8.

#### 2. Game Knowledge Grounding (medium ROI, later)

Embed external game knowledge: patch notes, champion guides, item synergy descriptions. When the comparison step identifies a gap like "Infinity Edge → Kraken Slayer", retrieve context about *why* Kraken Slayer is statistically better (e.g., "Kraken Slayer's true damage proc synergizes with Yasuo's attack speed scaling").

**What this gives you:**
- Grounded explanations instead of vague statistical commentary
- Patch-aware recommendations (the LLM knows what changed in 14.10)
- Domain-specific language that players recognize

**Data source:** Would need to ingest patch notes from Riot and/or community sources.

## What Already Exists

Infrastructure scaffolding is partially in place:

- `pgvector>=0.3.6` in `pyproject.toml` (dependency installed)
- `Match.to_embedding_text()` method exists in `app/models/match.py` (unused)
- PostgreSQL 16 with pgvector extension (in `docker-compose.yml`)
- `LLMAnalysis` records accumulating in the DB with full input/output payloads

## Implementation Plan

### Phase 1: Few-Shot Retrieval (recommended first)

**Prerequisite:** ~50+ `LLMAnalysis` records per champion/rank bucket.

#### Step 1: Add embedding column to `llm_analysis`

```python
# New column on LLMAnalysis model
from pgvector.sqlalchemy import Vector

embedding: list[float] | None = Field(
    default=None,
    sa_column=Column(Vector(1536), nullable=True),
)
```

Migration adds the column + an IVFFlat or HNSW index for cosine similarity.

#### Step 2: Generate embeddings at persist time (Step 8)

After persisting the `LLMAnalysis` record, generate an embedding from a text representation of the analysis context:

```
Embedding text = f"{champion_name} {rank_tier} | "
    + top improvement gaps (action_key, delta_w_gap)
    + selection bias flags
```

Use `text-embedding-3-small` (OpenAI) — cheap, fast, 1536 dims. This runs inline in `llm_analysis_job` after Step 8 persist, or as a lightweight post-persist hook.

#### Step 3: Retrieve similar analyses before Step 7

Between Step 6 (Compare) and Step 7 (Prompt LLM), add a retrieval step:

```python
# Pseudo-code for the retrieval step
query_text = build_embedding_text(champion_name, rank_tier, comparison)
query_embedding = await embed(query_text)

similar_analyses = await session.execute(
    select(LLMAnalysis)
    .where(LLMAnalysis.champion_name == champion_name)
    .order_by(LLMAnalysis.embedding.cosine_distance(query_embedding))
    .limit(3)
)
```

Filter to same champion (exact match) — the embedding similarity handles rank/action similarity.

#### Step 4: Inject into user prompt

Modify `build_user_prompt()` in `llm_prompt.py` to accept an optional `few_shot_examples` parameter:

```
Here are examples of high-quality analyses for similar situations:

Example 1 (Yasuo, GOLD):
{prior_analysis.output_payload}

Example 2 (Yasuo, SILVER):
{prior_analysis.output_payload}

Now analyze the following gap analysis:
{current_comparison}
```

#### Step 5: Backfill embeddings for existing records

One-time script to generate embeddings for all existing `LLMAnalysis` rows that have `embedding IS NULL`.

### Phase 2: Game Knowledge Grounding (future)

#### Step 1: Create a `game_knowledge` table

```sql
CREATE TABLE game_knowledge (
    id UUID PRIMARY KEY,
    source TEXT NOT NULL,          -- 'patch_notes', 'item_guide', 'champion_guide'
    source_version TEXT,           -- e.g. '14.10', 'Season 2025'
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL
);
```

#### Step 2: Ingest sources

- **Patch notes:** Riot publishes patch notes at known URLs; parse and chunk by section
- **Item data:** Data Dragon already provides item descriptions (`load_item_name_map()` fetches this); embed the full item descriptions including passive/active effects
- **Champion synergies:** Community wikis or manually curated champion-item synergy descriptions

#### Step 3: Retrieve relevant knowledge before Step 7

When the comparison identifies specific items or objectives, embed the gap context and retrieve relevant game knowledge chunks. Inject as grounding context in the system or user prompt.

### Pipeline Flow with RAG

```
Steps 1-4: (unchanged — ML pipeline produces ΔW scores)
    ↓
Step 5 (Aggregate): (unchanged)
    ↓
Step 6 (Compare): (unchanged — produces ComparisonResult)
    ↓
Step 6.5 (Retrieve): NEW — embed comparison context, retrieve:
    a) Similar past LLMAnalysis records (few-shot examples)
    b) Relevant game knowledge chunks (grounding context)
    ↓
Step 7 (Prompt LLM): Enhanced prompt with few-shot examples + grounding
    ↓
Step 8 (Persist): (unchanged + generate embedding for this analysis)
```

## Key Files to Modify

| File | Change |
|------|--------|
| `app/models/llm_analysis.py` | Add `embedding` vector column |
| `app/jobs/llm_analysis.py` | Add retrieval step (6.5), embed after persist (8) |
| `app/services/llm_prompt.py` | Accept + format few-shot examples in user prompt |
| `alembic/versions/` | New migration for vector column + index |
| `app/services/llm_client.py` | Add `embed()` method to `LLMClient` protocol |

## When to Start

| Signal | Action |
|--------|--------|
| < 50 `LLMAnalysis` records per champion/rank | Not yet — cold prompt is fine |
| 50-100 records per bucket | Start Phase 1 — few-shot retrieval will meaningfully improve consistency |
| Recommendations feel generic or lack game context | Start Phase 2 — game knowledge grounding |
| Model retrain changes ΔW distributions significantly | Re-embed existing analyses (embeddings based on gap patterns, not raw ΔW values) |

## What RAG Does NOT Replace

- **The win probability model** — RAG cannot produce ΔW scores. The ML model is the quantitative backbone.
- **Aggregation logic** — Statistical aggregation (K≥50 threshold, population fallback) is deterministic SQL, not a retrieval problem.
- **Comparison ranking** — Ranking actions by ΔW and detecting selection bias is arithmetic, not semantic search.

RAG enhances how the LLM *communicates* insights from the ML pipeline. It does not change the insights themselves.
