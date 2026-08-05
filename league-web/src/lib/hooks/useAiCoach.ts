"use client";

import {useCallback, useState} from "react";
import {useAnalysis} from "./useAnalysis";
import {useAnalysisChampions} from "./useAnalysisChampions";
import type {
  AnalysisChampion,
  AnalysisResponse,
} from "../types/analysis";

type UseAiCoachArgs = {
  riotAccountId: string | null;
  rankTier: string | null;
  refreshIndex?: number;
};

type UseAiCoachResult = {
  champions: AnalysisChampion[];
  selectedChampion: AnalysisChampion | null;
  selectChampion: (championId: number) => void;
  isOptionsLoading: boolean;
  optionsError: string | null;
  analysis: AnalysisResponse | null;
  analysisError: string | null;
  isAnalyzing: boolean;
  isAnalysisForSelectedChampion: boolean;
  isAnalysisOpen: boolean;
  handleAnalysisClick: () => void;
  dismissAnalysis: () => void;
};

/**
 * Shared AI Coach wiring for the match pages: server-provided champion
 * eligibility, picker state, the analysis request/poll flow, and the
 * panel-open invariant tying the visible panel to the picked champion.
 */
export function useAiCoach({
  riotAccountId,
  rankTier,
  refreshIndex = 0,
}: UseAiCoachArgs): UseAiCoachResult {
  const {
    analysis,
    isLoading: isAnalyzing,
    error: analysisError,
    requestedChampionId,
    requestAnalysis,
    dismiss: dismissAnalysis,
  } = useAnalysis(riotAccountId);
  const {
    champions,
    isLoading: isOptionsLoading,
    error: optionsError,
  } = useAnalysisChampions(riotAccountId, {refreshIndex});

  const [pickedChampionId, setPickedChampionId] = useState<number | null>(
    null
  );
  // Drop a stale pick when the account changes (render-time adjustment —
  // setState in an effect body trips react-hooks/set-state-in-effect).
  const [lastAccountId, setLastAccountId] = useState(riotAccountId);
  if (riotAccountId !== lastAccountId) {
    setLastAccountId(riotAccountId);
    setPickedChampionId(null);
  }
  // Fall back to the endpoint's highest-scored eligible champion when the
  // current pick is absent or becomes ineligible after a refresh.
  const selectedChampion =
    champions.find((champion) => champion.champion_id === pickedChampionId) ??
    champions[0] ??
    null;

  const isAnalysisForSelectedChampion =
    requestedChampionId !== null &&
    requestedChampionId === (selectedChampion?.champion_id ?? null);
  const isAnalysisOpen =
    (analysis !== null || analysisError !== null) &&
    isAnalysisForSelectedChampion;

  const selectChampion = useCallback(
    (championId: number) => {
      if (
        requestedChampionId !== null &&
        requestedChampionId !== championId
      ) {
        dismissAnalysis();
      }
      setPickedChampionId(championId);
    },
    [dismissAnalysis, requestedChampionId]
  );

  const handleAnalysisClick = useCallback(() => {
    if (isAnalysisOpen) {
      dismissAnalysis();
      return;
    }
    if (!selectedChampion) return;
    // Pin the implicit selection at request time so a later re-poll reorder
    // of `champions` can't change what `selectedChampion` resolves to out
    // from under an in-flight or already-open analysis.
    setPickedChampionId(selectedChampion.champion_id);
    void requestAnalysis(selectedChampion.champion_id, rankTier);
  }, [
    isAnalysisOpen,
    dismissAnalysis,
    selectedChampion,
    requestAnalysis,
    rankTier,
  ]);

  return {
    champions,
    selectedChampion,
    selectChampion,
    isOptionsLoading,
    optionsError,
    analysis,
    analysisError,
    isAnalyzing,
    isAnalysisForSelectedChampion,
    isAnalysisOpen,
    handleAnalysisClick,
    dismissAnalysis,
  };
}
