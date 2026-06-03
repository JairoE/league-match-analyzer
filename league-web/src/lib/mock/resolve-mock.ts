// Demo-mode request router.
//
// `isDemoMode()` decides whether the app runs without a backend. When enabled,
// `resolveMock()` answers every API path from the bundled demo dataset so the
// frontend works as a standalone static deploy (no FastAPI, DB, or Riot key).
//
// Demo mode is enabled when ANY of the following is true:
//   • build-time:  NEXT_PUBLIC_DEMO_MODE === "true"
//   • runtime:     localStorage["league.demoMode"] === "true"
//   • runtime:     the URL contains a `demo=1` query param
//
// The runtime toggles exist so E2E tests (and quick manual demos) can flip the
// app into demo mode against a plain `npm run dev` without rebuilding.

import {ApiError} from "../errors/types";
import {
  canonical,
  DEMO_ACCOUNT,
  DEMO_CHAMPIONS,
  DEMO_EMAIL,
  DEMO_EMPTY_PAGE,
  DEMO_LANE_STATS,
  DEMO_MATCH_PAGE,
  DEMO_RANK,
  DEMO_RIOT_ID,
  DEMO_USER,
  demoChampion,
  demoMatchDetailById,
} from "./demo-data";

export const DEMO_MODE_STORAGE_KEY = "league.demoMode";

export function isDemoMode(): boolean {
  if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") return true;
  if (typeof window === "undefined") return false;
  try {
    if (window.localStorage.getItem(DEMO_MODE_STORAGE_KEY) === "true") {
      return true;
    }
    if (window.location.search.includes("demo=1")) return true;
  } catch {
    // Accessing storage can throw in locked-down browsers — treat as disabled.
  }
  return false;
}

function stripQuery(path: string): string {
  const noQuery = path.split("?")[0];
  // Normalize away any origin so we match on pathname only.
  try {
    if (noQuery.startsWith("http")) return new URL(noQuery).pathname;
  } catch {
    // Fall through and use the raw value.
  }
  return noQuery;
}

/**
 * Resolve an API request against the bundled demo dataset.
 *
 * @param path - The request path passed to apiFetch (may include a query).
 * @param init - The fetch init (used only to read the HTTP method).
 * @returns The canned payload typed as the caller's expected response.
 */
export async function resolveMock<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const pathname = stripQuery(path);
  const body = parseBody(init.body);
  const result = route(method, pathname, path, body);
  console.debug("[demo] resolveMock", {method, pathname, matched: result.tag});
  return result.body as T;
}

type RouteResult = {tag: string; body: unknown};
type RequestBody = Record<string, unknown>;

function parseBody(raw: BodyInit | null | undefined): RequestBody {
  if (typeof raw !== "string" || raw.length === 0) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as RequestBody;
    }
  } catch {
    // Non-JSON body — ignore.
  }
  return {};
}

/** Error mirroring the backend's Riot 404 → frontend "no search results". */
function notFoundError(): ApiError {
  return new ApiError({
    status: 404,
    statusText: "Not Found",
    detail: "riot_api_failed",
    riotStatus: 404,
    message: "riot_api_failed",
  });
}

/** Auth rejection that tells the visitor which demo credentials work. */
function authError(): ApiError {
  return new ApiError({
    status: 404,
    statusText: "Not Found",
    detail: `Demo mode: sign in as ${DEMO_RIOT_ID} with ${DEMO_EMAIL}.`,
    message: "demo_auth_failed",
  });
}

function matchPageFor(fullPath: string): RouteResult {
  const isLoadMore = /[?&]after=/.test(fullPath);
  const isPageTwoPlus = /[?&]page=([2-9]|\d{2,})/.test(fullPath);
  if (isLoadMore || isPageTwoPlus) {
    return {tag: "matches-empty", body: DEMO_EMPTY_PAGE};
  }
  return {tag: "matches", body: DEMO_MATCH_PAGE};
}

function route(
  method: string,
  pathname: string,
  fullPath: string,
  body: RequestBody
): RouteResult {
  // Auth — only the one demo summoner (+ email for sign-in) is accepted.
  if (method === "POST" && /\/users\/sign_in$/.test(pathname)) {
    const summonerOk =
      canonical(String(body.summoner_name ?? "")) === canonical(DEMO_RIOT_ID);
    const emailOk =
      canonical(String(body.email ?? "")) === canonical(DEMO_EMAIL);
    if (summonerOk && emailOk) return {tag: "sign_in", body: DEMO_USER};
    throw authError();
  }
  if (method === "POST" && /\/users\/sign_up$/.test(pathname)) {
    if (canonical(String(body.summoner_name ?? "")) === canonical(DEMO_RIOT_ID)) {
      return {tag: "sign_up", body: DEMO_USER};
    }
    throw authError();
  }

  // Riot account lookup (search flow) — gated by Riot ID.
  const accountMatch = pathname.match(/\/search\/([^/]+)\/account$/);
  if (accountMatch) {
    if (canonical(accountMatch[1]) === canonical(DEMO_RIOT_ID)) {
      return {tag: "account", body: DEMO_ACCOUNT};
    }
    throw notFoundError();
  }

  // Timeline lane stats — must be checked before the generic match route.
  if (/\/matches\/[^/]+\/timeline-stats$/.test(pathname)) {
    return {tag: "timeline-stats", body: DEMO_LANE_STATS};
  }

  // Search match list — gated by Riot ID (mirror the account 404 behavior).
  const searchMatches = pathname.match(/\/search\/([^/]+)\/matches$/);
  if (searchMatches) {
    if (canonical(searchMatches[1]) !== canonical(DEMO_RIOT_ID)) {
      throw notFoundError();
    }
    return matchPageFor(fullPath);
  }

  // Signed-in match list — the session always belongs to the demo user.
  if (/\/riot-accounts\/[^/]+\/matches$/.test(pathname)) {
    return matchPageFor(fullPath);
  }

  // Single match detail.
  const matchDetail = pathname.match(/\/matches\/([^/]+)$/);
  if (matchDetail) {
    return {tag: "match-detail", body: demoMatchDetailById(matchDetail[1])};
  }

  // Rank for the signed-in account.
  if (/\/riot-accounts\/[^/]+\/fetch_rank$/.test(pathname)) {
    return {tag: "rank", body: DEMO_RANK};
  }

  // Batch rank lookup — non-critical, return an empty map.
  if (/\/rank\/batch$/.test(pathname)) {
    return {tag: "rank-batch", body: {}};
  }

  // Single champion by id.
  const champById = pathname.match(/\/champions\/(\d+)$/);
  if (champById) {
    return {tag: "champion", body: demoChampion(Number(champById[1]))};
  }

  // Full champion catalog.
  if (/\/champions$/.test(pathname)) {
    return {tag: "champions", body: DEMO_CHAMPIONS};
  }

  console.warn("[demo] unmatched route — returning empty object", {pathname});
  return {tag: "unmatched", body: {}};
}
