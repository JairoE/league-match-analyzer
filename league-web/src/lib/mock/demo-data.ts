// Bundled demo dataset for the backend-free "demo mode" deploy.
//
// When NEXT_PUBLIC_DEMO_MODE is enabled (see ./resolve-mock), every API call
// is served from the canned data below instead of hitting the FastAPI backend.
// This lets the frontend be deployed as a fully static site with no server,
// database, or Riot API key.

import type {Champion} from "../types/champion";
import type {LaneStats, MatchSummary, PaginatedMatchList} from "../types/match";
import type {RankInfo} from "../types/rank";
import type {RiotAccountData, UserSession} from "../types/user";
import {getChampionImageUrl} from "../constants/ddragon";

export const DEMO_PUUID = "demo-puuid-0001";
const DEMO_ACCOUNT_ID = "demo-riot-account-0001";

export const DEMO_ACCOUNT: RiotAccountData = {
  id: DEMO_ACCOUNT_ID,
  summonerName: "DemoSummoner",
  riot_id: "DemoSummoner#NA1",
  puuid: DEMO_PUUID,
  profileIconId: 29,
  summonerLevel: 312,
};

export const DEMO_USER: UserSession = {
  id: "demo-user-0001",
  email: "demo@league-analyzer.gg",
  riot_account: DEMO_ACCOUNT,
};

// The single summoner + email the demo dataset recognizes. Every other search
// or sign-in is rejected just like a real "not found", so the demo behaves like
// production for any other input.
export const DEMO_RIOT_ID = DEMO_ACCOUNT.riot_id;
export const DEMO_EMAIL = DEMO_USER.email;

/**
 * Normalize a Riot ID or email for comparison: percent-decode when needed,
 * trim, and lowercase. Handles "DemoSummoner%23NA1" and "DemoSummoner#NA1".
 */
export function canonical(value: string): string {
  let decoded = value;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    // Not percent-encoded — use the raw value.
  }
  return decoded.trim().toLowerCase();
}

export const DEMO_RANK: RankInfo = {
  queueType: "RANKED_SOLO_5x5",
  tier: "PLATINUM",
  rank: "IV",
  leaguePoints: 62,
  wins: 128,
  losses: 117,
};

export const DEMO_LANE_STATS: LaneStats = {
  cs_diff_at_10: 8,
  cs_diff_at_15: 14,
  gold_diff_at_10: 320,
  gold_diff_at_15: 540,
  lane_opponent_name: "EnemyZed",
  lane_opponent_champion: "Zed",
};

const CHAMPION_NAMES: Record<number, string> = {
  11: "MasterYi",
  22: "Ashe",
  64: "LeeSin",
  89: "Leona",
  91: "Talon",
  99: "Lux",
  157: "Yasuo",
  235: "Senna",
  238: "Zed",
  254: "Vi",
};

export function demoChampion(id: number): Champion {
  const name = CHAMPION_NAMES[id] ?? `Champion ${id}`;
  return {
    id,
    champ_id: id,
    name,
    title: "the Demo Champion",
    // Point at the public DDragon CDN so the portrait loads with no backend.
    image_url: CHAMPION_NAMES[id] ? getChampionImageUrl(name) : "",
  };
}

export const DEMO_CHAMPIONS: Champion[] = Object.keys(CHAMPION_NAMES).map((id) =>
  demoChampion(Number(id))
);

// ── Match builders ───────────────────────────────────────────────────

type ParticipantOverrides = Record<string, unknown>;

function makeMainParticipant(overrides: ParticipantOverrides = {}) {
  return {
    puuid: DEMO_PUUID,
    summonerName: "DemoSummoner",
    gameName: "DemoSummoner",
    tagLine: "NA1",
    participantId: 1,
    championId: 157,
    championName: "Yasuo",
    champLevel: 14,
    kills: 8,
    deaths: 3,
    assists: 6,
    win: true,
    teamId: 100,
    individualPosition: "MIDDLE",
    totalDamageDealtToChampions: 25400,
    totalMinionsKilled: 198,
    neutralMinionsKilled: 12,
    timePlayed: 1800,
    summoner1Id: 4,
    summoner2Id: 14,
    // Real DDragon item IDs so the build row renders actual icons (AD build).
    item0: 6673,
    item1: 3006,
    item2: 3031,
    item3: 3072,
    item4: 3036,
    item5: 6676,
    item6: 3340,
    perks: {
      styles: [
        {
          description: "primaryStyle",
          style: 8000,
          selections: [{perk: 8008}, {perk: 9111}, {perk: 9104}, {perk: 8014}],
        },
        {
          description: "subStyle",
          style: 8200,
          selections: [{perk: 8234}, {perk: 8236}],
        },
      ],
    },
    ...overrides,
  };
}

function makeEnemy(
  participantId: number,
  championId: number,
  championName: string,
  teamId: number
) {
  return {
    puuid: `demo-enemy-${championId}`,
    summonerName: `Enemy${championName}`,
    participantId,
    championId,
    championName,
    champLevel: 13,
    kills: 4,
    deaths: 5,
    assists: 3,
    win: teamId === 100,
    teamId,
    totalDamageDealtToChampions: 17600,
    totalMinionsKilled: 160,
    neutralMinionsKilled: 8,
    timePlayed: 1800,
  };
}

function makeAlly(
  participantId: number,
  championId: number,
  championName: string,
  win: boolean,
  kda: [number, number, number]
) {
  return {
    puuid: `demo-ally-${championId}`,
    summonerName: `Ally${championName}`,
    participantId,
    championId,
    championName,
    champLevel: 13,
    kills: kda[0],
    deaths: kda[1],
    assists: kda[2],
    win,
    teamId: 100,
    totalDamageDealtToChampions: 15000,
    totalMinionsKilled: 140,
    neutralMinionsKilled: 6,
    timePlayed: 1800,
  };
}

function makeTeam(teamId: number, win: boolean) {
  return {teamId, win: win ? "Win" : "Fail", objectives: {}, bans: []};
}

function buildMatch(
  matchId: string,
  queueId: number,
  ageMs: number,
  main: ParticipantOverrides,
  win: boolean
): MatchSummary {
  const timestamp = Date.now() - ageMs;
  return {
    id: matchId,
    match_id: matchId,
    game_start_timestamp: timestamp,
    queueId,
    game_info: {
      metadata: {matchId},
      info: {
        queueId,
        gameDuration: 1800,
        gameCreation: timestamp,
        gameStartTimestamp: timestamp,
        participants: [
          makeMainParticipant(main),
          makeEnemy(2, 238, "Zed", 200),
          makeEnemy(3, 91, "Talon", 200),
          makeEnemy(4, 64, "LeeSin", 200),
          makeEnemy(5, 11, "MasterYi", 200),
          makeAlly(6, 235, "Senna", win, [2, 1, 14]),
          makeAlly(7, 254, "Vi", win, [5, 4, 7]),
          makeAlly(8, 89, "Leona", win, [1, 2, 16]),
          makeAlly(9, 99, "Lux", win, [6, 3, 9]),
          makeAlly(10, 22, "Ashe", win, [7, 2, 8]),
        ],
        teams: [makeTeam(100, win), makeTeam(200, !win)],
      },
    },
  };
}

// 2 ranked solo (queue 420), 1 normal draft (400), 1 ARAM (450).
const DEMO_MATCHES: MatchSummary[] = [
  buildMatch(
    "DEMO_NA1_001",
    420,
    1_800_000,
    {kills: 8, deaths: 3, assists: 6, win: true},
    true
  ),
  buildMatch(
    "DEMO_NA1_002",
    420,
    5_400_000,
    {kills: 2, deaths: 7, assists: 4, win: false},
    false
  ),
  buildMatch(
    "DEMO_NA1_003",
    400,
    9_000_000,
    {
      championId: 238,
      championName: "Zed",
      kills: 11,
      deaths: 4,
      assists: 5,
      win: true,
      // Zed assassin build.
      item0: 6692,
      item1: 3006,
      item2: 6694,
      item3: 6676,
      item4: 3814,
      item5: 3071,
      item6: 3340,
    },
    true
  ),
  buildMatch(
    "DEMO_NA1_004",
    450,
    12_600_000,
    {
      championId: 99,
      championName: "Lux",
      kills: 14,
      deaths: 6,
      assists: 21,
      win: true,
      // Lux AP build.
      item0: 6655,
      item1: 3020,
      item2: 4645,
      item3: 3089,
      item4: 3157,
      item5: 3135,
      item6: 3340,
    },
    true
  ),
];

export const DEMO_MATCH_PAGE: PaginatedMatchList = {
  data: DEMO_MATCHES,
  meta: {
    page: 1,
    limit: 20,
    total: DEMO_MATCHES.length,
    last_page: 1,
    stale: false,
    stale_reason: null,
  },
};

export const DEMO_EMPTY_PAGE: PaginatedMatchList = {
  data: [],
  meta: {
    page: 2,
    limit: 20,
    total: DEMO_MATCHES.length,
    last_page: 1,
    stale: false,
    stale_reason: null,
  },
};

export function demoMatchDetailById(matchId: string): MatchSummary["game_info"] {
  const found = DEMO_MATCHES.find(
    (m) => m.match_id === matchId || m.id === matchId
  );
  return found?.game_info ?? DEMO_MATCHES[0].game_info;
}
