## App Flow Recommendations (Post Sign-In)

### Reliability and safety
- Replace `eval(game_info)` with safe JSON serialization and parsing in `MatchesController#show`.
- Handle null `User` responses on sign-in and show a clear error state in the UI.
- Add request timeouts and error handling for all `fetch()` calls.
- Guard against empty `matches` arrays before indexing in `SoloStats.fetchMatchInfo()`.
- Avoid `componentWillUpdate` (deprecated) and move redirect logic to `componentDidUpdate`.

### Performance and rate limits
- Batch match detail requests where possible (or reduce to a smaller initial count).
- Cache champion data in the frontend or preload `/champions` once per session.
- Add pagination or lazy loading for matches instead of always fetching 20.
- Throttle rank/match fetches to avoid Riot API rate limits.

### Observability
- Add structured logging for each request/response pair in the frontend.
- Log backend request durations and upstream Riot API failures.
- Add a request correlation id passed from frontend to backend for tracing.

### Data and security
- Move API keys to environment variables and rotate existing keys.
- Avoid storing `game_info` as a string; store JSON or a normalized schema.
- Validate `params[:id]` and `params[:summonerName]` on the server.
