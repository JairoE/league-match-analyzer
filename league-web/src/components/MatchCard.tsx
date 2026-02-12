"use client";

import {useEffect, useMemo, useState} from "react";
import styles from "./MatchCard.module.css";
import {apiGet} from "../lib/api";
import type {Champion} from "../lib/types/champion";
import type {MatchDetail, MatchSummary, Participant} from "../lib/types/match";
import type {UserSession} from "../lib/types/user";
import {
  getCsPerMinute,
  getKdaRatio,
  getMatchId,
  getParticipantByPuuid,
  getParticipantForUser,
} from "../lib/match-utils";

type MatchCardProps = {
  match: MatchSummary;
  detail: MatchDetail | null;
  user: UserSession | null;
  targetPuuid?: string | null;
};

export default function MatchCard({
  match,
  detail,
  user,
  targetPuuid = null,
}: MatchCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [champion, setChampion] = useState<Champion | null>(null);

  const matchId = useMemo(() => getMatchId(match), [match]);
  const participant = useMemo<Participant | null>(
    () =>
      targetPuuid
        ? getParticipantByPuuid(detail, targetPuuid)
        : getParticipantForUser(detail, user),
    [detail, targetPuuid, user]
  );
  const championId = participant?.championId ?? null;

  const gameStartDate = useMemo(() => {
    const timestamp = match.game_start_timestamp;
    if (!timestamp) return null;
    return new Date(timestamp);
  }, [match.game_start_timestamp]);

  const formattedDate = useMemo<string | null>(() => {
    if (!gameStartDate) return null;
    return gameStartDate.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }, [gameStartDate]);

  const formattedTime = useMemo<string | null>(() => {
    if (!gameStartDate) return null;
    return gameStartDate.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }, [gameStartDate]);

  useEffect(() => {
    if (!championId) return;
    let isActive = true;

    const loadChampion = async () => {
      try {
        console.debug("[match-card] fetch champion", {championId, matchId});
        const response = await apiGet<Champion>(`/champions/${championId}`, {
          cacheTtlMs: 60_000,
        });
        if (isActive) {
          setChampion(response);
          console.debug("[match-card] champion loaded", {championId, matchId});
        }
      } catch (error) {
        console.debug("[match-card] champion load failed", {
          championId,
          matchId,
          error,
        });
      }
    };

    void loadChampion();

    return () => {
      isActive = false;
    };
  }, [championId, matchId]);

  const kdaRatio = getKdaRatio(participant);
  const csPerMinute = getCsPerMinute(participant);
  const isWin = participant?.win ?? null;
  const championName =
    champion?.name ?? participant?.championName ?? "Unknown Champion";
  const imageUrl =
    champion?.imageUrl ??
    champion?.image_url ??
    champion?.iconUrl ??
    champion?.icon_url ??
    null;
  const gameMode = (detail?.info as any)?.gameMode as string | undefined;

  return (
    <article className={styles.card}>
      <header className={styles.header}>
        <div>
          <p className={styles.matchId}>
            {gameMode ? `${gameMode} Match` : `Match ${matchId ?? "Unknown"}`}
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
          <img
            className={styles.championImage}
            src={imageUrl}
            alt={championName}
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
      <button
        className={styles.toggle}
        onClick={() => setIsOpen((prev) => !prev)}
      >
        {isOpen ? "Hide details" : "Show details"}
      </button>
      {isOpen ? (
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
