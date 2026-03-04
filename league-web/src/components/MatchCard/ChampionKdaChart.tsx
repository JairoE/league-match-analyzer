import {BarChart, Bar, Tooltip, XAxis, ResponsiveContainer} from "recharts";
import type {BarShapeProps} from "recharts/types/cartesian/Bar";
import styles from "./MatchCard.module.css";
import type {ChampionKdaChartProps} from "./types";

export function ChampionKdaChart({history, currentMatchId}: ChampionKdaChartProps) {
  if (history.length < 2) return null;

  const data = history.map((p) => ({
    matchId: p.matchId,
    kda: parseFloat(((p.kills + p.assists) / Math.max(1, p.deaths)).toFixed(2)),
    kills: p.kills,
    deaths: p.deaths,
    assists: p.assists,
    outcome: p.outcome,
    isCurrent: p.matchId === currentMatchId,
    date: p.timestamp
      ? new Date(p.timestamp).toLocaleDateString(undefined, {
          month: "numeric",
          day: "numeric",
        })
      : "",
  }));

  return (
    <div className={styles.kdaChart}>
      <div className={styles.kdaChartLabel}>Champion KDA History</div>
      <ResponsiveContainer width="100%" height={100}>
        <BarChart data={data} margin={{top: 4, right: 0, bottom: 0, left: 0}}>
          <XAxis
            dataKey="date"
            tick={{fontSize: 9, fill: "var(--match-text-muted)"}}
            tickLine={false}
            axisLine={false}
            interval={0}
          />
          <Tooltip
            cursor={{fill: "rgba(255,255,255,0.04)"}}
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
          <Bar
            dataKey="kda"
            radius={[2, 2, 0, 0]}
            shape={(props: BarShapeProps) => {
              const entry = props as BarShapeProps & {
                isCurrent?: boolean;
                outcome?: string;
              };
              const fill = entry.isCurrent
                ? "#ffffff"
                : entry.outcome === "victory"
                  ? "var(--match-bar-victory)"
                  : entry.outcome === "defeat"
                    ? "var(--match-bar-defeat)"
                    : "var(--match-bar-remake)";
              return (
                <rect
                  x={entry.x}
                  y={entry.y}
                  width={entry.width}
                  height={entry.height}
                  fill={fill}
                  rx={2}
                  ry={2}
                />
              );
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
