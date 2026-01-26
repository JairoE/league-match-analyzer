import type { UserSession } from "./types/user";

export function getUserId(user: UserSession | null): string | null {
  if (!user) return null;
  const candidate =
    user.id ?? user.userId ?? user.user_id ?? (user as { uid?: string | number }).uid;
  if (candidate === undefined || candidate === null) return null;
  return String(candidate);
}

export function getUserDisplayName(user: UserSession | null): string {
  if (!user) return "Unknown Summoner";
  const name =
    user.summonerName ??
    user.summoner_name ??
    user.gameName ??
    (user as { name?: string }).name ??
    "Unknown Summoner";
  const tag = user.tagLine ? `#${user.tagLine}` : "";
  return `${name}${tag}`;
}
