"use client";

import {useEffect, useRef, useState} from "react";
import {apiGet} from "../api";
import {useAppError} from "../errors/error-store";
import type {AnalysisChampion} from "../types/analysis";

const LOG_TAG = "useAnalysisChampions";

// After a refresh, freshly-ingested matches are extracted and scored
// asynchronously (a few seconds later). Re-poll the eligibility list a bounded
// number of times so a newly-scored champion surfaces in the picker without a
// manual second refresh. Silent (no loading state); stops early once a new
// champion appears.
const REPOLL_ATTEMPTS = 3;
const REPOLL_INTERVAL_MS = 5000;

type UseAnalysisChampionsOptions = {
  refreshIndex?: number;
};

type UseAnalysisChampionsResult = {
  champions: AnalysisChampion[];
  isLoading: boolean;
  error: string | null;
};

/** Loads the champions with scored account actions eligible for AI Coach. */
export function useAnalysisChampions(
  riotAccountId: string | null,
  options?: UseAnalysisChampionsOptions
): UseAnalysisChampionsResult {
  const {refreshIndex = 0} = options ?? {};
  const [champions, setChampions] = useState<AnalysisChampion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const {errorMessage, reportError, clearError} = useAppError(
    "analysis.champions"
  );
  // Track the previous account + refreshIndex so re-polling fires only for an
  // actual refresh of the same account — not the initial mount or an account
  // switch (where nothing new is being scored).
  const prevAccountRef = useRef<string | null>(null);
  const prevRefreshIndexRef = useRef<number | null>(null);

  useEffect(() => {
    let isActive = true;
    const timers: ReturnType<typeof setTimeout>[] = [];

    const triggeredByRefresh =
      prevAccountRef.current === riotAccountId &&
      prevRefreshIndexRef.current !== null &&
      prevRefreshIndexRef.current !== refreshIndex;
    prevAccountRef.current = riotAccountId;
    prevRefreshIndexRef.current = refreshIndex;

    if (!riotAccountId) {
      setChampions([]);
      setIsLoading(false);
      clearError();
      return () => {
        isActive = false;
      };
    }

    const url = `/riot-accounts/${riotAccountId}/analysis/champions`;
    const fetchChampions = () =>
      apiGet<AnalysisChampion[]>(url, {useCache: false});

    const scheduleRepoll = (attempt: number, baselineCount: number) => {
      if (attempt > REPOLL_ATTEMPTS) return;
      const timer = setTimeout(async () => {
        if (!isActive) return;
        try {
          const next = await fetchChampions();
          if (!isActive) return;
          setChampions(next);
          console.debug(`[${LOG_TAG}] repoll`, {
            riotAccountId,
            attempt,
            count: next.length,
          });
          // Stop once a newly-scored champion has appeared; keep polling
          // (up to the cap) while the list is unchanged.
          if (next.length > baselineCount) return;
          scheduleRepoll(attempt + 1, baselineCount);
        } catch (error) {
          // Re-polls are best-effort: keep the last good list, never surface.
          console.debug(`[${LOG_TAG}] repoll failed`, {riotAccountId, error});
        }
      }, REPOLL_INTERVAL_MS);
      timers.push(timer);
    };

    const load = async () => {
      setChampions([]);
      setIsLoading(true);
      clearError();
      console.debug(`[${LOG_TAG}] fetch start`, {riotAccountId});
      try {
        const response = await fetchChampions();
        if (!isActive) return;
        setChampions(response);
        console.debug(`[${LOG_TAG}] fetch done`, {
          riotAccountId,
          count: response.length,
        });
        if (triggeredByRefresh) {
          scheduleRepoll(1, response.length);
        }
      } catch (error) {
        if (!isActive) return;
        console.debug(`[${LOG_TAG}] fetch failed`, {riotAccountId, error});
        setChampions([]);
        reportError(error);
      } finally {
        if (isActive) setIsLoading(false);
      }
    };

    void load();
    return () => {
      isActive = false;
      timers.forEach((timer) => clearTimeout(timer));
    };
  }, [riotAccountId, refreshIndex, clearError, reportError]);

  return {
    champions,
    isLoading,
    error: errorMessage || null,
  };
}
