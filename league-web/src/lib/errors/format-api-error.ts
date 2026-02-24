import type {ApiError} from "./types";

/**
 * Maps machine-readable detail codes sent by the backend to user-friendly
 * messages. Add an entry here whenever the backend introduces a new code.
 */
const DETAIL_MESSAGES: Record<string, string> = {
  // HTTP 400 – bad input
  invalid_riot_id: "Invalid Riot ID. Expected format: GameName#TagLine.",

  // Riot API proxy errors (RiotRequestError → exceptions.py handler)
  // Note: riot_api_failed is handled separately below because its meaning
  // depends on the riotStatus code (404 = not found vs 401 = bad key, etc.).
  riot_api_max_retries_exceeded:
    "Riot servers are busy. Please wait a moment and try again.",
  missing_riot_api_key: "Service configuration error. Please try again later.",
  unexpected_rank_payload_format:
    "Unable to load rank data. Please try again later.",
};

function statusFallback(status: number): string {
  if (status === 400) return "Invalid request. Please check your input and try again.";
  if (status === 401) return "Authentication required. Please sign in.";
  if (status === 403) return "Access denied.";
  if (status === 404) return "Not found. Please check your input and try again.";
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status >= 500) return "Server error. Please try again later.";
  return "Something went wrong. Please try again.";
}

export function formatApiError(error: ApiError | null): string {
  if (!error) return "";

  // riot_api_failed carries riotStatus which determines the actual failure
  // reason — branch on it before falling through to the flat lookup table.
  if (error.detail === "riot_api_failed") {
    if (error.riotStatus === 404) return "Account not found. Please check the summoner name and try again.";
    if (error.riotStatus === 429) return "Riot servers are busy. Please wait a moment and try again.";
    return "Unable to reach Riot servers. Please try again.";
  }

  // Translate other known machine-readable detail codes — omit riotStatus from
  // the user-visible message since it is a debugging detail, not a user action.
  if (error.detail !== null && DETAIL_MESSAGES[error.detail] !== undefined) {
    return DETAIL_MESSAGES[error.detail];
  }

  // For HTTP errors use the detail string if it looks human-readable, else
  // fall back to a status-based generic message.
  if (error.status !== null) {
    const base = error.detail ?? statusFallback(error.status);
    return error.riotStatus !== null ? `${base} (riot: ${error.riotStatus})` : base;
  }

  // Network / internal errors: show the detail directly without a misleading
  // "Network error" prefix, or fall back to a generic message.
  return error.detail ?? "Something went wrong. Please try again.";
}
