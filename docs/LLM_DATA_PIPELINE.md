# LLM Data Pipeline Outline

## Pipeline Steps

1.  **Ingest**: fetch match list, detail, and timeline from Riot API and store raw JSON. Transiently cache timeline payloads (~1MB) to save storage.
2.  **Normalize**: map Riot payload into a stable `MatchSummary` schema.
3.  **State Reconstruction**: Parse `participantFrames` and `events` to build time-indexed state vectors ($X$) and extract discrete actions ($a$) per participant.
4.  **Action Joining**: Join each event to its surrounding frame snapshots (with interpolation) to extract the pre-action state ($x$) and post-action state ($z$).
5.  **Contextualize**: Apply a Win Probability Model $w(x)$ to compute Win Probability Added ($\Delta W$) for each action: $\Delta W(d) = w(z) - w(x)$. Compute mean initial win probability $W_X(a)$ to detect selection bias.
6.  **Redact**: remove PII, secrets, and large raw timeline data before any LLM call. Keep only the computed contextual events.
7.  **Validate**: enforce schema and size limits (Zod/Ajv).
8.  **Cache**: store normalized summary and aggregated $\Delta W$ statistics with TTL for reuse.
9.  **Enrich**: attach champion metadata from the champions table.
10. **Submit**: send context-enriched summary (aggregated $\Delta W$ statistics) with prompt + schema version to the LLM.
11. **Store result**: persist LLM output with trace IDs and metadata.
12. **Observe**: log request IDs, latency, token counts, error rates.
13. **Review**: add manual review flags for sensitive outputs.

## Game State Vector (X) Reconstruction

The thesis framework relies on reconstructing the game state from timeline data. For every snapshot interval, map the following features from `participantFrames` and `events`:

- **Position (2D)**: `position.x`, `position.y` per participantFrame
- **Level**: `level` per participantFrame
- **Gold (cumulative)**: `totalGold` per participantFrame
- **Damage Dealt**: `damageStats.totalDamageDoneToChampions`
- **Damage Taken**: `damageStats.totalDamageTaken`
- **Kills/Deaths/Assists**: Derived from `CHAMPIONKILL` events
- **Dragons/Barons**: Derived from `ELITEMONSTERKILL` events
- **Turrets Destroyed**: Derived from `BUILDINGKILL` events
- **Time**: `timestamp`

Interpolation is required between the 1-minute `participantFrames` snapshots to accurately estimate the state at the exact timestamp of an event.

## Action ($\Delta W$) Processing

Compute $\Delta W$ for specific action types by defining the pre-action ($x$) and post-action ($z$) states:

- **Item Purchases**: Action ($a$) is `ITEMPURCHASED`. ($x$) is the state just before purchase. ($z$) is the next `ITEMDESTROYED`, `ITEMUNDO`, or terminal state. `ITEMUNDO` events are key signals of players correcting suboptimal decisions.
- **Objective Kills (Dragon/Baron/Herald)**: Action ($a$) is `ELITEMONSTERKILL`. ($x$) is the state before the kill. ($z$) is the state ~3-5 minutes later (the objective's effective buff window).
- **Champion Kill Decisions**: Action ($a$) is `CHAMPIONKILL`. ($x$) is the state just before the fight. ($z$) is the state after the death timer expires (creating a window of opportunity).
- **Skill Leveling Order**: Action ($a$) is `SKILLLEVELUP`. ($x$) is the state at the level-up decision. ($z$) is the state at the next level-up.
- **Ward Placements**: Action ($a$) is `WARDPLACED`. ($x$) is the pre-ward state. ($z$) is the state when the ward expires or is killed.

## Win Probability Model Integration

A model $w(x)$ (e.g., a lightweight logistic regression or a deeper neural network) is required to score states efficiently.

- Calculate $\Delta W(d) = w(z) - w(x)$ to measure the contextualized value of an action.
- Compute $W_X(a)$, the mean initial win probability. Flag actions with high $W$ but low $\Delta W$ (safe but low-impact) or low $W$ but positive $\Delta W$ (high-value comeback plays).
- Feed aggregated $\Delta W$ statistics to the LLM (as single-match data lacks statistical significance without broader aggregation).

## Redaction Checklist

- Remove summoner name, account ID, PUUID, email.
- Remove internal IDs not required for analysis.
- Drop raw timeline data (1MB+ payloads) after extracting state vectors and events to prevent LLM context bloat.
- Never include API keys, tokens, or raw Riot payloads.

## Notes

- Keep the LLM payload minimal and versioned.
- Store the schema version with every LLM response.
