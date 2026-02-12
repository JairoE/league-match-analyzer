import type {UserSession} from "./types/user";

export function getUserId(user: UserSession | null): string | null {
  if (!user) return null;
  return user.id ?? null;
}

export function getRiotAccountId(user: UserSession | null): string | null {
  if (!user?.riot_account?.id) return null;
  return user.riot_account.id;
}

export function getUserDisplayName(user: UserSession | null): string {
  if (!user?.riot_account) return "Unknown Summoner";
  const account = user.riot_account;
  return account.summonerName ?? account.riot_id ?? "Unknown Summoner";
}

export function getUserPuuid(user: UserSession | null): string | null {
  if (!user?.riot_account?.puuid) return null;
  return user.riot_account.puuid;
}
