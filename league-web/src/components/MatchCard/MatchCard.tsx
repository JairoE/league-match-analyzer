"use client";
/*
 * eslint-disable @next/next/no-img-element
 *
 * This file intentionally uses <img> (not <Image>) for external DDragon CDN
 * assets (items, spells, rune icons, champion thumbnails). These elements
 * require onError handlers for graceful hidden-fallback when an asset 404s,
 * and the DDragon domain is not listed in next.config.ts remotePatterns.
 * Adding the domain is deferred until we add a full Image optimization pass.
 */
/* eslint-disable @next/next/no-img-element */

import {memo, useMemo} from "react";
import Image from "next/image";
import styles from "./MatchCard.module.css";
import type {Champion} from "../../lib/types/champion";
import type {ChampionKdaPoint, LaneStats, MatchDetail, MatchSummary, Participant} from "../../lib/types/match";
import type {RankInfo} from "../../lib/types/rank";
import type {UserSession} from "../../lib/types/user";
import {
  calculateKillParticipation,
  formatGameDuration,
  formatRelativeTime,
  getAlliedTeam,
  getCsPerMinute,
  getDamageRankPosition,
  getEnemyTeam,
  getKdaRatio,
  getMatchId,
  getMatchOutcome,
  getParticipantByPuuid,
  getParticipantForUser,
  getTotalCs,
  ordinalSuffix,
} from "../../lib/match-utils";
import {getQueueMode, getQueueModeLabel} from "../../lib/types/queue";
import {
  FALLBACK_DDRAGON_VERSION,
  getChampionImageUrl,
  getItemImageUrl,
  getKeystoneImageUrl,
  getRuneStyleIconUrl,
  getSpellImageUrl,
  getSpellLabel,
} from "../../lib/constants/ddragon";
import {BarChart, Bar, Tooltip, XAxis, ResponsiveContainer} from "recharts";
import type {BarShapeProps} from "recharts/types/cartesian/Bar";

// ── Types ─────────────────────────────────────────────────────────────

type MatchCardProps = {
  match: MatchSummary;
  detail: MatchDetail | null;
  champion: Champion | null;
  user: UserSession | null;
  isSearchView?: boolean;
  targetPuuid?: string | null;
  rankByPuuid?: Record<string, RankInfo | null>;
  laneStats?: LaneStats | null;
  championHistory?: ChampionKdaPoint[];
  expanded?: boolean;
};

// ── Sub-component: Item Slot ──────────────────────────────────────────

function ItemSlot({itemId, version}: {itemId: number; version: string}) {
  if (itemId === 0) {
    return <div className={styles.itemSlotEmpty} aria-hidden="true" />;
  }
  return (
    <img
      src={getItemImageUrl(itemId, version)}
      alt={`Item ${itemId}`}
      className={styles.itemSlot}
      width={22}
      height={22}
      loading="lazy"
      onError={(e) => {
        (e.target as HTMLImageElement).style.display = "none";
      }}
    />
  );
}

// ── Sub-component: Teams (memoized — 10 images below the fold) ────────

type TeamsProps = {
  participants: Participant[];
  current: Participant;
  currentPuuid: string | undefined;
  version: string;
  rankByPuuid?: Record<string, RankInfo | null>;
};

const Teams = memo(function Teams({
  participants,
  current,
  currentPuuid,
  version,
  rankByPuuid,
}: TeamsProps) {
  const allied = getAlliedTeam(participants, current);
  const enemy = getEnemyTeam(participants, current);

  function PlayerRow({p}: {p: Participant}) {
    const isSelf = p.puuid != null && p.puuid === currentPuuid;
    const champName = p.championName ?? "Unknown";
    const summonerDisplay =
      p.riotIdGameName ?? p.summonerName ?? p.gameName ?? "Unknown";
    const rankInfo = rankByPuuid && p.puuid ? rankByPuuid[p.puuid] : undefined;
    const rankLabel =
      rankInfo?.tier && rankInfo.rank
        ? `${rankInfo.tier} ${rankInfo.rank}`
        : null;
    return (
      <div
        className={`${styles.teamPlayer} ${isSelf ? styles.teamPlayerSelf : ""}`}
        aria-label={`${champName} played by ${summonerDisplay}`}
      >
        <img
          src={getChampionImageUrl(champName, version)}
          alt={champName}
          className={styles.teamChampIcon}
          width={16}
          height={16}
          loading="lazy"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
        <span className={styles.teamSummonerName}>{summonerDisplay}</span>
        {rankLabel && <span className={styles.rankBadge}>{rankLabel}</span>}
      </div>
    );
  }

  return (
    <div className={styles.teamsColumn}>
      <div className={styles.teamList}>
        {allied.map((p, i) => (
          <PlayerRow key={p.puuid ?? i} p={p} />
        ))}
      </div>
      <div className={styles.teamList}>
        {enemy.map((p, i) => (
          <PlayerRow key={p.puuid ?? i} p={p} />
        ))}
      </div>
    </div>
  );
});

// ── Sub-component: Champion KDA History Chart ─────────────────────────

type ChampionKdaChartProps = {
  history: ChampionKdaPoint[];
  currentMatchId: string | null;
};

function ChampionKdaChart({history, currentMatchId}: ChampionKdaChartProps) {
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
      ? new Date(p.timestamp).toLocaleDateString(undefined, {month: "numeric", day: "numeric"})
      : "",
  }));

  return (
    <div className={styles.kdaChart}>
      <div className={styles.kdaChartLabel}>Champion KDA History</div>
      <ResponsiveContainer width="100%" height={100}>
        <BarChart data={data} margin={{top: 4, right: 0, bottom: 0, left: 0}}>
          <XAxis
            dataKey="date"
            tick={{fontSize: 9, fill: "#6b7280"}}
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
              const entry = props as BarShapeProps & { isCurrent?: boolean; outcome?: string };
              const fill = entry.isCurrent
                ? "#ffffff"
                : entry.outcome === "victory"
                  ? "#60a5fa55"
                  : entry.outcome === "defeat"
                    ? "#f8717155"
                    : "#6b728055";
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

// ── Main Component ────────────────────────────────────────────────────

export default function MatchCard({
  match,
  detail,
  champion,
  user,
  isSearchView = false,
  targetPuuid = null,
  rankByPuuid,
  laneStats,
  championHistory = [],
}: MatchCardProps) {
  // ── Participant resolution ──────────────────────────────────────────
  const participant = useMemo<Participant | null>(
    () =>
      isSearchView
        ? getParticipantByPuuid(detail, targetPuuid)
        : getParticipantForUser(detail, user),
    [detail, isSearchView, targetPuuid, user]
  );

  const participants = detail?.info?.participants ?? [];
  const gameDuration = detail?.info?.gameDuration;
  const currentMatchId = getMatchId(match) ?? null;

  // ── Derived stats ───────────────────────────────────────────────────
  const outcome = getMatchOutcome(participant, gameDuration);
  const kdaRatio = getKdaRatio(participant);
  const totalCs = getTotalCs(participant);
  const csPerMin = getCsPerMinute(participant);
  const killParticipation = calculateKillParticipation(participant, participants);
  const damageRank = getDamageRankPosition(participant, participants);
  const durationStr = formatGameDuration(gameDuration);
  const relativeTime = formatRelativeTime(match.game_start_timestamp ?? undefined);

  // ── Display values ──────────────────────────────────────────────────
  const championName = champion?.name ?? participant?.championName ?? "Unknown Champion";
  const champLevel = participant?.champLevel;
  const imageUrl = champion?.image_url ?? null;
  const queueId = detail?.info?.queueId ?? match.queueId ?? undefined;
  const queueModeLabel = getQueueModeLabel(getQueueMode(queueId));

  // ── Items (slots 0-5 = items, slot 6 = trinket) ─────────────────────
  const itemIds: number[] = [
    participant?.item0 ?? 0,
    participant?.item1 ?? 0,
    participant?.item2 ?? 0,
    participant?.item3 ?? 0,
    participant?.item4 ?? 0,
    participant?.item5 ?? 0,
    participant?.item6 ?? 0,
  ];

  // ── Spells & keystone ───────────────────────────────────────────────
  const spell1Id = participant?.summoner1Id ?? 0;
  const spell2Id = participant?.summoner2Id ?? 0;
  const primaryStyle = participant?.perks?.styles?.find(
    (s) => s.description === "primaryStyle"
  );
  const subStyle = participant?.perks?.styles?.find(
    (s) => s.description === "subStyle"
  );
  const keystonePerkId = primaryStyle?.selections?.[0]?.perk ?? 0;
  const keystoneStyleId = primaryStyle?.style ?? 0;
  const subStyleId = subStyle?.style ?? 0;
  const hasKeystone = keystonePerkId > 0 && keystoneStyleId > 0;
  const hasSubStyle = subStyleId > 0;

  // ── Multikill badges ────────────────────────────────────────────────
  type MultikillEntry = {label: string; count: number; penta: boolean};
  const rawDoubles = participant?.doubleKills ?? 0;
  const rawTriples = participant?.tripleKills ?? 0;
  const rawQuadras = participant?.quadraKills ?? 0;
  const rawPentas  = participant?.pentaKills  ?? 0;
  const multikills: MultikillEntry[] = (
    [
      {label: "Double Kill", count: rawDoubles - rawTriples, penta: false},
      {label: "Triple Kill", count: rawTriples - rawQuadras, penta: false},
      {label: "Quadra Kill", count: rawQuadras - rawPentas,  penta: false},
      {label: "Penta Kill",  count: rawPentas,               penta: true},
    ] as MultikillEntry[]
  ).filter((mk) => mk.count > 0);

  // ── Subjective badges ───────────────────────────────────────────────
  const showVictor = outcome === "victory" && ((damageRank > 0 && damageRank <= 3) || kdaRatio > 5);
  const showDownfall = outcome === "defeat" && ((participant?.deaths ?? 0) > 8 || kdaRatio < 1);

  // ── DDragon version ─────────────────────────────────────────────────
  const version = FALLBACK_DDRAGON_VERSION;

  // ── Outcome → CSS modifier ──────────────────────────────────────────
  const outcomeClass =
    outcome === "victory"
      ? styles.cardVictory
      : outcome === "defeat"
        ? styles.cardDefeat
        : styles.cardRemake;

  const textQueueClass =
    outcome === "victory"
      ? styles.textBlue
      : outcome === "defeat"
        ? styles.textRed
        : styles.textGray;

  const outcomeLabel =
    outcome === "victory" ? "Victory" : outcome === "defeat" ? "Defeat" : "Remake";

  const currentPuuid = isSearchView
    ? (targetPuuid ?? undefined)
    : (user?.riot_account?.puuid ?? undefined);

  // ── Laning stat helpers ─────────────────────────────────────────────
  function diffLabel(val: number | null | undefined): string | null {
    if (val == null) return null;
    return val > 0 ? `+${val}` : String(val);
  }

  return (
    <article className={`${styles.card} ${outcomeClass}`}>
      {/* ── Column 1: Game Info ── */}
      <div className={styles.gameInfo}>
        <div className={`${styles.queueType} ${textQueueClass}`}>{queueModeLabel}</div>
        <div className={styles.textGray}>{relativeTime}</div>
        <div className={styles.outcomeLine}>{outcomeLabel}</div>
        <div className={styles.textGray}>{durationStr}</div>
      </div>

      {/* ── Column 2: Player Info (Champ, Spells, KDA, Items) ── */}
      <div className={styles.playerInfo}>
        <div className={styles.playerInfoTop}>
          <div className={styles.championPortrait}>
            {imageUrl ? (
              <Image
                className={styles.championImage}
                src={imageUrl}
                alt={`${championName} level ${champLevel ?? ""}`}
                width={48}
                height={48}
                unoptimized
              />
            ) : (
              <div className={styles.championFallback}>?</div>
            )}
            {champLevel != null && (
              <span className={styles.champLevel}>{champLevel}</span>
            )}
          </div>

          <div className={styles.spellCol}>
            <img
              src={getSpellImageUrl(spell1Id, version)}
              alt={getSpellLabel(spell1Id)}
              className={styles.spellSlot}
              width={20}
              height={20}
              loading="lazy"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
            {hasKeystone ? (
              <img
                src={getKeystoneImageUrl(keystonePerkId, keystoneStyleId)}
                alt="Keystone rune"
                className={styles.keystoneSlot}
                width={20}
                height={20}
                loading="lazy"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            ) : (
              <div className={styles.keystoneEmpty} aria-hidden="true" />
            )}
            <img
              src={getSpellImageUrl(spell2Id, version)}
              alt={getSpellLabel(spell2Id)}
              className={styles.spellSlot}
              width={20}
              height={20}
              loading="lazy"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
            {hasSubStyle ? (
              <img
                src={getRuneStyleIconUrl(subStyleId)}
                alt="Secondary rune style"
                className={styles.keystoneSlot}
                width={20}
                height={20}
                loading="lazy"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            ) : (
              <div className={styles.keystoneEmpty} aria-hidden="true" />
            )}
          </div>

          <div className={styles.kdaBox}>
            <div className={styles.kdaNumbers}>
              <span className={styles.kills}>{participant?.kills ?? "-"}</span>
              <span className={styles.slash}>/</span>
              <span className={styles.deaths}>{participant?.deaths ?? "-"}</span>
              <span className={styles.slash}>/</span>
              <span className={styles.assists}>{participant?.assists ?? "-"}</span>
            </div>
            <div className={styles.kdaRatioText}>{kdaRatio.toFixed(2)}:1 KDA</div>
          </div>
        </div>

        <div className={styles.buildRow}>
          {itemIds.slice(0, 6).map((id, i) => (
            <ItemSlot key={i} itemId={id} version={version} />
          ))}
          <div className={styles.itemSpacer} />
          <ItemSlot itemId={itemIds[6]} version={version} />
        </div>
      </div>

      {/* ── Column 3: Stats & Badges ── */}
      <div className={styles.statsColumn}>
        {killParticipation > 0 && (
          <div className={styles.textGray}>P/Kill {killParticipation}%</div>
        )}
        <div className={styles.textGray}>CS {totalCs} ({csPerMin.toFixed(1)})</div>

        {/* Laning stats (only when timeline data is available) */}
        {laneStats && (
          <div className={styles.laningRow}>
            {diffLabel(laneStats.cs_diff_at_10) != null && (
              <span
                className={`${styles.laningStat} ${
                  (laneStats.cs_diff_at_10 ?? 0) >= 0 ? styles.laningPos : styles.laningNeg
                }`}
              >
                CS@10 {diffLabel(laneStats.cs_diff_at_10)}
              </span>
            )}
            {diffLabel(laneStats.cs_diff_at_15) != null && (
              <span
                className={`${styles.laningStat} ${
                  (laneStats.cs_diff_at_15 ?? 0) >= 0 ? styles.laningPos : styles.laningNeg
                }`}
              >
                CS@15 {diffLabel(laneStats.cs_diff_at_15)}
              </span>
            )}
            {diffLabel(laneStats.gold_diff_at_10) != null && (
              <span
                className={`${styles.laningStat} ${
                  (laneStats.gold_diff_at_10 ?? 0) >= 0 ? styles.laningPos : styles.laningNeg
                }`}
              >
                G@10 {diffLabel(laneStats.gold_diff_at_10)}
              </span>
            )}
          </div>
        )}

        <div className={styles.badgesRow}>
          {multikills.map((mk) =>
            Array.from({length: mk.count}).map((_, i) => (
              <span
                key={`${mk.label}-${i}`}
                className={`${styles.badge} ${mk.penta ? styles.badgeGold : styles.badgeRed}`}
                aria-label={`Achieved ${mk.label}`}
              >
                {mk.label}
              </span>
            ))
          )}
          {damageRank > 0 && participants.length > 0 && (
            <span
              className={`${styles.badge} ${styles.badgeGray}`}
              aria-label={`Damage rank ${ordinalSuffix(damageRank)} of all players`}
            >
              {ordinalSuffix(damageRank)}
            </span>
          )}
          {showVictor && (
            <span className={`${styles.badge} ${styles.badgeGray}`}>Victor</span>
          )}
          {showDownfall && (
            <span className={`${styles.badge} ${styles.badgeGray}`}>Downfall</span>
          )}
        </div>
      </div>

      {/* ── Column 4: Teams ── */}
      {participants.length > 0 && participant && (
        <Teams
          participants={participants}
          current={participant}
          currentPuuid={currentPuuid}
          version={version}
          rankByPuuid={rankByPuuid}
        />
      )}

      {/* ── KDA History Chart (full-width row) ── */}
      {championHistory.length >= 2 && (
        <ChampionKdaChart history={championHistory} currentMatchId={currentMatchId} />
      )}
    </article>
  );
}
