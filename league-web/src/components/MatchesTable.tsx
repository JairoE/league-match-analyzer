"use client";

import React, {useEffect, useMemo, useState, useCallback} from "react";
import styles from "./MatchesTable.module.css";
import MatchRow from "./MatchRow";
import MatchDetailPanel from "./MatchDetailPanel";
import {getMatchId} from "../lib/match-utils";
import type {MatchDetail, MatchSummary} from "../lib/types/match";
import type {UserSession} from "../lib/types/user";
import {GameQueueGroup, getQueueGroup, getQueueGroupLabel} from "../lib/types/queue";

type MatchesTableProps = {
  matches: MatchSummary[];
  matchDetails: Record<string, MatchDetail>;
  user: UserSession | null;
  isSearchView?: boolean;
  targetPuuid?: string | null;
  isLoading?: boolean;
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
}: MatchesTableProps) {
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<GameQueueGroup | "all">("all");

  const handleRowClick = useCallback((matchId: string) => {
    setSelectedMatchId((prev) => (prev === matchId ? null : matchId));
  }, []);

  const handleClosePanel = useCallback(() => setSelectedMatchId(null), []);

  // Clear panel selection when switching tabs
  useEffect(() => {
    setSelectedMatchId(null);
  }, [activeTab]);

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

  // Derive dynamic queue group tabs from data
  const queueGroups = useMemo(() => {
    const groups = new Set<GameQueueGroup>();
    for (const match of matches) {
      const queueId = resolveQueueId(match);
      const group = getQueueGroup(queueId);
      groups.add(group);
    }
    return Array.from(groups).sort();
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

  return (
    <div className={styles.wrapper}>
      <div className={styles.tabBar}>
        <button
          className={activeTab === "all" ? styles.tabActive : styles.tab}
          onClick={() => setActiveTab("all")}
        >
          All
        </button>
        {queueGroups.map((group) => (
          <button
            key={group}
            className={activeTab === group ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab(group)}
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
              user={user}
              isSearchView={isSearchView}
              targetPuuid={targetPuuid}
              onClose={handleClosePanel}
            />
          </div>
        )}
      </div>
    </div>
  );
}
