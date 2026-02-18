import {ApiError, type ApiErrorPayload, isApiError} from "./types";

type ApiErrorResponseInit = {
  url: string;
  method: string;
  status: number;
  statusText: string;
  rawBody: string;
};

function parseJsonBody(rawBody: string): ApiErrorPayload | null {
  if (!rawBody) return null;
  try {
    const parsed = JSON.parse(rawBody) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as ApiErrorPayload;
    }
    return null;
  } catch {
    return null;
  }
}

function pickDetail(payload: ApiErrorPayload | null): string | null {
  if (!payload) return null;
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim().length > 0) {
    return detail.trim();
  }
  const message = payload.message;
  if (typeof message === "string" && message.trim().length > 0) {
    return message.trim();
  }
  return null;
}

function pickRiotStatus(payload: ApiErrorPayload | null): number | null {
  if (!payload) return null;
  const riotStatus = payload.riot_status;
  return typeof riotStatus === "number" ? riotStatus : null;
}

export function buildApiErrorFromResponse(
  init: ApiErrorResponseInit
): ApiError {
  const payload = parseJsonBody(init.rawBody);
  const detail = pickDetail(payload);
  const riotStatus = pickRiotStatus(payload);

  return new ApiError({
    url: init.url,
    method: init.method,
    status: init.status,
    statusText: init.statusText,
    detail,
    riotStatus,
    rawBody: init.rawBody,
    payload,
  });
}

export function toApiError(error: unknown): ApiError {
  if (isApiError(error)) {
    return error;
  }

  if (error instanceof Error) {
    return new ApiError({
      status: null,
      detail: error.message,
      message: error.message,
    });
  }

  return new ApiError({
    status: null,
    detail: "Unknown error",
    message: "Unknown error",
  });
}
