import type {MatchDetail, MatchSummary, Participant} from "./types/match";
import type {UserSession} from "./types/user";

export function getMatchId(match: MatchSummary): string | null {
  const candidate =
    match.matchId ??
    match.match_id ??
    match.id ??
    (match as {matchID?: string}).matchID;
  if (!candidate) return null;
  return String(candidate);
}

export function getParticipantForUser(
  detail: MatchDetail | null,
  user: UserSession | null
): Participant | null {
  if (!detail?.info?.participants?.length) return null;
  const participants = detail.info.participants;

  // Match by riot account puuid
  const targetPuuid = user?.riot_account?.puuid;
  if (targetPuuid) {
    const match = participants.find(
      (participant) => participant.puuid === targetPuuid
    );
    if (match) return match;
  }

  // Fallback: match by summoner name
  const targetName = user?.riot_account?.summonerName;
  if (targetName) {
    const normalized = targetName.toLowerCase();
    const match = participants.find((participant) => {
      const candidate =
        participant.summonerName ??
        participant.gameName ??
        participant.name ??
        "";
      return candidate.toLowerCase() === normalized;
    });
    if (match) return match;
  }

  return participants[0] ?? null;
}

/**
 * Find a participant by puuid directly (for search results where
 * the viewed account may differ from the signed-in user).
 */
export function getParticipantByPuuid(
  detail: MatchDetail | null,
  puuid: string | null
): Participant | null {
  if (!detail?.info?.participants?.length || !puuid) return null;
  return (
    detail.info.participants.find(
      (participant) => participant.puuid === puuid
    ) ?? null
  );
}

export function getKdaRatio(participant: Participant | null): number {
  if (!participant) return 0;
  const kills = participant.kills ?? 0;
  const deaths = participant.deaths ?? 0;
  const assists = participant.assists ?? 0;
  return (kills + assists) / Math.max(1, deaths);
}

export function getCsPerMinute(participant: Participant | null): number {
  if (!participant) return 0;
  const total =
    (participant.totalMinionsKilled ?? 0) +
    (participant.neutralMinionsKilled ?? 0);
  const minutes = (participant.timePlayed ?? 0) / 60;
  if (minutes <= 0) return 0;
  return total / minutes;
}
