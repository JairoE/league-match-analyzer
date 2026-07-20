export type Recommendation = {
  rank: number;
  title: string;
  current_choice: string;
  recommended_choice: string;
  delta_w_gap: number;
  explanation: string;
  category: string;
};

export type AnalysisResponse = {
  id: string;
  riot_account_id: string;
  champion_name: string;
  rank_tier: string | null;
  match_count: number;
  recommendations: Recommendation[];
  overall_assessment: string | null;
  selection_bias_summary: string | null;
  model_name: string | null;
  created_at: string;
};

export type AnalysisEnqueueResponse = {
  status: "enqueued" | "already_exists";
  analysis_id: string | null;
  champion_name: string;
};

export type AnalysisChampion = {
  champion_id: number;
  champion_name: string;
  scored_match_count: number;
  scored_action_count: number;
  corpus_example_count: number;
};
