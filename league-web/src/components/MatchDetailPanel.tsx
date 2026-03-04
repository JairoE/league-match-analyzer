"use client";

import React from "react";
import styles from "./MatchDetailPanel.module.css";
import MatchCard from "./MatchCard";
import type {Champion} from "../lib/types/champion";
import type {LaneStats, MatchDetail, MatchSummary} from "../lib/types/match";
import type {RankInfo} from "../lib/types/rank";
import type {UserSession} from "../lib/types/user";

type MatchDetailPanelProps = {
  match: MatchSummary;
  detail: MatchDetail | null;
  champion: Champion | null;
  user: UserSession | null;
  isSearchView: boolean;
  targetPuuid: string | null;
  rankByPuuid?: Record<string, RankInfo | null>;
  laneStats?: LaneStats | null;
  onClose: () => void;
};

function PanelSkeleton() {
  return (
    <div>
      <div className={`${styles.skeletonBlock} ${styles.skeletonHeader}`} />
      <div className={`${styles.skeletonBlock} ${styles.skeletonSummary}`} />
      <div className={`${styles.skeletonBlock} ${styles.skeletonSummary}`} />
      <div className={`${styles.skeletonBlock} ${styles.skeletonDetails}`} />
      <div className={`${styles.skeletonBlock} ${styles.skeletonDetails}`} />
      <div className={`${styles.skeletonBlock} ${styles.skeletonDetails}`} />
    </div>
  );
}

export default function MatchDetailPanel({
  match,
  detail,
  champion,
  user,
  isSearchView,
  targetPuuid,
  rankByPuuid,
  laneStats,
  onClose,
}: MatchDetailPanelProps) {
  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelTitle}>Match Details</span>
        <button
          className={styles.closeButton}
          onClick={onClose}
          aria-label="Close match detail"
        >
          ✕
        </button>
      </div>
      <div className={styles.panelBody}>
        {detail === null ? (
          <PanelSkeleton />
        ) : (
          <MatchCard
            match={match}
            detail={detail}
            champion={champion}
            user={user}
            isSearchView={isSearchView}
            targetPuuid={targetPuuid}
            rankByPuuid={rankByPuuid}
            laneStats={laneStats}
            expanded
          />
        )}
      </div>
    </div>
  );
}
