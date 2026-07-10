"use client";

import styles from "./AnalysisButton.module.css";

type AnalysisButtonProps = {
  championName: string | null;
  isLoading: boolean;
  isPanelOpen: boolean;
  disabled: boolean;
  onClick: () => void;
};

/**
 * SubHeader action that triggers the AI Coach analysis for the
 * viewer's most-played champion, or hides the open panel.
 */
export default function AnalysisButton({
  championName,
  isLoading,
  isPanelOpen,
  disabled,
  onClick,
}: AnalysisButtonProps) {
  const label = isLoading
    ? "Analyzing…"
    : isPanelOpen
      ? "Hide AI Coach"
      : championName
        ? `AI Coach: ${championName}`
        : "AI Coach";

  return (
    <button
      className={styles.button}
      onClick={onClick}
      disabled={disabled || isLoading}
      data-testid="ai-coach-button"
    >
      {isLoading ? <span className={styles.spinner} aria-hidden /> : null}
      {label}
    </button>
  );
}
