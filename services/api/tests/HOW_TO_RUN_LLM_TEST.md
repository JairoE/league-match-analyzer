# Running the LLM Pipeline Integration Test

Tests step 7 of the LLM pipeline (prompt build + OpenAI call) against real comparison data
captured from a Riot account.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/league_db` |
| `OPENAI_API_KEY` | Required only for the test step, not seeding |
| Matches ingested | The target player must have data in the DB (steps 1–4 complete) |

---

## Step 1 — Ingest the player (if not already done)

Hit the search endpoint to pull matches into the DB:

```
GET http://localhost:8000/search/{riot_id}/matches
```

Replace `{riot_id}` with the target player, e.g. `PlayerName%23TAG`.

---

## Step 2 — Seed the fixture

Pass `RIOT_ID` as an env var (defaults to `damanjr#NA1` if omitted):

```bash
RIOT_ID=PlayerName#TAG \
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/league_db \
    python services/api/tests/seed_llm_fixture.py
```

The script picks the champion with the most recorded games automatically.
To force a specific champion, pass `CHAMPION_ID`:

```bash
RIOT_ID=PlayerName#TAG \
CHAMPION_ID=Jinx \
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/league_db \
    python services/api/tests/seed_llm_fixture.py
```

On success it writes `services/api/tests/fixtures/<riot_id>_comparison.json`
(e.g. `PlayerName_TAG_comparison.json`). The file is overwritten each run.

---

## Step 3 — Run the test

```bash
OPENAI_API_KEY=sk-... pytest services/api/tests/test_llm_pipeline_real_data.py -s -v
```

---

## Troubleshooting

| Error | Fix |
|---|---|
| `No RiotAccount found` | Run step 1 (ingest) for the target player first |
| `compare_action_stats returned None` | Player doesn't have enough scored match data yet |
| Test is SKIPPED | `OPENAI_API_KEY` is unset or the fixture file is missing |
