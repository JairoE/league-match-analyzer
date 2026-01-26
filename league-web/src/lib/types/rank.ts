export type RankInfo = {
  tier?: string;
  rank?: string;
  leaguePoints?: number;
  wins?: number;
  losses?: number;
  queueType?: string;
  [key: string]: unknown;
};
