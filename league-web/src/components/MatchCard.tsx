"use client";

import {useMemo, useState} from "react";
import Image from "next/image";
import styles from "./MatchCard.module.css";
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

type MatchCardProps = {
  match: MatchSummary;
  detail: MatchDetail | null;
  champion: Champion | null;
  user: UserSession | null;
  isSearchView?: boolean;
  targetPuuid?: string | null;
  expanded?: boolean;
};

export default function MatchCard({
  match,
  detail,
  champion,
  user,
  isSearchView = false,
  targetPuuid = null,
  expanded = false,
}: MatchCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const showDetails = expanded || isOpen;

  const participant = useMemo<Participant | null>(
    () => {
      if (isSearchView) {
        return getParticipantByPuuid(detail, targetPuuid);
      }
      return getParticipantForUser(detail, user);
    },
    [detail, isSearchView, targetPuuid, user]
  );

  const {formattedDate, formattedTime} = useMemo(() => {
    const d = match.game_start_timestamp
      ? new Date(match.game_start_timestamp)
      : null;
    if (!d) return {formattedDate: null, formattedTime: null};
    return {
      formattedDate: d.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      }),
      formattedTime: d.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };
  }, [match.game_start_timestamp]);

  const kdaRatio = getKdaRatio(participant);
  const csPerMinute = getCsPerMinute(participant);
  const isWin = participant?.win ?? null;
  const championName =
    champion?.name ?? participant?.championName ?? "Unknown Champion";
  const imageUrl = champion?.image_url ?? null;
  const queueId = detail?.info?.queueId ?? match.queueId ?? undefined;
  const queueModeLabel = getQueueModeLabel(getQueueMode(queueId));

  return (
    <article className={styles.card}>
      <header className={styles.header}>
        <div>
          <p className={styles.matchId}>
            {queueModeLabel} Match
          </p>
          {formattedDate && formattedTime && (
            <p className={styles.matchId}>
              {formattedDate} at {formattedTime}
            </p>
          )}
          <h3 className={styles.title}>
            {championName} {isWin === null ? "" : isWin ? "Win" : "Loss"}
          </h3>
        </div>
        {imageUrl ? (
          <Image
            className={styles.championImage}
            src={imageUrl}
            alt={championName}
            width={48}
            height={48}
            unoptimized
          />
        ) : (
          <div className={styles.championFallback}>?</div>
        )}
      </header>
      <div className={styles.summary}>
        <span>KDA {kdaRatio.toFixed(2)}</span>
        <span>CS/min {csPerMinute.toFixed(1)}</span>
        <span>{participant?.lane ?? "Unknown Lane"}</span>
        <span>{participant?.role ?? "Unknown Role"}</span>
      </div>
      {!expanded ? (
        <button
          className={styles.toggle}
          onClick={() => setIsOpen((prev) => !prev)}
        >
          {isOpen ? "Hide details" : "Show details"}
        </button>
      ) : null}
      {showDetails ? (
        <div className={styles.details}>
          <div>
            <p>Kills: {participant?.kills ?? "-"}</p>
            <p>Deaths: {participant?.deaths ?? "-"}</p>
            <p>Assists: {participant?.assists ?? "-"}</p>
          </div>
          <div>
            <p>Gold: {participant?.goldEarned ?? "-"}</p>
            <p>Game duration: {detail?.info?.gameDuration ?? "-"} sec</p>
            <p>Queue: {detail?.info?.queueId ?? match.queueId ?? "-"}</p>
          </div>
        </div>
      ) : null}
    </article>
  );
}
