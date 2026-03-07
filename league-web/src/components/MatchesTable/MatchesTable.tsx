"use client";

import {useMemo, useState, useCallback, useRef} from "react";
import Image from "next/image";
import styles from "./MatchesTable.module.css";
import MatchRow from "../MatchRow/MatchRow";
import Pagination from "../Pagination/Pagination";
import SkeletonRows from "./SkeletonRows";
import {COLUMNS} from "./constants";
import {useMatchSelection} from "./useMatchSelection";
import {useMatchDetailData} from "./useMatchDetailData";
import {
  getMatchId,
  getMatchOutcome,
  getParticipantByPuuid,
  getParticipantForUser,
} from "../../lib/match-utils";
import type {ChampionKdaPoint, MatchDetail, MatchSummary, PaginationMeta, Participant} from "../../lib/types/match";
import type {UserSession} from "../../lib/types/user";
import {
  GameQueueGroup,
  getQueueGroup,
  getQueueGroupLabel,
  QUEUE_GROUP_DISPLAY_ORDER,
} from "../../lib/types/queue";

// Stable empty array — prevents memo-defeating new references on every render
// for rows whose champion history hasn't loaded yet.
const EMPTY_HISTORY: ChampionKdaPoint[] = [];

type MatchesTableProps = {
  matches: MatchSummary[];
  matchDetails: Record<string, MatchDetail>;
  user: UserSession | null;
  isSearchView?: boolean;
  targetPuuid?: string | null;
  isLoading?: boolean;
  isLoadingMore?: boolean;
  canLoadMore?: boolean;
  onLoadMore?: () => void;
  paginationMeta?: PaginationMeta | null;
  onPageChange?: (page: number) => void;
};

export default function MatchesTable({
  matches,
  matchDetails,
  user,
  isSearchView = false,
  targetPuuid = null,
  isLoading = false,
  isLoadingMore = false,
  canLoadMore = false,
  onLoadMore,
  paginationMeta = null,
  onPageChange,
}: MatchesTableProps) {
  const {selectedMatchId, toggleMatch, closeMatch, clearAll} = useMatchSelection();
  const [activeTab, setActiveTab] = useState<GameQueueGroup | "all">("all");

  /** Resolve queueId from detail or match-level fallback */
  const resolveQueueId = useCallback(
    (match: MatchSummary): number | undefined => {
      const matchId = getMatchId(match);
      const detail = matchId ? matchDetails[matchId] : null;
      const fromDetail = detail?.info?.queueId;
      return typeof fromDetail === "number" ? fromDetail : match.queueId ?? undefined;
    },
    [matchDetails]
  );

  const getParticipantForMatch = useCallback(
    (match: MatchSummary): Participant | null => {
      const matchId = getMatchId(match);
      const detail = matchId ? matchDetails[matchId] : null;
      if (isSearchView) {
        return getParticipantByPuuid(detail, targetPuuid);
      }
      return getParticipantForUser(detail, user);
    },
    [isSearchView, matchDetails, targetPuuid, user]
  );

  const championIdsToLoad = useMemo(() => {
    const ids = new Set<number>();
    for (const match of matches) {
      const participant = getParticipantForMatch(match);
      const championId = participant?.championId;
      if (typeof championId === "number") ids.add(championId);
    }
    return Array.from(ids);
  }, [getParticipantForMatch, matches]);

  const {championById, rankByPuuid, laneStatsByMatchId} = useMatchDetailData({
    selectedMatchId,
    matches,
    matchDetails,
    getParticipantForMatch,
    championIdsToLoad,
  });

  // Derive queue group tabs from data in fixed display order
  const queueGroups = useMemo(() => {
    const groups = new Set<GameQueueGroup>();
    for (const match of matches) {
      const queueId = resolveQueueId(match);
      const group = getQueueGroup(queueId);
      groups.add(group);
    }
    return QUEUE_GROUP_DISPLAY_ORDER.filter((group) => groups.has(group));
  }, [matches, resolveQueueId]);

  // Filter matches by active tab; fall back to "all" when tab has no matches
  const filteredMatches = useMemo(() => {
    if (activeTab === "all") return matches;
    const filtered = matches.filter((match) => {
      const queueId = resolveQueueId(match);
      return getQueueGroup(queueId) === activeTab;
    });
    return filtered.length > 0 ? filtered : matches;
  }, [matches, resolveQueueId, activeTab]);

  // Stable gate for matchSummaryStats: a number that only grows when new match
  // details arrive. matchDetails gets a new object reference on every polling
  // tick, but this count only changes when previously-null entries are filled.
  const loadedDetailCount = useMemo(
    () =>
      filteredMatches.filter((m) => {
        const id = getMatchId(m);
        return id != null && matchDetails[id] != null;
      }).length,
    [filteredMatches, matchDetails],
  );

  // Snapshot ref lets matchSummaryStats read matchDetails from the closure
  // when loadedDetailCount changes, without adding matchDetails to its deps.
  // This prevents the 80-line memo from re-running on every polling tick.
  const matchDetailsRef = useRef(matchDetails);
  matchDetailsRef.current = matchDetails;

  // Summary stats: win rate & best consecutive-win champion
  const matchSummaryStats = useMemo(() => {
    const details = matchDetailsRef.current;
    let wins = 0;
    let total = 0;

    // Track consecutive wins per champion (by championId)
    const streakByChamp: Record<number, {
      current: number;
      best: number;
      name: string | null;
    }> = {};

    // Process in chronological order (oldest first)
    const sorted = [...filteredMatches].sort((a, b) => {
      const tsA = a.game_start_timestamp ?? a.gameCreation ?? 0;
      const tsB = b.game_start_timestamp ?? b.gameCreation ?? 0;
      return tsA - tsB;
    });

    for (const match of sorted) {
      const matchId = getMatchId(match);
      const detail = matchId ? (details[matchId] ?? null) : null;
      const participant = isSearchView
        ? getParticipantByPuuid(detail, targetPuuid)
        : getParticipantForUser(detail, user);
      if (!participant) continue;

      const outcome = getMatchOutcome(participant, detail?.info?.gameDuration);
      if (outcome === "remake") continue;

      total++;
      const isWin = outcome === "victory";
      if (isWin) wins++;

      const champId = participant.championId;
      if (typeof champId !== "number") continue;

      if (!streakByChamp[champId]) {
        streakByChamp[champId] = {
          current: 0,
          best: 0,
          name: participant.championName ?? null,
        };
      }
      const entry = streakByChamp[champId];
      if (isWin) {
        entry.current++;
        if (entry.current > entry.best) {
          entry.best = entry.current;
        }
      } else {
        entry.current = 0;
      }
    }

    // Find champion with highest best streak
    let bestStreakChampId: number | null = null;
    let bestStreakCount = 0;
    let bestStreakName: string | null = null;
    for (const [id, entry] of Object.entries(streakByChamp)) {
      if (entry.best > bestStreakCount) {
        bestStreakCount = entry.best;
        bestStreakChampId = Number(id);
        bestStreakName = entry.name;
      }
    }

    return {wins, total, bestStreakChampId, bestStreakCount, bestStreakName};
    // loadedDetailCount is an intentional gate: it is a derived number that
    // only changes when new match details arrive. matchDetails is read via
    // matchDetailsRef so this memo skips ticks where only the reference
    // changed with no new content (i.e., every 3-second polling tick where
    // no new game_info loaded). ESLint flags loadedDetailCount as
    // "unnecessary" because it is not read inside the body — that is by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredMatches, loadedDetailCount, isSearchView, targetPuuid, user]);

  // Build KDA history per champion, keyed by matchId.
  // Only includes matches whose details have loaded; only entries with 2+ games on the champion are stored.
  // Only computed when a row is expanded — avoids iterating all matches on every detail fetch.
  const championHistoryByMatchId = useMemo<Record<string, ChampionKdaPoint[]>>(() => {
    if (!selectedMatchId) return {};
    const groupByChamp: Record<number, ChampionKdaPoint[]> = {};

    for (const match of matches) {
      const matchId = getMatchId(match);
      if (!matchId) continue;
      const detail = matchDetails[matchId] ?? null;
      if (!detail) continue;
      const participant = getParticipantForMatch(match);
      const championId = participant?.championId;
      if (typeof championId !== "number") continue;

      if (!groupByChamp[championId]) groupByChamp[championId] = [];
      groupByChamp[championId].push({
        matchId,
        kills: participant?.kills ?? 0,
        deaths: participant?.deaths ?? 0,
        assists: participant?.assists ?? 0,
        outcome: getMatchOutcome(participant, detail?.info?.gameDuration),
        timestamp: match.game_start_timestamp ?? match.gameCreation ?? 0,
      });
    }

    for (const points of Object.values(groupByChamp)) {
      points.sort((a, b) => a.timestamp - b.timestamp);
    }

    const result: Record<string, ChampionKdaPoint[]> = {};
    for (const match of matches) {
      const matchId = getMatchId(match);
      if (!matchId) continue;
      const participant = getParticipantForMatch(match);
      const championId = participant?.championId;
      if (typeof championId !== "number") continue;
      const history = groupByChamp[championId];
      if (history && history.length > 1) result[matchId] = history;
    }
    return result;
  }, [selectedMatchId, matches, matchDetails, getParticipantForMatch]);

  return (
    <div className={styles.wrapper}>
      <div className={styles.tabBar}>
        <button
          type="button"
          className={activeTab === "all" ? styles.tabActive : styles.tab}
          onClick={() => {
            clearAll();
            setActiveTab("all");
          }}
        >
          All
        </button>
        {queueGroups.map((group) => (
          <button
            type="button"
            key={group}
            className={activeTab === group ? styles.tabActive : styles.tab}
            onClick={() => {
              clearAll();
              setActiveTab(group);
            }}
          >
            {getQueueGroupLabel(group)}
          </button>
        ))}
      </div>
      {!isLoading && matchSummaryStats.total > 0 && (
        <div className={styles.summaryBar}>
          <div>
            <span className={styles.summaryLabel}>
              Record{" "}
            </span>
            <span
              className={`${styles.summaryValue} ${styles.summaryWin}`}
            >
              {matchSummaryStats.wins}W
            </span>
            {" "}
            <span
              className={`${styles.summaryValue} ${styles.summaryLoss}`}
            >
              {matchSummaryStats.total - matchSummaryStats.wins}L
            </span>
          </div>
          {matchSummaryStats.bestStreakCount >= 2 && (
            <div className={styles.summaryStreak}>
              <span className={styles.summaryLabel}>
                Best Champion Win Streak{" "}
              </span>
              {matchSummaryStats.bestStreakChampId != null &&
                championById[
                  matchSummaryStats.bestStreakChampId
                ]?.image_url && (
                  <Image
                    className={styles.summaryChampIcon}
                    src={
                      championById[
                        matchSummaryStats.bestStreakChampId
                      ]!.image_url!
                    }
                    alt={
                      matchSummaryStats.bestStreakName ?? ""
                    }
                    width={20}
                    height={20}
                    unoptimized
                  />
                )}
              <span className={styles.summaryValue}>
                {matchSummaryStats.bestStreakName ??
                  "Unknown"}{" "}
                x{matchSummaryStats.bestStreakCount}
              </span>
            </div>
          )}
        </div>
      )}
      <div className={styles.tableContainer}>
        <table className={styles.table}>
          <thead className={styles.thead}>
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={styles.th}
                  style={{width: col.colWidth, minWidth: col.colWidth}}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <SkeletonRows count={8} colCount={COLUMNS.length} />
            ) : filteredMatches.length === 0 ? (
              <tr>
                <td colSpan={COLUMNS.length} className={styles.empty}>
                  No matches found.
                </td>
              </tr>
            ) : (
              filteredMatches.map((match, index) => {
                const matchId = getMatchId(match);
                const detail = matchId ? (matchDetails[matchId] ?? null) : null;
                const isExpanded = matchId ? selectedMatchId === matchId : false;
                const participant = getParticipantForMatch(match);
                const championId = participant?.championId ?? null;
                const champion =
                  championId != null ? (championById[championId] ?? null) : null;
                const laneStats = matchId ? (laneStatsByMatchId[matchId] ?? null) : null;
                // Only pass expensive maps to the one expanded row — prevents
                // rankByPuuid / championHistory new-reference churn from
                // defeating React.memo on all 19 other rows.
                const championHistory = isExpanded && matchId
                  ? (championHistoryByMatchId[matchId] ?? EMPTY_HISTORY)
                  : EMPTY_HISTORY;

                return (
                  <MatchRow
                    key={matchId ?? `match-${index}`}
                    match={match}
                    detail={detail}
                    user={user}
                    isSearchView={isSearchView}
                    targetPuuid={targetPuuid}
                    isSelected={isExpanded}
                    index={index}
                    colCount={COLUMNS.length}
                    champion={champion}
                    rankByPuuid={isExpanded ? rankByPuuid : undefined}
                    laneStats={laneStats}
                    championHistory={championHistory}
                    onClick={() => matchId && toggleMatch(matchId)}
                    onClose={() => matchId && closeMatch(matchId)}
                  />
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {canLoadMore && onLoadMore && (
        <div className={styles.loadMore}>
          <button
            type="button"
            className={styles.loadMoreBtn}
            onClick={onLoadMore}
            disabled={isLoadingMore}
          >
            {isLoadingMore ? "Loading..." : "See more"}
          </button>
        </div>
      )}
      <div>
        {paginationMeta && onPageChange && (
          <Pagination meta={paginationMeta} onPageChange={onPageChange} />
        )}
      </div>
    </div>
  );
}
