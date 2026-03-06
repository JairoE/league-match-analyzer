import type {MatchDetail, MatchSummary, Participant} from "./types/match";
import type {UserSession} from "./types/user";

// ── Outcome ───────────────────────────────────────────────────────────

export type MatchOutcome = "victory" | "defeat" | "remake";

/**
 * Determines match outcome for a participant.
 * Remake = early surrender flag OR duration ≤ 210 seconds (League remake window).
 *
 * The duration fallback handles cases where gameEndedInEarlySurrender is absent
 * from the stored payload (e.g. older cached game_info entries).
 *
 * Used by: MatchCard outcome styling, MatchRow result column, LLM normalize step.
 */
export function getMatchOutcome(
  participant: Participant | null,
  gameDuration: number | undefined
): MatchOutcome {
  if (!participant) return "defeat";
  const duration = gameDuration ?? 0;
  const isRemake =
    participant.gameEndedInEarlySurrender === true ||
    (duration > 0 && duration <= 210);
  if (isRemake) return "remake";
  return participant.win ? "victory" : "defeat";
}

// ── Formatting ────────────────────────────────────────────────────────

/**
 * Formats raw seconds into "Xm Ys" display string.
 * e.g. 1847 → "30m 47s"
 */
export function formatGameDuration(seconds: number | undefined): string {
  if (!seconds || seconds <= 0) return "0m 0s";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

/**
 * Converts an epoch-millisecond timestamp to a relative human string.
 * e.g. "Today", "Yesterday", "5 days ago".
 */
export function formatRelativeTime(timestamp: number | undefined): string {
  if (!timestamp) return "";
  const now = Date.now();
  const diff = now - timestamp;
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return `${days} days ago`;
}

// ── Aggregates ────────────────────────────────────────────────────────

/**
 * Kill participation as an integer percentage (0-100).
 * (kills + assists) / teamKills * 100.
 * Returns 0 when team has no kills.
 *
 * Used by: MatchCard summary row, LLM context builder.
 */
export function calculateKillParticipation(
  participant: Participant | null,
  allParticipants: Participant[]
): number {
  if (!participant) return 0;
  const teamId = participant.teamId;
  const teamKills = allParticipants
    .filter((p) => p.teamId === teamId)
    .reduce((sum, p) => sum + (p.kills ?? 0), 0);
  if (teamKills === 0) return 0;
  const contrib = (participant.kills ?? 0) + (participant.assists ?? 0);
  return Math.round((contrib / teamKills) * 100);
}

/**
 * 1-indexed damage rank among all 10 participants sorted by
 * totalDamageDealtToChampions descending.
 * Returns 0 if participant is not found.
 */
export function getDamageRankPosition(
  participant: Participant | null,
  allParticipants: Participant[]
): number {
  if (!participant || allParticipants.length === 0) return 0;
  const sorted = [...allParticipants].sort(
    (a, b) =>
      (b.totalDamageDealtToChampions ?? 0) -
      (a.totalDamageDealtToChampions ?? 0)
  );
  const idx = sorted.findIndex(
    (p) =>
      (participant.participantId != null &&
        p.participantId === participant.participantId) ||
      (participant.puuid != null && p.puuid === participant.puuid)
  );
  return idx === -1 ? 0 : idx + 1;
}

// ── Team helpers ──────────────────────────────────────────────────────

/** Returns participants on the same team as `current`. */
export function getAlliedTeam(
  participants: Participant[],
  current: Participant
): Participant[] {
  return participants.filter((p) => p.teamId === current.teamId);
}

/** Returns participants on the opposing team from `current`. */
export function getEnemyTeam(
  participants: Participant[],
  current: Participant
): Participant[] {
  return participants.filter((p) => p.teamId !== current.teamId);
}

// ── CS helpers ────────────────────────────────────────────────────────

/** Total CS = totalMinionsKilled + neutralMinionsKilled. */
export function getTotalCs(participant: Participant | null): number {
  if (!participant) return 0;
  return (
    (participant.totalMinionsKilled ?? 0) +
    (participant.neutralMinionsKilled ?? 0)
  );
}

// ── Display helpers ───────────────────────────────────────────────────

/** Converts 1 → "1st", 2 → "2nd", 3 → "3rd", N → "Nth". */
export function ordinalSuffix(n: number): string {
  if (n === 1) return "1st";
  if (n === 2) return "2nd";
  if (n === 3) return "3rd";
  return `${n}th`;
}

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

  return null;
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
