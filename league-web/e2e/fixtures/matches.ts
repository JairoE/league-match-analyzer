import type {PaginatedMatchList, MatchSummary} from "../../src/lib/types/match";

const TEST_PUUID = "test-puuid-abc123";
const TEST_RIOT_ID = "TestUser%23NA1";

// Build a minimal participant for the test user
function makeParticipant(overrides: Record<string, unknown> = {}) {
  return {
    puuid: TEST_PUUID,
    summonerName: "TestUser",
    gameName: "TestUser",
    tagLine: "NA1",
    championId: 157, // Yasuo
    championName: "Yasuo",
    champLevel: 12,
    kills: 8,
    deaths: 3,
    assists: 5,
    win: true,
    teamId: 100,
    totalDamageDealtToChampions: 25000,
    totalMinionsKilled: 180,
    neutralMinionsKilled: 20,
    summoner1Id: 4,
    summoner2Id: 14,
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

function makeEnemy(championId: number, championName: string, teamId: number) {
  return {
    puuid: `enemy-${championId}`,
    summonerName: `Enemy${championName}`,
    championId,
    championName,
    champLevel: 11,
    kills: 3,
    deaths: 5,
    assists: 2,
    win: teamId === 200,
    teamId,
    totalDamageDealtToChampions: 18000,
    totalMinionsKilled: 150,
    neutralMinionsKilled: 10,
  };
}

function makeTeam(teamId: number, win: boolean) {
  return {teamId, win: win ? "Win" : "Fail", objectives: {}, bans: []};
}

// Ranked match (queueId=420) — Yasuo, WIN
export const RANKED_MATCH_1: MatchSummary = {
  match_id: "NA1_001",
  game_start_timestamp: Date.now() - 3_600_000,
  queueId: 420,
  game_info: {
    metadata: {matchId: "NA1_001"},
    info: {
      queueId: 420,
      gameDuration: 1800,
      gameCreation: Date.now() - 3_600_000,
      participants: [
        makeParticipant({kills: 8, deaths: 3, assists: 5, win: true}),
        makeEnemy(238, "Zed", 200),
        makeEnemy(91, "Talon", 200),
        makeEnemy(157, "Yasuo", 200),
        makeEnemy(64, "LeeSin", 200),
        makeEnemy(11, "MasterYi", 200),
        {
          ...makeParticipant({puuid: "ally2", win: true, teamId: 100, championId: 235, championName: "Senna", kills: 2, deaths: 1, assists: 10}),
        },
        {
          ...makeParticipant({puuid: "ally3", win: true, teamId: 100, championId: 254, championName: "Vi", kills: 5, deaths: 4, assists: 6}),
        },
        {
          ...makeParticipant({puuid: "ally4", win: true, teamId: 100, championId: 89, championName: "Leona", kills: 1, deaths: 2, assists: 12}),
        },
        {
          ...makeParticipant({puuid: "ally5", win: true, teamId: 100, championId: 99, championName: "Lux", kills: 4, deaths: 3, assists: 8}),
        },
      ],
      teams: [makeTeam(100, true), makeTeam(200, false)],
    },
  },
};

// Ranked match (queueId=420) — Yasuo, LOSS
export const RANKED_MATCH_2: MatchSummary = {
  match_id: "NA1_002",
  game_start_timestamp: Date.now() - 7_200_000,
  queueId: 420,
  game_info: {
    metadata: {matchId: "NA1_002"},
    info: {
      queueId: 420,
      gameDuration: 2100,
      gameCreation: Date.now() - 7_200_000,
      participants: [
        makeParticipant({kills: 2, deaths: 7, assists: 1, win: false}),
        makeEnemy(238, "Zed", 100),
        makeEnemy(91, "Talon", 100),
        makeEnemy(157, "Yasuo", 100),
        makeEnemy(64, "LeeSin", 100),
        makeEnemy(11, "MasterYi", 100),
        {
          ...makeParticipant({puuid: "ally2", win: false, teamId: 200, championId: 235, championName: "Senna", kills: 3, deaths: 4, assists: 7}),
        },
        {
          ...makeParticipant({puuid: "ally3", win: false, teamId: 200, championId: 254, championName: "Vi", kills: 1, deaths: 6, assists: 3}),
        },
        {
          ...makeParticipant({puuid: "ally4", win: false, teamId: 200, championId: 89, championName: "Leona", kills: 0, deaths: 5, assists: 8}),
        },
        {
          ...makeParticipant({puuid: "ally5", win: false, teamId: 200, championId: 99, championName: "Lux", kills: 2, deaths: 4, assists: 5}),
        },
      ],
      teams: [makeTeam(100, true), makeTeam(200, false)],
    },
  },
};

// Normal match (queueId=400)
export const NORMAL_MATCH: MatchSummary = {
  match_id: "NA1_003",
  game_start_timestamp: Date.now() - 10_800_000,
  queueId: 400,
  game_info: {
    metadata: {matchId: "NA1_003"},
    info: {
      queueId: 400,
      gameDuration: 1500,
      gameCreation: Date.now() - 10_800_000,
      participants: [
        makeParticipant({championId: 238, championName: "Zed", kills: 5, deaths: 2, assists: 3, win: true}),
        makeEnemy(157, "Yasuo", 200),
        makeEnemy(91, "Talon", 200),
        makeEnemy(64, "LeeSin", 200),
        makeEnemy(11, "MasterYi", 200),
        makeEnemy(235, "Senna", 200),
        {
          ...makeParticipant({puuid: "ally2", win: true, teamId: 100, championId: 254, championName: "Vi", kills: 4, deaths: 3, assists: 5}),
        },
        {
          ...makeParticipant({puuid: "ally3", win: true, teamId: 100, championId: 89, championName: "Leona", kills: 1, deaths: 1, assists: 9}),
        },
        {
          ...makeParticipant({puuid: "ally4", win: true, teamId: 100, championId: 99, championName: "Lux", kills: 3, deaths: 2, assists: 7}),
        },
        {
          ...makeParticipant({puuid: "ally5", win: true, teamId: 100, championId: 22, championName: "Ashe", kills: 6, deaths: 4, assists: 4}),
        },
      ],
      teams: [makeTeam(100, true), makeTeam(200, false)],
    },
  },
};

// ARAM match (queueId=450)
export const ARAM_MATCH: MatchSummary = {
  match_id: "NA1_004",
  game_start_timestamp: Date.now() - 14_400_000,
  queueId: 450,
  game_info: {
    metadata: {matchId: "NA1_004"},
    info: {
      queueId: 450,
      gameDuration: 1200,
      gameCreation: Date.now() - 14_400_000,
      participants: [
        makeParticipant({championId: 99, championName: "Lux", kills: 10, deaths: 5, assists: 15, win: true}),
        makeEnemy(238, "Zed", 200),
        makeEnemy(157, "Yasuo", 200),
        makeEnemy(91, "Talon", 200),
        makeEnemy(64, "LeeSin", 200),
        makeEnemy(11, "MasterYi", 200),
        {
          ...makeParticipant({puuid: "ally2", win: true, teamId: 100, championId: 254, championName: "Vi", kills: 3, deaths: 6, assists: 8}),
        },
        {
          ...makeParticipant({puuid: "ally3", win: true, teamId: 100, championId: 89, championName: "Leona", kills: 0, deaths: 4, assists: 14}),
        },
        {
          ...makeParticipant({puuid: "ally4", win: true, teamId: 100, championId: 235, championName: "Senna", kills: 5, deaths: 3, assists: 12}),
        },
        {
          ...makeParticipant({puuid: "ally5", win: true, teamId: 100, championId: 22, championName: "Ashe", kills: 7, deaths: 2, assists: 11}),
        },
      ],
      teams: [makeTeam(100, true), makeTeam(200, false)],
    },
  },
};

// Page 1 response: 2 ranked + 1 normal + 1 ARAM = 4 matches, total=40 (so pagination is available)
export const PAGE_1_RESPONSE: PaginatedMatchList = {
  data: [RANKED_MATCH_1, RANKED_MATCH_2, NORMAL_MATCH, ARAM_MATCH],
  meta: {
    page: 1,
    limit: 20,
    total: 40,
    last_page: 2,
    stale: false,
    stale_reason: null,
  },
};

// Page 2 response: 2 more ranked matches for pagination test
export const PAGE_2_RESPONSE: PaginatedMatchList = {
  data: [
    {
      ...RANKED_MATCH_1,
      match_id: "NA1_005",
      game_start_timestamp: Date.now() - 18_000_000,
    },
    {
      ...RANKED_MATCH_2,
      match_id: "NA1_006",
      game_start_timestamp: Date.now() - 21_600_000,
    },
  ],
  meta: {
    page: 2,
    limit: 20,
    total: 40,
    last_page: 2,
    stale: false,
    stale_reason: null,
  },
};

export const ACCOUNT_RESPONSE = {
  id: "summoner-id-123",
  puuid: TEST_PUUID,
  riot_id: "TestUser#NA1",
  summoner_name: "TestUser",
  profile_icon_id: 1,
};

export {TEST_PUUID, TEST_RIOT_ID};
