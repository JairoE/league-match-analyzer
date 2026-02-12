export type RiotAccountData = {
  id: string;
  summonerName?: string;
  riot_id: string;
  puuid: string;
  profileIconId?: number;
  summonerLevel?: number;
};

export type UserSession = {
  id: string;
  email: string;
  riot_account: RiotAccountData;
};

export type UserAuthPayload = {
  summoner_name: string;
  email: string;
};
