# MatchCard — Remaining Work

All core redesign steps (types, DDragon constants, match utilities, MatchCard UI, CSS) are fully implemented. This document tracks the remaining deferred features.

---

## Step 1 — Per-Player Rank Badges

Show a rank badge (e.g., `Gold 2`) next to each player name in the expanded 10-player team list inside `Teams` (MatchCard.tsx:88–137).

### Backend

`fetch_rank_by_puuid()` already exists. Needs a **batch endpoint** to avoid 10 sequential calls per match:

```
GET /rank/batch?puuids=<csv>
```

- Accepts up to 10 PUUIDs as a comma-separated query param.
- Internally calls `fetch_rank_by_puuid()` concurrently via `asyncio.gather`.
- Returns `Record<puuid, { tier: string; rank: string; lp: number } | null>`.
- Cache key: `rank:{puuid}` — TTL: 1 hour (rank changes slowly).
- Cache at the individual PUUID level so a cache miss for one player doesn't invalidate others.

### Frontend

**Where to call it:** `MatchesTable.tsx` — fetch rank data when a match is expanded (i.e., when `selectedMatchId` changes). Do not fetch proactively for all matches.

**State shape:**
```typescript
// MatchesTable.tsx
const [rankByPuuid, setRankByPuuid] = useState<Record<string, RankInfo | null>>({});
```

**Fetch trigger:** in a `useEffect` keyed on `selectedMatchId`. Extract the 10 PUUIDs from `selectedDetail?.info.participants`, filter out already-cached entries, then call `/rank/batch`.

**Pass down:** `MatchDetailPanel` → `MatchCard` → `Teams` (new prop `rankByPuuid: Record<string, RankInfo | null>`).

**UI in `Teams`:**

```tsx
// MatchCard.tsx — inside PlayerRow
const rank = rankByPuuid[p.puuid ?? ""];
const rankLabel = rank ? `${rank.tier} ${rank.rank}` : null;

// Render next to summonerDisplay
{rankLabel && <span className={styles.rankBadge}>{rankLabel}</span>}
```

**CSS in `MatchCard.module.css`:**
```css
.rankBadge {
  font-size: 10px;
  color: #a78bfa;
  opacity: 0.85;
  white-space: nowrap;
}
```

**Effort:** ~3 hours (batch endpoint + useEffect fetch + UI badge).

---

## Step 2 — Timeline API (Laning Phase Analytics)

Enables CS diff, gold diff, and lane opponent identification at 10 and 15 minutes.

### Backend

**Riot Endpoint:** `GET /lol/match/v5/matches/{matchId}/timeline`

- Timelines are immutable once a match ends → cache indefinitely (`ttl=None` or very long TTL).
- Cache key: `timeline:{matchId}`.
- Store the raw Riot payload in `Match.timeline_info` (new nullable JSONB column alongside the existing `game_info`).
- Or: fetch on-demand and cache in Redis only (no DB storage) if storage is a concern.

**New internal endpoint:**
```
GET /matches/{matchId}/timeline-stats
```
Returns pre-computed laning stats to avoid shipping the full 1MB+ timeline JSON to the client:

```python
class LaneStats(BaseModel):
    cs_diff_at_10: int | None
    cs_diff_at_15: int | None
    gold_diff_at_10: int | None
    gold_diff_at_15: int | None
    lane_opponent_name: str | None
    lane_opponent_champion: str | None
```

**Parsing logic:** In the Riot timeline payload, look at `frames[N].participantFrames[participantId]` for `totalMinionsKilled + neutralMinionsKilled` and `totalGold` at frame index 10 and 15 (each frame = 1 minute). The lane opponent is the participant with the opposite `teamId` and closest `individualPosition`.

### Frontend

- Fetch `/matches/{matchId}/timeline-stats` lazily when a match is expanded (same trigger as rank fetch in Step 1).
- Add `laneStats: LaneStats | null` prop to `MatchCard`.
- Render below the existing stats column or in a new "Laning" row:

```tsx
{laneStats?.cs_diff_at_10 != null && (
  <div className={styles.textGray}>
    CS@10 {laneStats.cs_diff_at_10 > 0 ? "+" : ""}{laneStats.cs_diff_at_10}
  </div>
)}
```

**Effort:** ~5 hours (new DB column or Redis-only caching, timeline parsing, endpoint, frontend integration).

---

## Step 3 — Champion KDA History Chart

For each MatchCard, render a small bar chart showing K/D/A across all loaded matches played on the **same champion**. The current match is highlighted. Gives immediate context: "Is this a typical game for me on this champion?"

This mirrors the rank chart in `wit-take-home/apps/frontend/src/components/PlayerDetailPanel.tsx:176–218` — same `recharts` `BarChart` / `ResponsiveContainer` / `Cell` pattern, adapted for KDA stacked bars.

### Install recharts

```bash
cd league-web && npm install recharts
```

### Data Shape

Define in `league-web/src/lib/types/match.ts`:

```typescript
export type ChampionKdaPoint = {
  matchId: string;
  kills: number;
  deaths: number;
  assists: number;
  outcome: "victory" | "defeat" | "remake";
  timestamp: number; // game_start_timestamp — for ordering
};
```

### Derive Data in `MatchesTable.tsx`

`MatchesTable` already owns all the data needed: `matches`, `matchDetails`, `getParticipantForMatch`. Add a new derived value:

```typescript
// MatchesTable.tsx — new memoized value
const championHistoryByMatchId = useMemo(() => {
  // Group loaded matches by championId → list of KDA points
  const byChampion = new Map<number, ChampionKdaPoint[]>();

  for (const match of matches) {
    const matchId = getMatchId(match);
    if (!matchId) continue;
    const detail = matchDetails[matchId];
    if (!detail) continue; // skip unloaded details
    const p = getParticipantForMatch(match);
    if (!p?.championId) continue;

    const point: ChampionKdaPoint = {
      matchId,
      kills: p.kills ?? 0,
      deaths: p.deaths ?? 0,
      assists: p.assists ?? 0,
      outcome: getMatchOutcome(p, detail.info?.gameDuration),
      timestamp: match.game_start_timestamp ?? 0,
    };
    const existing = byChampion.get(p.championId) ?? [];
    byChampion.set(p.championId, [...existing, point]);
  }

  // Sort each group oldest→newest and map by matchId for O(1) lookup
  const result: Record<string, ChampionKdaPoint[]> = {};
  for (const match of matches) {
    const matchId = getMatchId(match);
    if (!matchId) continue;
    const p = getParticipantForMatch(match);
    if (!p?.championId) continue;
    const history = byChampion.get(p.championId);
    if (history && history.length > 1) {
      result[matchId] = [...history].sort((a, b) => a.timestamp - b.timestamp);
    }
  }
  return result;
}, [matches, matchDetails, getParticipantForMatch]);
```

Pass `championHistory={championHistoryByMatchId[matchId] ?? []}` to `MatchDetailPanel` → `MatchCard`.

### New Prop on `MatchCard`

```typescript
// MatchCard.tsx — extend MatchCardProps
type MatchCardProps = {
  // ... existing props
  championHistory?: ChampionKdaPoint[]; // KDA points for this champion, sorted oldest→newest
};
```

### Chart Component (inside `MatchCard.tsx`)

Add a new `ChampionKdaChart` sub-component. Only renders when `championHistory.length >= 2`.

The chart shows one bar per match. Each bar is **stacked KDA** (kills on top, assists in middle, deaths at bottom — or use separate bars per K/D/A). The **current match** bar is highlighted white; others use muted outcome-tinted colors.

```tsx
import {BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip} from "recharts";
import type {ChampionKdaPoint} from "../lib/types/match";

type ChampionKdaChartProps = {
  history: ChampionKdaPoint[];
  currentMatchId: string;
};

function ChampionKdaChart({history, currentMatchId}: ChampionKdaChartProps) {
  if (history.length < 2) return null;

  const data = history.map((point) => ({
    matchId: point.matchId,
    kills: point.kills,
    deaths: point.deaths,
    assists: point.assists,
    kda: (point.kills + point.assists) / Math.max(1, point.deaths),
    isCurrent: point.matchId === currentMatchId,
    outcome: point.outcome,
  }));

  return (
    <div className={styles.kdaChart}>
      <div className={styles.kdaChartLabel}>Champion KDA History</div>
      <ResponsiveContainer width="100%" height={80}>
        <BarChart data={data} margin={{top: 4, right: 0, left: 0, bottom: 0}} barCategoryGap="10%">
          <XAxis dataKey="matchId" hide />
          <YAxis hide />
          <Tooltip
            content={({active, payload}) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload;
              return (
                <div className={styles.kdaTooltip}>
                  {d.kills}/{d.deaths}/{d.assists}
                </div>
              );
            }}
          />
          <Bar dataKey="kda" radius={[2, 2, 0, 0]} maxBarSize={20}>
            {data.map((entry, i) => (
              <Cell
                key={i}
                fill={
                  entry.isCurrent
                    ? "#ffffff"
                    : entry.outcome === "victory"
                      ? "#60a5fa55"
                      : entry.outcome === "defeat"
                        ? "#f8717155"
                        : "#6b728055"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### CSS in `MatchCard.module.css`

```css
.kdaChart {
  grid-column: 1 / -1; /* full width below the 4 columns */
  padding: 4px 8px 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.kdaChartLabel {
  font-size: 10px;
  color: #6b7280;
  margin-bottom: 2px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.kdaTooltip {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: #f8fafc;
}
```

### Wire into `MatchCard` JSX

Add at the bottom of `<article>`, after the `Teams` column:

```tsx
{/* ── KDA History Chart ── */}
{championHistory && championHistory.length >= 2 && (
  <ChampionKdaChart
    history={championHistory}
    currentMatchId={getMatchId(match) ?? ""}
  />
)}
```

**Notes:**
- Chart only appears when ≥2 matches are loaded for that champion — graceful progressive enhancement.
- No backend changes needed — all data already exists in `matchDetails`.
- `getMatchId` is already imported in `MatchCard.tsx`'s parent; import it in `MatchCard` too.
- The chart is **below** the 4-column layout, not replacing any column. The `card` CSS grid needs `grid-template-rows: auto auto` to accommodate it.

**Effort:** ~3 hours (install recharts, derive data in MatchesTable, ChampionKdaChart sub-component, CSS).

---

## Step 4 — Live Game Integration

Show a live game indicator when the searched summoner is currently in-game.

**Riot Endpoint:** `GET /lol/spectator/v5/active-games/by-summoner/{encryptedSummonerId}`

- Poll every 30 seconds (not continuously streaming — Riot doesn't support SSE on spectator).
- Cache TTL: 30 seconds. 404 = not in game.
- Separate `LiveGameCard` component — do not modify `MatchCard` for this.
- Use a WebSocket or server-sent events for the frontend polling to avoid repeated HTTP calls.

**Effort:** ~8–10 hours (new polling architecture, LiveGameCard component, spectator data parsing). Remains lowest priority.
