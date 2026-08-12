"use client";

import {useEffect, useRef, useState} from "react";
import {apiGet} from "../api";
import {useAppError} from "../errors/error-store";
import type {AnalysisChampion} from "../types/analysis";

const LOG_TAG = "useAnalysisChampions";

// After a refresh — or the first search of a summoner, which triggers the
// same async extraction+scoring on the backend — freshly-ingested matches
// are extracted and scored asynchronously (a few seconds later). Re-poll the
// eligibility list a bounded number of times so a newly-scored champion
// surfaces in the picker without a manual second refresh. Silent (no loading
// state); stops early once a champion outside the baseline appears.
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
  // Track the previous account + refreshIndex so re-polling fires for an
  // actual refresh of the same account, or for an account becoming known for
  // the first time (first search) — not a subsequent bare re-render where
  // nothing new is being scored.
  const prevAccountRef = useRef<string | null>(null);
  const prevRefreshIndexRef = useRef<number | null>(null);

  useEffect(() => {
    let isActive = true;
    const timers: ReturnType<typeof setTimeout>[] = [];

    const accountBecameKnown =
      prevAccountRef.current !== riotAccountId && riotAccountId !== null;
    const refreshedSameAccount =
      prevAccountRef.current === riotAccountId &&
      prevRefreshIndexRef.current !== null &&
      prevRefreshIndexRef.current !== refreshIndex;
    const shouldRepoll = accountBecameKnown || refreshedSameAccount;
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

    const scheduleRepoll = (attempt: number, baselineIds: Set<number>) => {
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
          // Stop once a champion outside the baseline has appeared (a true
          // newly-scored champion, not just a same-length reorder from
          // scores changing); keep polling (up to the cap) otherwise.
          const hasNewChampion = next.some(
            (champion) => !baselineIds.has(champion.champion_id)
          );
          if (hasNewChampion) return;
          scheduleRepoll(attempt + 1, baselineIds);
        } catch (error) {
          // Re-polls are best-effort: keep the last good list, never surface.
          console.debug(`[${LOG_TAG}] repoll failed`, {riotAccountId, error});
          if (isActive) scheduleRepoll(attempt + 1, baselineIds);
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
        if (shouldRepoll) {
          scheduleRepoll(1, new Set(response.map((c) => c.champion_id)));
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
