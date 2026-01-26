import { getFromCache, setInCache } from "./cache";

type ApiFetchOptions = {
  cacheTtlMs?: number;
  useCache?: boolean;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const base = API_BASE_URL.endsWith("/") ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
  const suffix = path.startsWith("/") ? path : `/${path}`;
  const url = `${base}${suffix}`;
  console.debug("[api] buildUrl", { path, url });
  return url;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  options: ApiFetchOptions = {},
): Promise<T> {
  const url = buildUrl(path);
  const method = init.method?.toUpperCase() ?? "GET";
  const useCache = options.useCache ?? method === "GET";
  const cacheKey = `${method}:${url}`;

  if (useCache) {
    const cached = getFromCache<T>(cacheKey);
    if (cached) {
      console.debug("[api] cache hit", { url, method });
      return cached;
    }
  }

  console.debug("[api] fetch", { url, method });
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = await res.text();
    console.debug("[api] error", { url, method, status: res.status, body });
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }

  const data = (await res.json()) as T;
  console.debug("[api] success", { url, method });

  if (useCache) {
    setInCache(cacheKey, data, options.cacheTtlMs);
  }

  return data;
}

export async function apiGet<T>(path: string, options?: ApiFetchOptions): Promise<T> {
  return apiFetch<T>(path, { method: "GET" }, options);
}

export async function apiPost<TBody, TResponse>(
  path: string,
  body: TBody,
  options?: ApiFetchOptions,
): Promise<TResponse> {
  return apiFetch<TResponse>(
    path,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    { ...options, useCache: false },
  );
}
