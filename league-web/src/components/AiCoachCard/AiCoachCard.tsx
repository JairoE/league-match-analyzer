"use client";

import styles from "./AiCoachCard.module.css";
import AnalysisButton from "../AnalysisButton/AnalysisButton";
import AnalysisPanel from "../AnalysisPanel/AnalysisPanel";
import type {
  AnalysisChampion,
  AnalysisResponse,
} from "../../lib/types/analysis";

type AiCoachCardProps = {
  champions: AnalysisChampion[];
  selectedChampionId: number | null;
  onSelectChampion: (championId: number) => void;
  isAnalyzing: boolean;
  isOptionsLoading: boolean;
  isPanelOpen: boolean;
  disabled: boolean;
  onAnalysisClick: () => void;
  analysis: AnalysisResponse | null;
  error: string | null;
  onDismiss: () => void;
};

/**
 * Dedicated AI Coach surface: the champion picker + trigger and the analysis
 * results, grouped in one card that sits apart from the match table. The
 * caption states that coaching draws on the player's full scored history — the
 * picker lists champions by scored-match eligibility, which deliberately
 * differs from the games currently shown, so it must not read as if it were
 * derived from the visible match list.
 */
export default function AiCoachCard({
  champions,
  selectedChampionId,
  onSelectChampion,
  isAnalyzing,
  isOptionsLoading,
  isPanelOpen,
  disabled,
  onAnalysisClick,
  analysis,
  error,
  onDismiss,
}: AiCoachCardProps) {
  return (
    <section className={styles.card} data-testid="ai-coach-card">
      <div className={styles.header}>
        <div className={styles.heading}>
          <h3 className={styles.title}>AI Coach</h3>
          <p className={styles.caption}>
            Coaching draws on your full scored match history — not just the
            games shown below.
          </p>
        </div>
        <AnalysisButton
          champions={champions}
          selectedChampionId={selectedChampionId}
          onSelectChampion={onSelectChampion}
          isLoading={isAnalyzing}
          isOptionsLoading={isOptionsLoading}
          isPanelOpen={isPanelOpen}
          disabled={disabled}
          onClick={onAnalysisClick}
        />
      </div>
      <AnalysisPanel analysis={analysis} error={error} onDismiss={onDismiss} />
    </section>
  );
}
