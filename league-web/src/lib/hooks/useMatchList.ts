"use client";

import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {apiGet} from "../api";
import {clearCache} from "../cache";
import {useAppError} from "../errors/error-store";
import {getMatchId} from "../match-utils";
import {getStaleMessage} from "../stale-message";
import type {
  MatchDetail,
  MatchSummary,
  PaginatedMatchList,
  PaginationMeta,
} from "../types/match";

const LIMIT = 20;
const MAX_POLLS = 20;
const POLL_INTERVAL_MS = 3_000;

type MatchListUrlOptions = {refresh?: boolean};

type UseMatchListOptions = {
  matchesUrl: (page: number, opts?: MatchListUrlOptions) => string;
  errorScope: string;
  enabled?: boolean;
  cacheOptions?: {cacheTtlMs?: number; useCache?: boolean};
  logTag?: string;
  onFetchError?: (err: unknown) => boolean;
  resetKey?: string;
};

type UseMatchListReturn = {
  matches: MatchSummary[];
  matchDetails: Record<string, MatchDetail>;
  isLoading: boolean;
  isLoadingMore: boolean;
  canLoadMore: boolean;
  paginationMeta: PaginationMeta | null;
  page: number;
  errorMessage: string | null;
  staleMessage: string | null;
  reportError: (err: unknown) => void;
  clearError: () => void;
  handlePageChange: (newPage: number) => void;
  handleRefresh: () => void;
  loadMoreMatches: () => Promise<void>;
  refreshIndex: number;
};

function buildPaginationMeta(
  page: number,
  total: number,
  limit: number
): PaginationMeta {
  const last_page = Math.max(1, Math.ceil(total / limit));
  return {
    page,
    limit,
    total,
    last_page,
  };
}

export function useMatchList({
  matchesUrl,
  errorScope,
  enabled = true,
  cacheOptions,
  logTag = "useMatchList",
  onFetchError,
  resetKey,
}: UseMatchListOptions): UseMatchListReturn {
  const [allMatches, setAllMatches] = useState<MatchSummary[]>([]);
  const [matchDetails, setMatchDetails] = useState<
    Record<string, MatchDetail>
  >({});
  const [isLoading, setIsLoading] = useState(false);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [page, setPage] = useState(1);
  const [totalFromApi, setTotalFromApi] = useState<number | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [yearBoundaryReached, setYearBoundaryReached] = useState(false);
  const [staleReason, setStaleReason] = useState<string | null>(null);
  const [lastMetaFromApi, setLastMetaFromApi] =
    useState<PaginationMeta | null>(null);
  const nextFetchIsRefreshRef = useRef(false);

  const {errorMessage, reportError, clearError} =
    useAppError(errorScope);

  const cacheOptionsRef = useRef(cacheOptions);
  cacheOptionsRef.current = cacheOptions;
  const onFetchErrorRef = useRef(onFetchError);
  onFetchErrorRef.current = onFetchError;
  const logTagRef = useRef(logTag);
  logTagRef.current = logTag;

  const limit = LIMIT;
  const total = Math.max(totalFromApi ?? 0, allMatches.length);
  const last_page = Math.max(1, Math.ceil(total / limit));
  const paginationMeta = useMemo((): PaginationMeta | null => {
    const base = lastMetaFromApi
      ? {
          ...lastMetaFromApi,
          page,
          total,
          last_page,
        }
      : buildPaginationMeta(page, total, limit);
    return base;
  }, [lastMetaFromApi, page, total, last_page, limit]);

  // Slice for current page — this is what the table displays
  const matches = useMemo(
    () =>
      allMatches.slice((page - 1) * limit, page * limit),
    [allMatches, page, limit]
  );

  const hasMatches = allMatches.length > 0;
  const missingDetailCount = useMemo(
    () => matches.filter((m) => !m.game_info?.info).length,
    [matches]
  );

  // Reset when identity changes (e.g. new riotId)
  useEffect(() => {
    setPage(1);
    setAllMatches([]);
    setTotalFromApi(null);
    setMatchDetails({});
    setYearBoundaryReached(false);
    setStaleReason(null);
    setLastMetaFromApi(null);
  }, [resetKey]);

  // Fetch a page when we don't have enough data for the current page.
  // Accumulates: page 1 replaces, page 2+ appends.
  useEffect(() => {
    if (!enabled) return;
    const needCount = page * limit;
    if (allMatches.length >= needCount) {
      return;
    }
    let isActive = true;
    const tag = logTagRef.current;

    const load = async () => {
      setIsLoading(true);
      clearError();
      const opts =
        nextFetchIsRefreshRef.current
          ? ({refresh: true} as MatchListUrlOptions)
          : undefined;
      if (opts) nextFetchIsRefreshRef.current = false;
      const url = matchesUrl(page, opts);
      console.debug(`[${tag}] fetching matches`, {url, page});
      try {
        const res = await apiGet<PaginatedMatchList>(
          url,
          cacheOptionsRef.current ?? {useCache: false}
        );
        if (!isActive) return;
        const fetched = Array.isArray(res?.data) ? res.data : [];
        const meta = res?.meta ?? null;
        // Any response that includes meta must update both lastMetaFromApi and staleReason so the shell can show a stale warning.
        if (meta?.total != null) setTotalFromApi(meta.total);
        setStaleReason(meta?.stale_reason ?? null);
        setLastMetaFromApi(meta ?? null);

        setAllMatches((prev) => {
          if (page === 1 && prev.length === 0) return fetched;
          const start = (page - 1) * limit;
          return [...prev.slice(0, start), ...fetched];
        });
        console.debug(`[${tag}] matches loaded`, {
          page,
          count: fetched.length,
          totalFromApi: meta?.total,
        });
      } catch (err) {
        console.debug(`[${tag}] matches fetch failed`, {err});
        if (isActive) {
          const handled = onFetchErrorRef.current?.(err);
          if (!handled) reportError(err);
        }
      } finally {
        if (isActive) setIsLoading(false);
      }
    };

    void load();
    return () => {
      isActive = false;
    };
  }, [
    enabled,
    matchesUrl,
    page,
    refreshIndex,
    allMatches.length,
    clearError,
    reportError,
    limit,
  ]);

  // Seed matchDetails from game_info (merge, never clear on page change)
  useEffect(() => {
    if (!allMatches.length) {
      setMatchDetails({});
      return;
    }
    const seeded: Record<string, MatchDetail> = {};
    for (const match of allMatches) {
      const matchId = getMatchId(match);
      if (matchId && match.game_info?.info) {
        seeded[matchId] = match.game_info;
      }
    }
    if (Object.keys(seeded).length > 0) {
      setMatchDetails((prev) => ({...prev, ...seeded}));
    }
  }, [allMatches]);

  const pollCountRef = useRef(0);

  // Poll to fill game_info for the current page only; merge into allMatches
  useEffect(() => {
    if (!enabled || !hasMatches || isLoading) return;
    if (missingDetailCount === 0) return;

    let isActive = true;
    const tag = logTagRef.current;
    const url = matchesUrl(page);

    const poll = setInterval(async () => {
      if (!isActive) return;
      pollCountRef.current++;
      if (pollCountRef.current >= MAX_POLLS) {
        clearInterval(poll);
        return;
      }
      try {
        const fresh = await apiGet<PaginatedMatchList>(url, {
          useCache: false,
        });
        if (!isActive) return;
        if (fresh?.meta != null) {
          setStaleReason(fresh.meta?.stale_reason ?? null);
          setLastMetaFromApi(fresh.meta);
        }
        const freshArray = Array.isArray(fresh?.data) ? fresh.data : [];
        const stillMissing = freshArray.some((m) => !m.game_info?.info);

        setAllMatches((prev) => {
          const start = (page - 1) * limit;
          return [
            ...prev.slice(0, start),
            ...freshArray,
            ...prev.slice(start + freshArray.length),
          ];
        });
        if (!stillMissing) clearInterval(poll);
      } catch (err) {
        console.debug(`[${tag}] poll error`, {err});
      }
    }, POLL_INTERVAL_MS);

    return () => {
      isActive = false;
      clearInterval(poll);
    };
  }, [
    enabled,
    matchesUrl,
    refreshIndex,
    page,
    hasMatches,
    missingDetailCount,
    isLoading,
    limit,
  ]);

  // Reset poll counter when page or refresh changes
  useEffect(() => {
    pollCountRef.current = 0;
  }, [refreshIndex, page]);

  const staleMessage = getStaleMessage(staleReason);

  const canLoadMore = useMemo(() => {
    if (isLoadingMore || yearBoundaryReached) return false;
    return paginationMeta != null && page === paginationMeta.last_page;
  }, [paginationMeta, page, isLoadingMore, yearBoundaryReached]);

  const loadMoreMatches = useCallback(async () => {
    if (!canLoadMore) return;
    setIsLoadingMore(true);
    const offset = allMatches.length;
    const baseUrl = matchesUrl(page);
    const sep = baseUrl.includes("?") ? "&" : "?";
    const url = `${baseUrl}${sep}after=${offset}`;
    const tag = logTagRef.current;
    try {
      const res = await apiGet<PaginatedMatchList>(url, {useCache: false});
      const newMatches = Array.isArray(res?.data) ? res.data : [];
      if (res?.meta) {
        setLastMetaFromApi(res.meta);
        setStaleReason(res.meta?.stale_reason ?? null);
      }

      const currentYearStart = new Date(
        new Date().getFullYear(),
        0,
        1
      ).getTime();
      const filtered = newMatches.filter(
        (m) =>
          (m.game_start_timestamp ?? m.gameCreation ?? Date.now()) >=
          currentYearStart
      );

      if (
        newMatches.length === 0 ||
        filtered.length < newMatches.length
      ) {
        setYearBoundaryReached(true);
      }

      console.debug(`[${tag}] loadMore result`, {
        offset,
        raw: newMatches.length,
        filtered: filtered.length,
      });

      if (filtered.length > 0) {
        const newTotal = offset + filtered.length;
        setAllMatches((prev) => [...prev, ...filtered]);
        setTotalFromApi(newTotal);
        const pageWithFirstNew = Math.floor(offset / limit) + 1;
        setPage(pageWithFirstNew);
        window.scrollTo(0, 0);
      }
    } catch (err) {
      reportError(err);
    } finally {
      setIsLoadingMore(false);
    }
  }, [
    canLoadMore,
    matchesUrl,
    page,
    allMatches.length,
    limit,
    reportError,
  ]);

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
    window.scrollTo(0, 0);
  }, []);

  const handleRefresh = useCallback(() => {
    console.debug(`[${logTagRef.current}] manual refresh`);
    nextFetchIsRefreshRef.current = true;
    clearCache();
    setPage(1);
    setAllMatches([]);
    setTotalFromApi(null);
    setMatchDetails({});
    setYearBoundaryReached(false);
    setStaleReason(null);
    setLastMetaFromApi(null);
    setRefreshIndex((prev) => prev + 1);
  }, []);

  return {
    matches,
    matchDetails,
    isLoading,
    isLoadingMore,
    canLoadMore,
    paginationMeta,
    page,
    errorMessage,
    staleMessage,
    reportError,
    clearError,
    handlePageChange,
    handleRefresh,
    loadMoreMatches,
    refreshIndex,
  };
}
