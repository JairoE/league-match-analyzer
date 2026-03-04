"use client";
/*
 * eslint-disable @next/next/no-img-element
 *
 * This file intentionally uses <img> (not <Image>) for external DDragon CDN
 * assets (spells, rune icons). These elements require onError handlers for
 * graceful hidden-fallback when an asset 404s, and the DDragon domain is not
 * listed in next.config.ts remotePatterns.
 */
/* eslint-disable @next/next/no-img-element */

import {memo, useMemo} from "react";
import Image from "next/image";
import styles from "./MatchCard.module.css";
import type {MatchCardProps} from "./types";
import {ItemSlot} from "./ItemSlot";
import Teams from "./Teams";
import {ChampionKdaChart} from "./ChampionKdaChart";
import {diffLabel, getMultikillBadges, getOutcomeDisplay} from "./match-card.utils";
import {
  calculateKillParticipation,
  formatGameDuration,
  formatRelativeTime,
  getDamageRankPosition,
  getCsPerMinute,
  getKdaRatio,
  getMatchId,
  getMatchOutcome,
  getParticipantByPuuid,
  getParticipantForUser,
  getTotalCs,
  ordinalSuffix,
} from "../../lib/match-utils";
import {getQueueMode, getQueueModeLabel} from "../../lib/types/queue";
import {
  FALLBACK_DDRAGON_VERSION,
  getKeystoneImageUrl,
  getRuneStyleIconUrl,
  getSpellImageUrl,
  getSpellLabel,
} from "../../lib/constants/ddragon";

export default memo(function MatchCard({
  match,
  detail,
  champion,
  user,
  isSearchView = false,
  targetPuuid = null,
  rankByPuuid,
  laneStats,
  championHistory = [],
}: MatchCardProps) {
  // ── Participant resolution ──────────────────────────────────────────
  const participant = useMemo(
    () =>
      isSearchView
        ? getParticipantByPuuid(detail, targetPuuid)
        : getParticipantForUser(detail, user),
    [detail, isSearchView, targetPuuid, user]
  );

  const participants = detail?.info?.participants ?? [];
  const gameDuration = detail?.info?.gameDuration;
  const currentMatchId = getMatchId(match) ?? null;

  // ── Derived stats ───────────────────────────────────────────────────
  const outcome = getMatchOutcome(participant, gameDuration);
  const kdaRatio = getKdaRatio(participant);
  const totalCs = getTotalCs(participant);
  const csPerMin = getCsPerMinute(participant);
  const killParticipation = calculateKillParticipation(participant, participants);
  const damageRank = getDamageRankPosition(participant, participants);
  const durationStr = formatGameDuration(gameDuration);
  const relativeTime = formatRelativeTime(match.game_start_timestamp ?? undefined);

  // ── Display values ──────────────────────────────────────────────────
  const championName = champion?.name ?? participant?.championName ?? "Unknown Champion";
  const champLevel = participant?.champLevel;
  const imageUrl = champion?.image_url ?? null;
  const queueId = detail?.info?.queueId ?? match.queueId ?? undefined;
  const queueModeLabel = getQueueModeLabel(getQueueMode(queueId));

  // ── Items (slots 0-5 = items, slot 6 = trinket) ─────────────────────
  const itemIds: number[] = [
    participant?.item0 ?? 0,
    participant?.item1 ?? 0,
    participant?.item2 ?? 0,
    participant?.item3 ?? 0,
    participant?.item4 ?? 0,
    participant?.item5 ?? 0,
    participant?.item6 ?? 0,
  ];

  // ── Spells & keystone ───────────────────────────────────────────────
  const spell1Id = participant?.summoner1Id ?? 0;
  const spell2Id = participant?.summoner2Id ?? 0;
  const primaryStyle = participant?.perks?.styles?.find(
    (s) => s.description === "primaryStyle"
  );
  const subStyle = participant?.perks?.styles?.find(
    (s) => s.description === "subStyle"
  );
  const keystonePerkId = primaryStyle?.selections?.[0]?.perk ?? 0;
  const keystoneStyleId = primaryStyle?.style ?? 0;
  const subStyleId = subStyle?.style ?? 0;
  const hasKeystone = keystonePerkId > 0 && keystoneStyleId > 0;
  const hasSubStyle = subStyleId > 0;

  // ── Badges ──────────────────────────────────────────────────────────
  const multikills = getMultikillBadges(participant);
  const showVictor =
    outcome === "victory" && ((damageRank > 0 && damageRank <= 3) || kdaRatio > 5);
  const showDownfall =
    outcome === "defeat" && ((participant?.deaths ?? 0) > 8 || kdaRatio < 1);

  // ── DDragon version ─────────────────────────────────────────────────
  const version = FALLBACK_DDRAGON_VERSION;

  // ── Outcome display ─────────────────────────────────────────────────
  const {outcomeClass, textQueueClass, outcomeLabel} = getOutcomeDisplay(outcome, styles);

  const currentPuuid = isSearchView
    ? (targetPuuid ?? undefined)
    : (user?.riot_account?.puuid ?? undefined);

  return (
    <article className={`${styles.card} ${outcomeClass}`}>
      {/* ── Column 1: Game Info ── */}
      <div className={styles.gameInfo}>
        <div className={`${styles.queueType} ${textQueueClass}`}>{queueModeLabel}</div>
        <div className={styles.textGray}>{relativeTime}</div>
        <div className={styles.outcomeLine}>{outcomeLabel}</div>
        <div className={styles.textGray}>{durationStr}</div>
      </div>

      {/* ── Column 2: Player Info (Champ, Spells, KDA, Items) ── */}
      <div className={styles.playerInfo}>
        <div className={styles.playerInfoTop}>
          <div className={styles.championPortrait}>
            {imageUrl ? (
              <Image
                className={styles.championImage}
                src={imageUrl}
                alt={`${championName} level ${champLevel ?? ""}`}
                width={48}
                height={48}
                unoptimized
              />
            ) : (
              <div className={styles.championFallback}>?</div>
            )}
            {champLevel != null && (
              <span className={styles.champLevel}>{champLevel}</span>
            )}
          </div>

          <div className={styles.spellCol}>
            <img
              src={getSpellImageUrl(spell1Id, version)}
              alt={getSpellLabel(spell1Id)}
              className={styles.spellSlot}
              width={20}
              height={20}
              loading="lazy"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
            {hasKeystone ? (
              <img
                src={getKeystoneImageUrl(keystonePerkId, keystoneStyleId)}
                alt="Keystone rune"
                className={styles.keystoneSlot}
                width={20}
                height={20}
                loading="lazy"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            ) : (
              <div className={styles.keystoneEmpty} aria-hidden="true" />
            )}
            <img
              src={getSpellImageUrl(spell2Id, version)}
              alt={getSpellLabel(spell2Id)}
              className={styles.spellSlot}
              width={20}
              height={20}
              loading="lazy"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
            {hasSubStyle ? (
              <img
                src={getRuneStyleIconUrl(subStyleId)}
                alt="Secondary rune style"
                className={styles.keystoneSlot}
                width={20}
                height={20}
                loading="lazy"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            ) : (
              <div className={styles.keystoneEmpty} aria-hidden="true" />
            )}
          </div>

          <div className={styles.kdaBox}>
            <div className={styles.kdaNumbers}>
              <span className={styles.kills}>{participant?.kills ?? "-"}</span>
              <span className={styles.slash}>/</span>
              <span className={styles.deaths}>{participant?.deaths ?? "-"}</span>
              <span className={styles.slash}>/</span>
              <span className={styles.assists}>{participant?.assists ?? "-"}</span>
            </div>
            <div className={styles.kdaRatioText}>{kdaRatio.toFixed(2)}:1 KDA</div>
          </div>
        </div>

        <div className={styles.buildRow}>
          {itemIds.slice(0, 6).map((id, i) => (
            <ItemSlot key={i} itemId={id} version={version} />
          ))}
          <div className={styles.itemSpacer} />
          <ItemSlot itemId={itemIds[6]} version={version} />
        </div>
      </div>

      {/* ── Column 3: Stats & Badges ── */}
      <div className={styles.statsColumn}>
        {killParticipation > 0 && (
          <div className={styles.textGray}>P/Kill {killParticipation}%</div>
        )}
        <div className={styles.textGray}>CS {totalCs} ({csPerMin.toFixed(1)})</div>

        {laneStats && (
          <div className={styles.laningRow}>
            {diffLabel(laneStats.cs_diff_at_10) != null && (
              <span
                className={`${styles.laningStat} ${
                  (laneStats.cs_diff_at_10 ?? 0) >= 0 ? styles.laningPos : styles.laningNeg
                }`}
              >
                CS@10 {diffLabel(laneStats.cs_diff_at_10)}
              </span>
            )}
            {diffLabel(laneStats.cs_diff_at_15) != null && (
              <span
                className={`${styles.laningStat} ${
                  (laneStats.cs_diff_at_15 ?? 0) >= 0 ? styles.laningPos : styles.laningNeg
                }`}
              >
                CS@15 {diffLabel(laneStats.cs_diff_at_15)}
              </span>
            )}
            {diffLabel(laneStats.gold_diff_at_10) != null && (
              <span
                className={`${styles.laningStat} ${
                  (laneStats.gold_diff_at_10 ?? 0) >= 0 ? styles.laningPos : styles.laningNeg
                }`}
              >
                G@10 {diffLabel(laneStats.gold_diff_at_10)}
              </span>
            )}
          </div>
        )}

        <div className={styles.badgesRow}>
          {multikills.map((mk) =>
            Array.from({length: mk.count}).map((_, i) => (
              <span
                key={`${mk.label}-${i}`}
                className={`${styles.badge} ${mk.penta ? styles.badgeGold : styles.badgeRed}`}
                aria-label={`Achieved ${mk.label}`}
              >
                {mk.label}
              </span>
            ))
          )}
          {damageRank > 0 && participants.length > 0 && (
            <span
              className={`${styles.badge} ${styles.badgeGray}`}
              aria-label={`Damage rank ${ordinalSuffix(damageRank)} of all players`}
            >
              {ordinalSuffix(damageRank)}
            </span>
          )}
          {showVictor && (
            <span className={`${styles.badge} ${styles.badgeGray}`}>Victor</span>
          )}
          {showDownfall && (
            <span className={`${styles.badge} ${styles.badgeGray}`}>Downfall</span>
          )}
        </div>
      </div>

      {/* ── Column 4: Teams ── */}
      {participants.length > 0 && participant && (
        <Teams
          participants={participants}
          current={participant}
          currentPuuid={currentPuuid}
          version={version}
          rankByPuuid={rankByPuuid}
        />
      )}

      {/* ── KDA History Chart (full-width row) ── */}
      {championHistory.length >= 2 && (
        <ChampionKdaChart history={championHistory} currentMatchId={currentMatchId} />
      )}
    </article>
  );
});
