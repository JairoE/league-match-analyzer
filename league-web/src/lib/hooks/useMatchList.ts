"use client";

import {useCallback, useEffect, useMemo, useRef, useState} from "react";
import {apiGet} from "../api";
import {clearCache} from "../cache";
import {useAppError} from "../errors/error-store";
import {getMatchId} from "../match-utils";
import type {
  MatchDetail,
  MatchSummary,
  PaginatedMatchList,
  PaginationMeta,
} from "../types/match";

const MAX_POLLS = 20;
const POLL_INTERVAL_MS = 3_000;

type UseMatchListOptions = {
  matchesUrl: (page: number) => string;
  errorScope: string;
  enabled?: boolean;
  cacheOptions?: {cacheTtlMs?: number; useCache?: boolean};
  logTag?: string;
  /**
   * When provided, called instead of the default `reportError`.
   * Return `true` to suppress the default error handling.
   */
  onFetchError?: (err: unknown) => boolean;
  /** When this value changes, page resets to 1 (e.g. riotId). */
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
  reportError: (err: unknown) => void;
  clearError: () => void;
  handlePageChange: (newPage: number) => void;
  handleRefresh: () => void;
  loadMoreMatches: () => Promise<void>;
  refreshIndex: number;
};

export function useMatchList({
  matchesUrl,
  errorScope,
  enabled = true,
  cacheOptions,
  logTag = "useMatchList",
  onFetchError,
  resetKey,
}: UseMatchListOptions): UseMatchListReturn {
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [matchDetails, setMatchDetails] = useState<
    Record<string, MatchDetail>
  >({});
  const [isLoading, setIsLoading] = useState(false);
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [page, setPage] = useState(1);
  const [paginationMeta, setPaginationMeta] =
    useState<PaginationMeta | null>(null);
  const {errorMessage, reportError, clearError} =
    useAppError(errorScope);

  const [isLoadingMore, setIsLoadingMore] = useState(false);
  // Tracks total matches currently loaded — used as the `after` offset for
  // the next load-more request.
  const [loadMoreOffset, setLoadMoreOffset] = useState(0);
  const [yearBoundaryReached, setYearBoundaryReached] = useState(false);
  // True after loadMoreMatches has appended at least one batch. Prevents the
  // polling effect from overwriting the accumulated matches array.
  const hasLoadedMore = useRef(false);

  const cacheOptionsRef = useRef(cacheOptions);
  cacheOptionsRef.current = cacheOptions;
  const onFetchErrorRef = useRef(onFetchError);
  onFetchErrorRef.current = onFetchError;
  const logTagRef = useRef(logTag);
  logTagRef.current = logTag;

  // Reset page when the identity key changes (e.g. new riotId)
  useEffect(() => {
    setPage(1);
  }, [resetKey]);

  const pollCountRef = useRef(0);
  const hasMatches = matches.length > 0;
  const missingDetailCount = useMemo(
    () => matches.filter((m) => !m.game_info?.info).length,
    [matches]
  );

  // Fetch matches
  useEffect(() => {
    if (!enabled) return;
    let isActive = true;
    const tag = logTagRef.current;

    const load = async () => {
      setIsLoading(true);
      clearError();
      const url = matchesUrl(page);
      console.debug(`[${tag}] fetching matches`, {url, page});
      try {
        const res = await apiGet<PaginatedMatchList>(
          url,
          cacheOptionsRef.current ?? {useCache: false}
        );
        if (!isActive) return;
        const fetched = Array.isArray(res?.data) ? res.data : [];
        setMatches(fetched);
        setPaginationMeta(res?.meta ?? null);
        setLoadMoreOffset(0);
        setYearBoundaryReached(false);
        hasLoadedMore.current = false;
        console.debug(`[${tag}] matches loaded`, {
          count: res?.data?.length ?? 0,
        });
      } catch (err) {
        console.debug(`[${tag}] matches fetch failed`, {
          err,
        });
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
  }, [enabled, matchesUrl, page, refreshIndex, clearError, reportError]);

  // Seed matchDetails from game_info in the list response
  useEffect(() => {
    if (!matches.length) {
      setMatchDetails({});
      return;
    }
    const seeded: Record<string, MatchDetail> = {};
    for (const match of matches) {
      const matchId = getMatchId(match);
      if (matchId && match.game_info?.info) {
        seeded[matchId] = match.game_info;
      }
    }
    if (Object.keys(seeded).length > 0) {
      setMatchDetails((prev) => ({...prev, ...seeded}));
    }
  }, [matches]);

  // Reset poll counter on refresh or page change
  useEffect(() => {
    pollCountRef.current = 0;
  }, [refreshIndex, page]);

  // Poll until all game_info fields are populated.
  // Skip polling once load-more has appended extra pages — polling fetches a
  // single page and would overwrite the accumulated matches array.
  useEffect(() => {
    if (!enabled || !hasMatches || isLoading) return;
    if (hasLoadedMore.current) return;
    const tag = logTagRef.current;
    if (missingDetailCount === 0) {
      console.debug(
        `[${tag}] all match details present, no polling needed`
      );
      return;
    }

    let isActive = true;
    const url = matchesUrl(page);

    console.debug(`[${tag}] starting detail polling`, {
      missing: missingDetailCount,
    });

    const poll = setInterval(async () => {
      if (!isActive) return;
      pollCountRef.current++;

      if (pollCountRef.current >= MAX_POLLS) {
        console.debug(
          `[${tag}] polling max reached, stopping`
        );
        clearInterval(poll);
        return;
      }

      try {
        const fresh = await apiGet<PaginatedMatchList>(url, {
          useCache: false,
        });
        if (!isActive) return;

        const freshArray = Array.isArray(fresh?.data)
          ? fresh.data
          : [];
        const stillMissing = freshArray.some(
          (m) => !m.game_info?.info
        );

        setMatches(freshArray);
        setPaginationMeta(fresh?.meta ?? null);

        if (!stillMissing) {
          console.debug(
            `[${tag}] all details populated, stopping poll`
          );
          clearInterval(poll);
        } else {
          console.debug(`[${tag}] poll incomplete`, {
            poll: pollCountRef.current,
            stillMissing: freshArray.filter(
              (m) => !m.game_info?.info
            ).length,
          });
        }
      } catch (err) {
        console.debug(`[${tag}] poll error`, {
          err,
          poll: pollCountRef.current,
        });
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
  ]);

  // Show "See more" only when the user is on the last page (earliest matches
  // are visible) and no hard stop has been hit (year boundary or empty page).
  const canLoadMore = useMemo(() => {
    if (!paginationMeta || isLoadingMore || yearBoundaryReached) return false;
    return paginationMeta.page === paginationMeta.last_page;
  }, [paginationMeta, isLoadingMore, yearBoundaryReached]);

  const loadMoreMatches = useCallback(async () => {
    if (!canLoadMore) return;
    setIsLoadingMore(true);

    // Tell the backend how many matches we already have so it can skip
    // them and return the next batch (fetching from Riot if the DB is
    // exhausted).
    const offset = loadMoreOffset || matches.length;
    const baseUrl = matchesUrl(page);
    const sep = baseUrl.includes("?") ? "&" : "?";
    const url = `${baseUrl}${sep}after=${offset}`;
    try {
      const res = await apiGet<PaginatedMatchList>(url, {
        useCache: false,
      });
      const newMatches = Array.isArray(res?.data) ? res.data : [];

      // Filter matches from before the current calendar year
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

      // No data returned or year boundary crossed — stop showing button
      if (
        newMatches.length === 0 ||
        filtered.length < newMatches.length
      ) {
        setYearBoundaryReached(true);
      }

      if (filtered.length > 0) {
        setMatches((prev) => [...prev, ...filtered]);
        setLoadMoreOffset(offset + filtered.length);
        hasLoadedMore.current = true;
      }
      // Do NOT update paginationMeta — keep showing the original page's
      // meta so the Pagination component displays the correct page/total.
    } catch (err) {
      reportError(err);
    } finally {
      setIsLoadingMore(false);
    }
  }, [canLoadMore, matchesUrl, page, loadMoreOffset, matches.length, reportError]);

  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage);
    setMatchDetails({});
    window.scrollTo(0, 0);
  }, []);

  const handleRefresh = useCallback(() => {
    console.debug(`[${logTagRef.current}] manual refresh`);
    clearCache();
    setPage(1);
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
    reportError,
    clearError,
    handlePageChange,
    handleRefresh,
    loadMoreMatches,
    refreshIndex,
  };
}
