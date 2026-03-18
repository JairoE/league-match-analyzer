"""Pydantic models for the expected LLM analysis response.

Defines the JSON schema the LLM must return. Used for both prompt
instruction (schema included in system prompt) and response validation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    """A single actionable recommendation from the LLM.

    Attributes:
        rank: Priority ranking (1 = highest impact).
        title: Short summary of the recommendation.
        current_choice: The action/item the summoner currently uses.
        recommended_choice: The better alternative.
        delta_w_gap: Expected win probability improvement (ΔW gap).
        explanation: Context-specific advice (2-3 sentences).
        category: Type of recommendation.
    """

    rank: int = Field(ge=1, le=5)
    title: str
    current_choice: str
    recommended_choice: str
    delta_w_gap: float
    explanation: str
    category: Literal["item_purchase", "objective_kill", "selection_bias"]


class LLMAnalysisResponse(BaseModel):
    """Full structured response expected from the LLM.

    Attributes:
        recommendations: Up to 3 ranked recommendations by ΔW impact.
        selection_bias_summary: Optional paragraph on win-more patterns.
        overall_assessment: 1-2 sentence summary of the analysis.
    """

    recommendations: list[Recommendation] = Field(max_length=5)
    selection_bias_summary: str | None = None
    overall_assessment: str
