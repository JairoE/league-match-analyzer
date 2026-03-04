"use client";

import React, {useMemo, useState, useCallback} from "react";
import styles from "./MatchesTable.module.css";
import MatchRow from "../MatchRow/MatchRow";
import MatchDetailPanel from "../MatchDetailPanel/MatchDetailPanel";
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

type MatchesTableProps = {
  matches: MatchSummary[];
  matchDetails: Record<string, MatchDetail>;
  user: UserSession | null;
  isSearchView?: boolean;
  targetPuuid?: string | null;
  isLoading?: boolean;
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
  paginationMeta = null,
  onPageChange,
}: MatchesTableProps) {
  const {expandedMatchIds, toggleMatch, closeMatch, clearAll} = useMatchSelection();
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
    expandedMatchIds,
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

  // Filter matches by active tab
  const filteredMatches = useMemo(() => {
    if (activeTab === "all") return matches;
    return matches.filter((match) => {
      const queueId = resolveQueueId(match);
      return getQueueGroup(queueId) === activeTab;
    });
  }, [matches, resolveQueueId, activeTab]);

  // Build KDA history per champion, keyed by matchId.
  // Only includes matches whose details have loaded; only entries with 2+ games on the champion are stored.
  const championHistoryByMatchId = useMemo<Record<string, ChampionKdaPoint[]>>(() => {
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
  }, [matches, matchDetails, getParticipantForMatch]);

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
                const isExpanded = matchId ? expandedMatchIds.has(matchId) : false;
                const participant = getParticipantForMatch(match);
                const championId = participant?.championId ?? null;
                const champion =
                  championId != null ? (championById[championId] ?? null) : null;
                const laneStats = matchId ? (laneStatsByMatchId[matchId] ?? null) : null;
                const championHistory = matchId
                  ? (championHistoryByMatchId[matchId] ?? [])
                  : [];

                return (
                  <React.Fragment key={matchId ?? `match-${index}`}>
                    <MatchRow
                      match={match}
                      detail={detail}
                      user={user}
                      isSearchView={isSearchView}
                      targetPuuid={targetPuuid}
                      isSelected={isExpanded}
                      index={index}
                      championById={championById}
                      onClick={() => matchId && toggleMatch(matchId)}
                    />
                    {isExpanded && matchId && (
                      <tr>
                        <td colSpan={COLUMNS.length} className={styles.panelCell}>
                          <MatchDetailPanel
                            match={match}
                            detail={detail}
                            champion={champion}
                            user={user}
                            isSearchView={isSearchView}
                            targetPuuid={targetPuuid}
                            rankByPuuid={rankByPuuid}
                            laneStats={laneStats}
                            championHistory={championHistory}
                            onClose={() => closeMatch(matchId)}
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <div>
        {paginationMeta && onPageChange && (
          <Pagination meta={paginationMeta} onPageChange={onPageChange} />
        )}
      </div>
    </div>
  );
}
