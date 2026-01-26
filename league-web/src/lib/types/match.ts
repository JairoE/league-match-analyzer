export type MatchSummary = {
  id?: string;
  matchId?: string;
  match_id?: string;
  gameId?: number;
  queueId?: number;
  gameCreation?: number;
  gameStartTimestamp?: number;
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

export type Participant = {
  puuid?: string;
  summonerName?: string;
  gameName?: string;
  tagLine?: string;
  name?: string;
  championId?: number;
  championName?: string;
  kills?: number;
  deaths?: number;
  assists?: number;
  win?: boolean;
  teamId?: number;
  lane?: string;
  role?: string;
  totalMinionsKilled?: number;
  neutralMinionsKilled?: number;
  goldEarned?: number;
  timePlayed?: number;
  [key: string]: unknown;
};

export type Team = {
  teamId?: number;
  win?: boolean | string;
  [key: string]: unknown;
};
