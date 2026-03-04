# MatchCard — Remaining Work

All core redesign steps (types, DDragon constants, match utilities, MatchCard UI, CSS) are fully implemented. This document tracks the remaining deferred features.

---

## Step 1 — Champion KDA History Chart

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
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Cell,
  Tooltip,
} from "recharts";
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
        <BarChart
          data={data}
          margin={{top: 4, right: 0, left: 0, bottom: 0}}
          barCategoryGap="10%"
        >
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
{
  /* ── KDA History Chart ── */
}
{
  championHistory && championHistory.length >= 2 && (
    <ChampionKdaChart
      history={championHistory}
      currentMatchId={getMatchId(match) ?? ""}
    />
  );
}
```

**Notes:**

- Chart only appears when ≥2 matches are loaded for that champion — graceful progressive enhancement.
- No backend changes needed — all data already exists in `matchDetails`.
- `getMatchId` is already imported in `MatchCard.tsx`'s parent; import it in `MatchCard` too.
- The chart is **below** the 4-column layout, not replacing any column. The `card` CSS grid needs `grid-template-rows: auto auto` to accommodate it.

**Effort:** ~3 hours (install recharts, derive data in MatchesTable, ChampionKdaChart sub-component, CSS).

---

## Step 2 — Live Game Integration

Show a live game indicator when the searched summoner is currently in-game.

**Riot Endpoint:** `GET /lol/spectator/v5/active-games/by-summoner/{encryptedSummonerId}`

- Poll every 30 seconds (not continuously streaming — Riot doesn't support SSE on spectator).
- Cache TTL: 30 seconds. 404 = not in game.
- Separate `LiveGameCard` component — do not modify `MatchCard` for this.
- Use a WebSocket or server-sent events for the frontend polling to avoid repeated HTTP calls.

**Effort:** ~8–10 hours (new polling architecture, LiveGameCard component, spectator data parsing). Remains lowest priority.
