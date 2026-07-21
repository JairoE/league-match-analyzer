"use client";

import {useEffect, useState} from "react";
import {apiGet} from "../api";
import {useAppError} from "../errors/error-store";
import type {AnalysisChampion} from "../types/analysis";

const LOG_TAG = "useAnalysisChampions";

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

  useEffect(() => {
    let isActive = true;

    if (!riotAccountId) {
      setChampions([]);
      setIsLoading(false);
      clearError();
      return () => {
        isActive = false;
      };
    }

    const loadChampions = async () => {
      setChampions([]);
      setIsLoading(true);
      clearError();
      console.debug(`[${LOG_TAG}] fetch start`, {riotAccountId});
      try {
        const response = await apiGet<AnalysisChampion[]>(
          `/riot-accounts/${riotAccountId}/analysis/champions`,
          {useCache: false}
        );
        if (!isActive) return;
        setChampions(response);
        console.debug(`[${LOG_TAG}] fetch done`, {
          riotAccountId,
          count: response.length,
        });
      } catch (error) {
        if (!isActive) return;
        console.debug(`[${LOG_TAG}] fetch failed`, {riotAccountId, error});
        setChampions([]);
        reportError(error);
      } finally {
        if (isActive) setIsLoading(false);
      }
    };

    void loadChampions();
    return () => {
      isActive = false;
    };
  }, [riotAccountId, refreshIndex, clearError, reportError]);

  return {
    champions,
    isLoading,
    error: errorMessage || null,
  };
}
