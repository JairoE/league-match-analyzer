"use client";

import styles from "./AnalysisButton.module.css";
import type {PlayedChampion} from "../../lib/match-utils";

type AnalysisButtonProps = {
  champions: PlayedChampion[];
  selectedChampionId: number | null;
  onSelectChampion: (championId: number) => void;
  isLoading: boolean;
  isPanelOpen: boolean;
  disabled: boolean;
  onClick: () => void;
};

/**
 * SubHeader action pairing a champion picker with the AI Coach trigger.
 * Any champion from the loaded match history can be analyzed; the picker
 * defaults to the most-played one.
 */
export default function AnalysisButton({
  champions,
  selectedChampionId,
  onSelectChampion,
  isLoading,
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
      {champions.length > 0 ? (
        <select
          className={styles.select}
          data-testid="ai-coach-champion-select"
          aria-label="Champion to analyze"
          value={selectedChampionId ?? ""}
          disabled={isLoading}
          onChange={(event) => onSelectChampion(Number(event.target.value))}
        >
          {champions.map((champion) => (
            <option key={champion.championId} value={champion.championId}>
              {champion.championName} ({champion.count})
            </option>
          ))}
        </select>
      ) : null}
      <button
        className={styles.button}
        onClick={onClick}
        disabled={disabled || isLoading}
        data-testid="ai-coach-button"
      >
        {isLoading ? <span className={styles.spinner} aria-hidden /> : null}
        {label}
      </button>
    </span>
  );
}
