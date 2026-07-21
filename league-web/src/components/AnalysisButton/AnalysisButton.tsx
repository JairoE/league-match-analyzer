"use client";

import styles from "./AnalysisButton.module.css";
import type {AnalysisChampion} from "../../lib/types/analysis";

type AnalysisButtonProps = {
  champions: AnalysisChampion[];
  selectedChampionId: number | null;
  onSelectChampion: (championId: number) => void;
  isLoading: boolean;
  isOptionsLoading: boolean;
  isPanelOpen: boolean;
  disabled: boolean;
  onClick: () => void;
};

/**
 * SubHeader action pairing a champion picker with the AI Coach trigger.
 * Eligible champions come from scored account actions and default to the
 * option with the most scored matches.
 */
export default function AnalysisButton({
  champions,
  selectedChampionId,
  onSelectChampion,
  isLoading,
  isOptionsLoading,
  isPanelOpen,
  disabled,
  onClick,
}: AnalysisButtonProps) {
  const label = isLoading
    ? "Analyzing…"
    : isPanelOpen
      ? "Hide AI Coach"
      : "AI Coach";

  return (
    <span className={styles.group}>
      <select
        className={styles.select}
        data-testid="ai-coach-champion-select"
        aria-label="Champion to analyze"
        value={selectedChampionId ?? ""}
        disabled={disabled || isLoading || isOptionsLoading}
        onChange={(event) => onSelectChampion(Number(event.target.value))}
      >
        {isOptionsLoading ? (
          <option value="">Loading champions…</option>
        ) : champions.length === 0 ? (
          <option value="">No scored champions</option>
        ) : (
          champions.map((champion) => (
            <option key={champion.champion_id} value={champion.champion_id}>
              {champion.champion_name} ({champion.scored_match_count})
            </option>
          ))
        )}
      </select>
      <button
        className={styles.button}
        onClick={onClick}
        disabled={disabled || isLoading || isOptionsLoading}
        data-testid="ai-coach-button"
      >
        {isLoading ? <span className={styles.spinner} aria-hidden /> : null}
        {label}
      </button>
    </span>
  );
}
