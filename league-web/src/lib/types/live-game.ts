export type LiveGameParticipant = {
  puuid: string;
  championId: number;
  teamId: number;
  summonerId: string;
  /** Riot ID in "GameName#Tag" format (Spectator v5 field) */
  riotId?: string;
  summonerName?: string;
  profileIconId?: number;
  bot?: boolean;
  spell1Id: number;
  spell2Id: number;
  perks?: {
    perkIds: number[];
    perkStyle: number;
    perkSubStyle: number;
  };
};

export type BannedChampion = {
  championId: number;
  teamId: number;
  pickTurn: number;
};

export type LiveGameData = {
  gameId: number;
  gameType: string;
  gameStartTime: number;
  mapId: number;
  gameLength: number;
  gameMode: string;
  gameQueueConfigId: number;
  participants: LiveGameParticipant[];
  bannedChampions: BannedChampion[];
};
