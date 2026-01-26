export type UserSession = {
  id?: number | string;
  userId?: number | string;
  user_id?: number | string;
  puuid?: string;
  summonerName?: string;
  summoner_name?: string;
  gameName?: string;
  tagLine?: string;
  email?: string;
  [key: string]: unknown;
};

export type UserAuthPayload = {
  summoner_name: string;
  email: string;
};
