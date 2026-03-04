/*
 * eslint-disable @next/next/no-img-element
 *
 * Uses <img> (not <Image>) for external DDragon CDN assets with onError fallback.
 */
/* eslint-disable @next/next/no-img-element */

import {memo} from "react";
import styles from "./MatchCard.module.css";
import type {Participant} from "../../lib/types/match";
import {getAlliedTeam, getEnemyTeam} from "../../lib/match-utils";
import {getChampionImageUrl} from "../../lib/constants/ddragon";
import type {TeamsProps} from "./types";

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

export default Teams;
