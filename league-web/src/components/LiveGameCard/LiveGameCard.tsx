/* eslint-disable @next/next/no-img-element */
"use client";

import {useEffect, useState} from "react";
import styles from "./LiveGameCard.module.css";
import type {LiveGameData, LiveGameParticipant} from "../../lib/types/live-game";
import type {Champion} from "../../lib/types/champion";
import {apiGet} from "../../lib/api";
import {getSpellImageUrl} from "../../lib/constants/ddragon";
import {
  getQueueMode,
  getQueueModeLabel,
} from "../../lib/types/queue";

type LiveGameCardProps = {
  game: LiveGameData;
  targetPuuid: string;
};

function hideOnError(e: React.SyntheticEvent<HTMLImageElement>) {
  (e.target as HTMLImageElement).style.display = "none";
}

type ParticipantRowProps = {
  p: LiveGameParticipant;
  targetPuuid: string;
  championById: Record<number, Champion>;
};

function ParticipantRow({p, targetPuuid, championById}: ParticipantRowProps) {
  const isSelf = p.puuid === targetPuuid;
  const champ = championById[p.championId];
  const champName = champ?.name ?? `Champion ${p.championId}`;
  // Spectator v5 returns riotId ("Name#Tag") and summonerName
  const summonerDisplay = p.riotId
    ? p.riotId.split("#")[0]
    : (p.summonerName ?? "Summoner");

  return (
    <div
      className={`${styles.participant} ${isSelf ? styles.self : ""}`}
    >
      {champ?.image_url ? (
        <img
          src={champ.image_url}
          alt={champName}
          className={styles.champIcon}
          width={24}
          height={24}
          loading="lazy"
          onError={hideOnError}
        />
      ) : (
        <span className={styles.champIconPlaceholder} />
      )}
      <img
        src={getSpellImageUrl(p.spell1Id)}
        alt="Spell 1"
        className={styles.spellIcon}
        width={14}
        height={14}
        loading="lazy"
        onError={hideOnError}
      />
      <img
        src={getSpellImageUrl(p.spell2Id)}
        alt="Spell 2"
        className={styles.spellIcon}
        width={14}
        height={14}
        loading="lazy"
        onError={hideOnError}
      />
      <span className={styles.summonerName}>{summonerDisplay}</span>
    </div>
  );
}

export default function LiveGameCard({
  game,
  targetPuuid,
}: LiveGameCardProps) {
  const [championById, setChampionById] = useState<Record<number, Champion>>({});
  const [elapsed, setElapsed] = useState(game.gameLength);

  // Fetch champion list once for ID → name mapping
  useEffect(() => {
    let active = true;
    apiGet<Champion[]>("/champions")
      .then((list) => {
        if (!active) return;
        const map: Record<number, Champion> = {};
        for (const c of list) {
          if (c.champ_id != null) map[c.champ_id] = c;
        }
        setChampionById(map);
      })
      .catch((err) => {
        console.debug("[LiveGameCard] champion fetch failed", err);
      });
    return () => {
      active = false;
    };
  }, []);

  // Tick elapsed time every second
  useEffect(() => {
    const gameStartMs = game.gameStartTime;
    if (!gameStartMs || gameStartMs <= 0) return;

    const id = setInterval(() => {
      const secs = Math.max(0, Math.floor((Date.now() - gameStartMs) / 1000));
      setElapsed(secs);
    }, 1000);
    return () => clearInterval(id);
  }, [game.gameStartTime]);

  const queueLabel = getQueueModeLabel(getQueueMode(game.gameQueueConfigId));
  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const timeStr = `${minutes}:${seconds.toString().padStart(2, "0")}`;

  const blueTeam = game.participants.filter((p) => p.teamId === 100);
  const redTeam = game.participants.filter((p) => p.teamId === 200);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.liveBadge}>
          <span className={styles.liveDot} />
          LIVE
        </span>
        <span className={styles.queueLabel}>{queueLabel}</span>
        <span className={styles.timer}>{timeStr}</span>
      </div>

      <div className={styles.teams}>
        <div className={styles.team}>
          <div className={styles.teamLabel}>Blue Team</div>
          {blueTeam.map((p) => (
            <ParticipantRow
              key={p.puuid}
              p={p}
              targetPuuid={targetPuuid}
              championById={championById}
            />
          ))}
        </div>
        <div className={styles.team}>
          <div className={styles.teamLabel}>Red Team</div>
          {redTeam.map((p) => (
            <ParticipantRow
              key={p.puuid}
              p={p}
              targetPuuid={targetPuuid}
              championById={championById}
            />
          ))}
        </div>
      </div>

      {game.bannedChampions.length > 0 && (
        <div className={styles.bans}>
          <span className={styles.bansLabel}>Bans:</span>
          {game.bannedChampions.map((ban, i) => {
            const champ = championById[ban.championId];
            return champ?.image_url ? (
              <img
                key={i}
                src={champ.image_url}
                alt={champ.name ?? "Banned"}
                className={styles.banIcon}
                width={20}
                height={20}
                loading="lazy"
                onError={hideOnError}
              />
            ) : null;
          })}
        </div>
      )}
    </div>
  );
}
