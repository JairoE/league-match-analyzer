"use client";

import React, {useEffect, useMemo, useState} from "react";
import Image from "next/image";
import styles from "./MatchRow.module.css";
import {apiGet} from "../lib/api";
import type {Champion} from "../lib/types/champion";
import type {MatchDetail, MatchSummary, Participant} from "../lib/types/match";
import type {UserSession} from "../lib/types/user";
import {
  getCsPerMinute,
  getKdaRatio,
  getParticipantByPuuid,
  getParticipantForUser,
} from "../lib/match-utils";
import {getQueueMode, getQueueModeLabel} from "../lib/types/queue";

type MatchRowProps = {
  match: MatchSummary;
  detail: MatchDetail | null;
  user: UserSession | null;
  isSearchView: boolean;
  targetPuuid: string | null;
  isSelected: boolean;
  index: number;
  onClick: () => void;
};

const MatchRow = React.memo(function MatchRow({
  match,
  detail,
  user,
  isSearchView,
  targetPuuid,
  isSelected,
  index,
  onClick,
}: MatchRowProps) {
  const [champion, setChampion] = useState<Champion | null>(null);

  const participant = useMemo<Participant | null>(() => {
    if (isSearchView) {
      return getParticipantByPuuid(detail, targetPuuid);
    }
    return getParticipantForUser(detail, user);
  }, [detail, isSearchView, targetPuuid, user]);

  const championId = participant?.championId ?? null;

  useEffect(() => {
    if (!championId) return;
    let isActive = true;

    apiGet<Champion>(`/champions/${championId}`, {cacheTtlMs: 60_000})
      .then((response) => {
        if (isActive) setChampion(response);
      })
      .catch(() => {});

    return () => {
      isActive = false;
    };
  }, [championId]);

  const kdaRatio = getKdaRatio(participant);
  const csPerMinute = getCsPerMinute(participant);
  const isWin = participant?.win ?? null;
  const championName =
    champion?.name ?? participant?.championName ?? "Unknown";
  const imageUrl =
    champion?.imageUrl ??
    champion?.image_url ??
    champion?.iconUrl ??
    champion?.icon_url ??
    null;

  const queueId = detail?.info?.queueId ?? match.queueId ?? undefined;
  const queueModeLabel = getQueueModeLabel(getQueueMode(queueId));

  const formattedDate = useMemo<string | null>(() => {
    const timestamp = match.game_start_timestamp;
    if (!timestamp) return null;
    return new Date(timestamp).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  }, [match.game_start_timestamp]);

  const rowClass = isSelected
    ? styles.rowSelected
    : index % 2 === 0
      ? styles.rowEven
      : styles.rowOdd;

  return (
    <tr
      className={rowClass}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick();
      }}
    >
      <td className={styles.cell}>{queueModeLabel}</td>
      <td className={styles.cell}>
        <div className={styles.champion}>
          {imageUrl ? (
            <Image
              className={styles.championIcon}
              src={imageUrl}
              alt={championName}
              width={32}
              height={32}
              unoptimized
            />
          ) : (
            <div className={styles.championIconFallback}>?</div>
          )}
          <span className={styles.championName}>{championName}</span>
        </div>
      </td>
      <td className={styles.cell}>
        <span
          className={
            isWin === null
              ? styles.unknown
              : isWin
                ? styles.win
                : styles.loss
          }
        >
          {isWin === null ? "—" : isWin ? "Win" : "Loss"}
        </span>
      </td>
      <td className={styles.cell}>{kdaRatio.toFixed(2)}</td>
      <td className={styles.cell}>{csPerMinute.toFixed(1)}</td>
      <td className={styles.cell}>{participant?.lane ?? "—"}</td>
      <td className={styles.cell}>{participant?.role ?? "—"}</td>
      <td className={styles.cell}>{formattedDate ?? "—"}</td>
    </tr>
  );
});

export default MatchRow;
