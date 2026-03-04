"use client";

import React, {useEffect, useMemo, useState, useCallback} from "react";
import styles from "./MatchesTable.module.css";
import MatchRow from "./MatchRow";
import MatchDetailPanel from "./MatchDetailPanel";
import Pagination from "./Pagination";
import {apiGet} from "../lib/api";
import {
  getMatchId,
  getParticipantByPuuid,
  getParticipantForUser,
} from "../lib/match-utils";
import type {Champion} from "../lib/types/champion";
import type {LaneStats, MatchDetail, MatchSummary, PaginationMeta, Participant} from "../lib/types/match";
import type {RankBatchResponse, RankInfo} from "../lib/types/rank";
import type {UserSession} from "../lib/types/user";
import {
  GameQueueGroup,
  getQueueGroup,
  getQueueGroupLabel,
  QUEUE_GROUP_DISPLAY_ORDER,
} from "../lib/types/queue";

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

const COLUMNS: {key: string; label: string; colWidth: string}[] = [
  {key: "queueType", label: "Queue Type", colWidth: "120px"},
  {key: "champion", label: "Champion", colWidth: "180px"},
  {key: "result", label: "Result", colWidth: "80px"},
  {key: "kda", label: "KDA", colWidth: "80px"},
  {key: "csMin", label: "CS/min", colWidth: "80px"},
  {key: "lane", label: "Lane", colWidth: "100px"},
  {key: "role", label: "Role", colWidth: "100px"},
  {key: "date", label: "Date", colWidth: "120px"},
];

function SkeletonRows({count, colCount}: {count: number; colCount: number}) {
  return (
    <>
      {Array.from({length: count}, (_, i) => (
        <tr
          key={i}
          className={i % 2 === 0 ? styles.rowEven : styles.rowOdd}
        >
          {Array.from({length: colCount}, (_, j) => (
            <td key={j} className={styles.cell}>
              <div className={styles.skeletonCell} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

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
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<GameQueueGroup | "all">("all");
  const [championById, setChampionById] = useState<Record<number, Champion>>({});
  const [rankByPuuid, setRankByPuuid] = useState<Record<string, RankInfo | null>>({});
  const [laneStatsByMatchId, setLaneStatsByMatchId] = useState<Record<string, LaneStats | null>>({});

  const handleRowClick = useCallback((matchId: string) => {
    setSelectedMatchId((prev) => (prev === matchId ? null : matchId));
  }, []);

  const handleClosePanel = useCallback(() => setSelectedMatchId(null), []);

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
      if (typeof championId === "number") {
        ids.add(championId);
      }
    }
    return Array.from(ids);
  }, [getParticipantForMatch, matches]);

  useEffect(() => {
    const missingIds = championIdsToLoad.filter((id) => championById[id] == null);
    if (missingIds.length === 0) {
      return;
    }

    let isActive = true;

    void Promise.allSettled(
      missingIds.map(async (id) => {
        const champion = await apiGet<Champion>(`/champions/${id}`, {
          cacheTtlMs: 60_000,
        });
        return {id, champion};
      })
    ).then((results) => {
      if (!isActive) return;
      const loaded = results
        .filter((r) => r.status === "fulfilled")
        .map((r) => (r as PromiseFulfilledResult<{id: number; champion: Champion}>).value);
      if (loaded.length === 0) return;
      setChampionById((prev) => {
        const next = {...prev};
        for (const {id, champion} of loaded) {
          next[id] = champion;
        }
        return next;
      });
    });

    return () => {
      isActive = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [championIdsToLoad]);

  // Fetch rank data for all 10 participants when a match is expanded
  useEffect(() => {
    if (!selectedMatchId) return;
    const detail = matchDetails[selectedMatchId];
    if (!detail?.info?.participants) return;

    const puuids = detail.info.participants
      .map((p) => p.puuid)
      .filter((puuid): puuid is string => !!puuid && rankByPuuid[puuid] === undefined);

    if (puuids.length === 0) return;

    let isActive = true;
    void apiGet<RankBatchResponse>(`/rank/batch?puuids=${puuids.join(",")}`, {
      cacheTtlMs: 3_600_000,
    }).then((data) => {
      if (!isActive) return;
      setRankByPuuid((prev) => ({...prev, ...data}));
    }).catch(() => {/* silently ignore rank errors */});

    return () => {
      isActive = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMatchId, matchDetails]);

  // Fetch timeline stats for the selected participant when a match is expanded
  useEffect(() => {
    if (!selectedMatchId) return;
    if (laneStatsByMatchId[selectedMatchId] !== undefined) return;

    const detail = matchDetails[selectedMatchId];
    if (!detail?.info?.participants) return;

    const m = matches.find((x) => getMatchId(x) === selectedMatchId);
    const participant = m ? getParticipantForMatch(m) : null;

    const participantId = participant?.participantId;
    if (!participantId) return;

    let isActive = true;
    void apiGet<LaneStats>(
      `/matches/${selectedMatchId}/timeline-stats?participant_id=${participantId}`
    ).then((data) => {
      if (!isActive) return;
      setLaneStatsByMatchId((prev) => ({...prev, [selectedMatchId]: data}));
    }).catch(() => {
      if (!isActive) return;
      setLaneStatsByMatchId((prev) => ({...prev, [selectedMatchId]: null}));
    });

    return () => {
      isActive = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMatchId, matchDetails]);

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

  const selectedMatch = selectedMatchId
    ? filteredMatches.find((m) => getMatchId(m) === selectedMatchId) ?? null
    : null;
  const selectedDetail = selectedMatchId
    ? (matchDetails[selectedMatchId] ?? null)
    : null;
  const selectedParticipant = selectedMatch
    ? getParticipantForMatch(selectedMatch)
    : null;
  const selectedChampion =
    selectedParticipant?.championId != null
      ? (championById[selectedParticipant.championId] ?? null)
      : null;
  const selectedLaneStats = selectedMatchId
    ? (laneStatsByMatchId[selectedMatchId] ?? null)
    : null;

  return (
    <div className={styles.wrapper}>
      <div className={styles.tabBar}>
        <button
          className={activeTab === "all" ? styles.tabActive : styles.tab}
          onClick={() => {
            setSelectedMatchId(null);
            setActiveTab("all");
          }}
        >
          All
        </button>
        {queueGroups.map((group) => (
          <button
            key={group}
            className={activeTab === group ? styles.tabActive : styles.tab}
            onClick={() => {
              setSelectedMatchId(null);
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
                const detail = matchId
                  ? (matchDetails[matchId] ?? null)
                  : null;
                return (
                  <MatchRow
                    key={matchId ?? `match-${index}`}
                    match={match}
                    detail={detail}
                    user={user}
                    isSearchView={isSearchView}
                    targetPuuid={targetPuuid}
                    isSelected={matchId === selectedMatchId}
                    index={index}
                    championById={championById}
                    onClick={() => matchId && handleRowClick(matchId)}
                  />
                );
              })
            )}
          </tbody>
        </table>

        {selectedMatchId !== null && selectedMatch !== null && (
          <div className={styles.panelOverlay}>
            <MatchDetailPanel
              match={selectedMatch}
              detail={selectedDetail}
              champion={selectedChampion}
              user={user}
              isSearchView={isSearchView}
              targetPuuid={targetPuuid}
              rankByPuuid={rankByPuuid}
              laneStats={selectedLaneStats}
              onClose={handleClosePanel}
            />
          </div>
        )}
      </div>
      <div>
        {paginationMeta && onPageChange && (
          <Pagination meta={paginationMeta} onPageChange={onPageChange} />
        )}
      </div>
    </div>
  );
}
