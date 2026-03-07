/**
 * Maps backend stale_reason to user-facing message.
 */
export function getStaleMessage(reason: string | null): string | null {
  if (!reason) return null;
  if (reason === "rate_limited") {
    return "Riot API is temporarily rate limited. Showing cached match data.";
  }
  return "Showing cached data. Some information may be outdated.";
}
