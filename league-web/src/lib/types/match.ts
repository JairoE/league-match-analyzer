export type PaginationMeta = {
  page: number;
  limit: number;
  total: number;
  last_page: number;
  stale?: boolean;
  stale_reason?: string | null;
};

export type PaginatedMatchList = {
  data: MatchSummary[];
  meta: PaginationMeta;
};

export type MatchSummary = {
  id?: string;
  matchId?: string;
  match_id?: string;
  game_id?: string;
  gameId?: number;
  queueId?: number;
  gameCreation?: number;
  gameStartTimestamp?: number;
  game_start_timestamp?: number;
  game_info?: MatchDetail;
  [key: string]: unknown;
};

export type MatchDetail = {
  info?: MatchInfo;
  metadata?: MatchMetadata;
  [key: string]: unknown;
};

export type MatchInfo = {
  gameCreation?: number;
  gameDuration?: number;
  participants?: Participant[];
  teams?: Team[];
  queueId?: number;
  [key: string]: unknown;
};

export type MatchMetadata = {
  matchId?: string;
  [key: string]: unknown;
};

// ── Perk / Rune sub-types ────────────────────────────────────────────

export type PerkSelection = {
  perk?: number;
  var1?: number;
  var2?: number;
  var3?: number;
};

export type PerkStyle = {
  description?: string; // "primaryStyle" | "subStyle"
  selections?: PerkSelection[];
  style?: number; // Rune tree ID (8000=Precision, etc.)
};

export type ParticipantPerks = {
  statPerks?: {defense?: number; flex?: number; offense?: number};
  styles?: PerkStyle[];
};

// ── Participant ──────────────────────────────────────────────────────

export type Participant = {
  // Identity
  puuid?: string;
  summonerName?: string;
  gameName?: string;
  tagLine?: string;
  name?: string;
  riotIdGameName?: string;
  riotIdTagline?: string;
  summonerId?: string;
  summonerLevel?: number;
  participantId?: number;
  profileIcon?: number;

  // Champion & level
  championId?: number;
  championName?: string;
  champLevel?: number;
  champExperience?: number;

  // Core stats
  kills?: number;
  deaths?: number;
  assists?: number;
  win?: boolean;
  teamId?: number;
  lane?: string;
  role?: string;

  // Items (7 slots: 6 items + trinket)
  item0?: number;
  item1?: number;
  item2?: number;
  item3?: number;
  item4?: number;
  item5?: number;
  item6?: number;

  // Summoner spells
  summoner1Id?: number;
  summoner2Id?: number;
  summoner1Casts?: number;
  summoner2Casts?: number;

  // Perks / runes
  perks?: ParticipantPerks;

  // Multikills
  doubleKills?: number;
  tripleKills?: number;
  quadraKills?: number;
  pentaKills?: number;
  killingSprees?: number;
  largestKillingSpree?: number;
  largestMultiKill?: number;

  // Damage dealt
  totalDamageDealt?: number;
  totalDamageDealtToChampions?: number;
  physicalDamageDealt?: number;
  physicalDamageDealtToChampions?: number;
  magicDamageDealt?: number;
  magicDamageDealtToChampions?: number;
  trueDamageDealt?: number;
  trueDamageDealtToChampions?: number;
  largestCriticalStrike?: number;
  damageDealtToObjectives?: number;
  damageDealtToTurrets?: number;
  damageSelfMitigated?: number;

  // Damage taken
  totalDamageTaken?: number;
  physicalDamageTaken?: number;
  magicDamageTaken?: number;
  trueDamageTaken?: number;

  // Healing & shielding
  totalHeal?: number;
  totalHealsOnTeammates?: number;
  totalDamageShieldedOnTeammates?: number;
  totalUnitsHealed?: number;

  // Vision
  visionScore?: number;
  wardsPlaced?: number;
  wardsKilled?: number;
  visionWardsBoughtInGame?: number;
  detectorWardsPlaced?: number;

  // Objectives
  objectivesStolen?: number;
  objectivesStolenAssists?: number;
  turretKills?: number;
  turretTakedowns?: number;
  inhibitorKills?: number;
  inhibitorTakedowns?: number;
  dragonKills?: number;
  baronKills?: number;

  // Gold & economy
  goldEarned?: number;
  goldSpent?: number;
  totalMinionsKilled?: number;
  neutralMinionsKilled?: number;

  // Time stats
  timePlayed?: number;
  longestTimeSpentLiving?: number;
  timeCCingOthers?: number;
  totalTimeSpentDead?: number;
  totalTimeCCDealt?: number;

  // Game end state
  gameEndedInEarlySurrender?: boolean;
  gameEndedInSurrender?: boolean;
  teamEarlySurrendered?: boolean;

  // First blood / events
  firstBloodKill?: boolean;
  firstBloodAssist?: boolean;
  firstTowerKill?: boolean;
  firstTowerAssist?: boolean;

  // Consumables
  consumablesPurchased?: number;
  itemsPurchased?: number;

  // Miscellaneous
  nexusKills?: number;
  nexusTakedowns?: number;
  nexusLost?: number;
  spell1Casts?: number;
  spell2Casts?: number;
  spell3Casts?: number;
  spell4Casts?: number;

  // Escape hatch for unknown fields
  [key: string]: unknown;
};

export type Team = {
  teamId?: number;
  win?: boolean | string;
  [key: string]: unknown;
};

export type LaneStats = {
  cs_diff_at_10?: number | null;
  cs_diff_at_15?: number | null;
  gold_diff_at_10?: number | null;
  gold_diff_at_15?: number | null;
  lane_opponent_name?: string | null;
  lane_opponent_champion?: string | null;
};

export type ChampionKdaPoint = {
  matchId: string;
  kills: number;
  deaths: number;
  assists: number;
  outcome: "victory" | "defeat" | "remake";
  timestamp: number;
};
