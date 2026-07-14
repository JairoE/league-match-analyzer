"use client";

import styles from "./AnalysisPanel.module.css";
import type {
  AnalysisResponse,
  Recommendation,
} from "../../lib/types/analysis";

const CATEGORY_LABELS: Record<string, string> = {
  item_purchase: "Item",
  objective_kill: "Objective",
  selection_bias: "Bias",
};

function formatDeltaW(gap: number): string {
  const percent = (gap * 100).toFixed(1);
  return gap >= 0 ? `+${percent}% win probability` : `${percent}% win probability`;
}

function RecommendationCard({rec}: {rec: Recommendation}) {
  return (
    <article className={styles.card} data-testid="analysis-recommendation">
      <div className={styles.cardHeader}>
        <span className={styles.rankBadge}>#{rec.rank}</span>
        <h4 className={styles.cardTitle}>{rec.title}</h4>
        <span className={styles.category}>
          {CATEGORY_LABELS[rec.category] ?? rec.category}
        </span>
      </div>
      <p className={styles.choices}>
        Currently: <strong>{rec.current_choice}</strong> &rarr; Recommended:{" "}
        <strong>{rec.recommended_choice}</strong>
      </p>
      <p className={styles.deltaW}>{formatDeltaW(rec.delta_w_gap)}</p>
      <p className={styles.explanation}>{rec.explanation}</p>
    </article>
  );
}

type AnalysisPanelProps = {
  analysis: AnalysisResponse | null;
  error: string | null;
  onDismiss: () => void;
};

/**
 * Collapsible AI Coach results panel. Renders the recommendation cards
 * for a completed analysis, or an inline error/timeout message. Renders
 * nothing when there is neither.
 */
export default function AnalysisPanel({
  analysis,
  error,
  onDismiss,
}: AnalysisPanelProps) {
  if (!analysis && !error) return null;

  return (
    <section className={styles.panel} data-testid="analysis-panel">
      <div className={styles.headerRow}>
        <h3 className={styles.title}>
          AI Coach{analysis ? `: ${analysis.champion_name}` : ""}
        </h3>
        {analysis?.rank_tier ? (
          <span className={styles.tierBadge}>{analysis.rank_tier}</span>
        ) : null}
        <button
          className={styles.dismiss}
          onClick={onDismiss}
          aria-label="Dismiss analysis"
        >
          &times;
        </button>
      </div>

      {!analysis ? (
        <p className={styles.error} data-testid="analysis-error">
          {error}
        </p>
      ) : (
        <>
          {analysis.overall_assessment ? (
            <p className={styles.assessment}>{analysis.overall_assessment}</p>
          ) : null}
          {analysis.recommendations.length > 0 ? (
            <div className={styles.cards}>
              {analysis.recommendations.map((rec) => (
                <RecommendationCard key={rec.rank} rec={rec} />
              ))}
            </div>
          ) : (
            <p className={styles.empty}>
              No structured recommendations were produced for this analysis.
            </p>
          )}
          {analysis.selection_bias_summary ? (
            <details className={styles.bias}>
              <summary className={styles.biasSummary}>
                Selection bias notes
              </summary>
              <p className={styles.biasBody}>
                {analysis.selection_bias_summary}
              </p>
            </details>
          ) : null}
          <p className={styles.footnote}>
            Based on {analysis.match_count} scored{" "}
            {analysis.match_count === 1 ? "match" : "matches"}
            {analysis.model_name ? ` · ${analysis.model_name}` : ""}
          </p>
        </>
      )}
    </section>
  );
}
