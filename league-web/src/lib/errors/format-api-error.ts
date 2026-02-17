import type {ApiError} from "./types";

export function formatApiError(error: ApiError | null): string {
  if (!error) return "";

  const statusPart = error.status !== null ? `${error.status}` : "Network error";
  const detailPart =
    error.detail ??
    (error.statusText && error.statusText.trim().length > 0
      ? error.statusText
      : "Request failed");

  let message = `${statusPart} ${detailPart}`.trim();
  if (error.riotStatus !== null) {
    message = `${message} (riot: ${error.riotStatus})`;
  }
  return message;
}
