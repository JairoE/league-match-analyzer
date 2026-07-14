import type {AnalysisResponse} from "../../src/lib/types/analysis";

export const ANALYSIS_RESPONSE: AnalysisResponse = {
  id: "analysis-id-1",
  riot_account_id: "summoner-id-123",
  champion_name: "Yasuo",
  rank_tier: "GOLD",
  match_count: 12,
  recommendations: [
    {
      rank: 1,
      title: "Buy Immortal Shieldbow earlier",
      current_choice: "Berserker's Greaves rush",
      recommended_choice: "Immortal Shieldbow by 14:00",
      delta_w_gap: 0.052,
      explanation:
        "Your win probability jumps when Shieldbow completes before " +
        "the second dragon fight.",
      category: "item_purchase",
    },
    {
      rank: 2,
      title: "Contest more dragons",
      current_choice: "Side-lane pushing at dragon spawns",
      recommended_choice: "Rotate to dragon 30s before spawn",
      delta_w_gap: 0.038,
      explanation:
        "Players at your rank convert dragon control into a measurable " +
        "win-probability edge.",
      category: "objective_kill",
    },
    {
      rank: 3,
      title: "Vary your third item",
      current_choice: "Infinity Edge every game",
      recommended_choice: "Situational defensive third item",
      delta_w_gap: 0.021,
      explanation:
        "You pick Infinity Edge even when behind, where a defensive item " +
        "has a higher expected ΔW.",
      category: "selection_bias",
    },
  ],
  overall_assessment:
    "Strong laning fundamentals; the biggest gains are in objective timing " +
    "and adaptive itemization.",
  selection_bias_summary:
    "You favor full-damage builds regardless of game state, which wins " +
    "harder when ahead but costs win probability from behind.",
  model_name: "gpt-4o-mini",
  created_at: "2026-07-10T12:00:00Z",
};
