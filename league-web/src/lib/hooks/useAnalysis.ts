"use client";

import {useCallback, useEffect, useRef, useState} from "react";
import {apiGet, apiPost} from "../api";
import {useAppError} from "../errors/error-store";
import type {
  AnalysisEnqueueResponse,
  AnalysisResponse,
} from "../types/analysis";

const LOG_TAG = "useAnalysis";
const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 30; // 60s total

const TIMEOUT_MESSAGE =
  "Analysis is taking longer than expected. Try again later.";

type AnalysisStatus = "idle" | "requesting" | "polling" | "done" | "timeout";

type UseAnalysisResult = {
  analysis: AnalysisResponse | null;
  isLoading: boolean;
  status: AnalysisStatus;
  error: string | null;
  /** Champion id of the request behind the current panel/loading state. */
  requestedChampionId: number | null;
  requestAnalysis: (
    championId: number,
    rankTier: string | null
  ) => Promise<void>;
  dismiss: () => void;
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Drives the AI Coach flow: POST enqueues the backend analysis job,
 * then polls GET (cache bypassed — a cached null would never resolve)
 * until a persisted result appears or the 60s budget runs out.
 */
export function useAnalysis(riotAccountId: string | null): UseAnalysisResult {
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [status, setStatus] = useState<AnalysisStatus>("idle");
  const [timeoutMessage, setTimeoutMessage] = useState<string | null>(null);
  const [requestedChampionId, setRequestedChampionId] = useState<number | null>(
    null
  );
  const {errorMessage, reportError, clearError} = useAppError("analysis");
  const runIdRef = useRef(0);

  // Invalidate any in-flight polling loop on account change/unmount.
  useEffect(() => {
    return () => {
      runIdRef.current += 1;
    };
  }, [riotAccountId]);

  // Reset visible state when the account changes (render-time adjustment —
  // setState in an effect body trips react-hooks/set-state-in-effect).
  const [lastAccountId, setLastAccountId] = useState(riotAccountId);
  if (riotAccountId !== lastAccountId) {
    setLastAccountId(riotAccountId);
    setAnalysis(null);
    setStatus("idle");
    setTimeoutMessage(null);
    setRequestedChampionId(null);
  }

  const fetchAnalysis = useCallback(
    async (championName: string): Promise<AnalysisResponse | null> => {
      if (!riotAccountId) return null;
      const query = new URLSearchParams({champion_name: championName});
      return apiGet<AnalysisResponse | null>(
        `/riot-accounts/${riotAccountId}/analysis?${query.toString()}`,
        {useCache: false}
      );
    },
    [riotAccountId]
  );

  const requestAnalysis = useCallback(
    async (championId: number, rankTier: string | null) => {
      if (!riotAccountId) return;
      const runId = ++runIdRef.current;
      setStatus("requesting");
      // Clear any previously shown analysis so switching champions doesn't
      // leave a stale panel up while the new one loads.
      setAnalysis(null);
      setRequestedChampionId(championId);
      setTimeoutMessage(null);
      clearError();
      console.debug(`[${LOG_TAG}] request`, {riotAccountId, championId});
      try {
        const enqueue = await apiPost<
          {champion_id: number; rank_tier: string | null},
          AnalysisEnqueueResponse
        >(`/riot-accounts/${riotAccountId}/analysis`, {
          champion_id: championId,
          rank_tier: rankTier,
        });
        if (runIdRef.current !== runId) return;

        if (enqueue.status === "already_exists") {
          const cached = await fetchAnalysis(enqueue.champion_name);
          if (runIdRef.current !== runId) return;
          setAnalysis(cached);
          setStatus(cached ? "done" : "timeout");
          if (!cached) setTimeoutMessage(TIMEOUT_MESSAGE);
          return;
        }

        setStatus("polling");
        for (let poll = 0; poll < MAX_POLLS; poll++) {
          await sleep(POLL_INTERVAL_MS);
          if (runIdRef.current !== runId) return;
          const result = await fetchAnalysis(enqueue.champion_name);
          if (runIdRef.current !== runId) return;
          if (result) {
            console.debug(`[${LOG_TAG}] result`, {polls: poll + 1});
            setAnalysis(result);
            setStatus("done");
            return;
          }
        }
        console.debug(`[${LOG_TAG}] timeout`, {riotAccountId, championId});
        setStatus("timeout");
        setTimeoutMessage(TIMEOUT_MESSAGE);
      } catch (err) {
        console.debug(`[${LOG_TAG}] error`, {err});
        if (runIdRef.current !== runId) return;
        setStatus("idle");
        reportError(err);
      }
    },
    [riotAccountId, fetchAnalysis, clearError, reportError]
  );

  const dismiss = useCallback(() => {
    runIdRef.current += 1;
    setAnalysis(null);
    setStatus("idle");
    setTimeoutMessage(null);
    setRequestedChampionId(null);
    clearError();
  }, [clearError]);

  return {
    analysis,
    isLoading: status === "requesting" || status === "polling",
    status,
    // errorMessage is "" (not null) when the scope has no error
    error: timeoutMessage ?? (errorMessage || null),
    requestedChampionId,
    requestAnalysis,
    dismiss,
  };
}
