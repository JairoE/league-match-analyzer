 # LLM Data Pipeline Outline
 
 ## Pipeline Steps
 1. Ingest: fetch match list and match detail from Riot API and store raw JSON.
 2. Normalize: map Riot payload into a stable `MatchSummary` schema.
 3. Redact: remove PII and secrets before any LLM call.
 4. Validate: enforce schema and size limits (Zod/Ajv).
 5. Cache: store normalized summary with TTL for reuse.
 6. Enrich: attach champion metadata from the champions table.
 7. Submit: send only the summary with prompt + schema version.
 8. Store result: persist LLM output with trace IDs and metadata.
 9. Observe: log request IDs, latency, token counts, error rates.
 10. Review: add manual review flags for sensitive outputs.
 
 ## Redaction Checklist
 - Remove summoner name, account ID, PUUID, email.
 - Remove internal IDs not required for analysis.
 - Never include API keys, tokens, or raw Riot payloads.
 
 ## Notes
 - Keep the LLM payload minimal and versioned.
 - Store the schema version with every LLM response.
 
