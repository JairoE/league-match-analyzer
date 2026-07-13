"use client";

import {useCallback, useMemo, useState} from "react";
import {getPlayedChampions} from "../match-utils";
import {useAnalysis} from "./useAnalysis";
import type {PlayedChampion} from "../match-utils";
import type {AnalysisResponse} from "../types/analysis";
import type {MatchDetail} from "../types/match";

type UseAiCoachArgs = {
  riotAccountId: string | null;
  matchDetails: Record<string, MatchDetail>;
  puuid: string | null;
  rankTier: string | null;
};

type UseAiCoachResult = {
  playedChampions: PlayedChampion[];
  selectedChampion: PlayedChampion | null;
  selectChampion: (championId: number) => void;
  analysis: AnalysisResponse | null;
  analysisError: string | null;
  isAnalyzing: boolean;
  isAnalysisOpen: boolean;
  handleAnalysisClick: () => void;
  dismissAnalysis: () => void;
};

/**
 * Shared AI Coach wiring for the match pages: champion picker state
 * (most-played fallback), the analysis request/poll flow, and the
 * panel-open invariant tying the visible panel to the picked champion.
 */
export function useAiCoach({
  riotAccountId,
  matchDetails,
  puuid,
  rankTier,
}: UseAiCoachArgs): UseAiCoachResult {
  const {
    analysis,
    isLoading: isAnalyzing,
    error: analysisError,
    requestedChampionId,
    requestAnalysis,
    dismiss: dismissAnalysis,
  } = useAnalysis(riotAccountId);

  const playedChampions = useMemo(
    () => getPlayedChampions(matchDetails, puuid),
    [matchDetails, puuid]
  );
  const [pickedChampionId, setPickedChampionId] = useState<number | null>(
    null
  );
  // Fall back to most-played when nothing (or a stale champion) is picked.
  const selectedChampion =
    playedChampions.find((c) => c.championId === pickedChampionId) ??
    playedChampions[0] ??
    null;

  // "Open" relative to the picker: the visible panel belongs to the
  // currently selected champion, so the button toggles it closed.
  const isAnalysisOpen =
    (analysis !== null || analysisError !== null) &&
    requestedChampionId === (selectedChampion?.championId ?? null);

  const handleAnalysisClick = useCallback(() => {
    if (isAnalysisOpen) {
      dismissAnalysis();
      return;
    }
    if (!selectedChampion) return;
    void requestAnalysis(selectedChampion.championId, rankTier);
  }, [
    isAnalysisOpen,
    dismissAnalysis,
    selectedChampion,
    requestAnalysis,
    rankTier,
  ]);

  return {
    playedChampions,
    selectedChampion,
    selectChampion: setPickedChampionId,
    analysis,
    analysisError,
    isAnalyzing,
    isAnalysisOpen,
    handleAnalysisClick,
    dismissAnalysis,
  };
}
