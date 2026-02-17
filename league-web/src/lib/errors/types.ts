export type ApiErrorPayload = Record<string, unknown>;

export type ApiErrorInit = {
  url?: string;
  method?: string;
  status: number | null;
  statusText?: string;
  detail?: string | null;
  riotStatus?: number | null;
  rawBody?: string | null;
  payload?: ApiErrorPayload | null;
  message?: string;
};

export class ApiError extends Error {
  readonly url: string | null;
  readonly method: string | null;
  readonly status: number | null;
  readonly statusText: string | null;
  readonly detail: string | null;
  readonly riotStatus: number | null;
  readonly rawBody: string | null;
  readonly payload: ApiErrorPayload | null;

  constructor(init: ApiErrorInit) {
    const message =
      init.message ??
      `Request failed: ${init.status ?? "unknown"} ${init.statusText ?? ""}`.trim();
    super(message);
    this.name = "ApiError";
    this.url = init.url ?? null;
    this.method = init.method ?? null;
    this.status = init.status;
    this.statusText = init.statusText ?? null;
    this.detail = init.detail ?? null;
    this.riotStatus = init.riotStatus ?? null;
    this.rawBody = init.rawBody ?? null;
    this.payload = init.payload ?? null;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}
