"""Pydantic schemas for the AI Coach analysis endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AnalysisEnqueueRequest(BaseModel):
    """Request body for enqueueing an LLM analysis job.

    Attributes:
        champion_id: Numeric Riot champion identifier.
        rank_tier: Optional rank tier hint (e.g., "GOLD").
    """

    champion_id: int
    rank_tier: str | None = Field(default=None, max_length=32)


class AnalysisEnqueueResponse(BaseModel):
    """Response for the analysis enqueue endpoint.

    Attributes:
        status: Whether a job was enqueued or a recent analysis already exists.
        analysis_id: Existing analysis id when status is "already_exists".
        champion_name: Resolved champion name to use when polling for results.
    """

    status: Literal["enqueued", "already_exists"]
    analysis_id: UUID | None = None
    champion_name: str


class AnalysisChampionResponse(BaseModel):
    """A champion with enough account data to request AI Coach analysis."""

    champion_id: int
    champion_name: str
    scored_match_count: int
    scored_action_count: int
    corpus_example_count: int


class RecommendationResponse(BaseModel):
    """A single recommendation from a persisted analysis.

    Category is a plain string (not a Literal) so older or partially
    parsed rows never fail response validation.
    """

    rank: int
    title: str
    current_choice: str
    recommended_choice: str
    delta_w_gap: float
    explanation: str
    category: str


class AnalysisResponse(BaseModel):
    """A persisted LLM analysis, shaped for the frontend panel."""

    id: UUID
    riot_account_id: UUID
    champion_name: str
    rank_tier: str | None = None
    match_count: int
    recommendations: list[RecommendationResponse] = Field(default_factory=list)
    overall_assessment: str | None = None
    selection_bias_summary: str | None = None
    model_name: str | None = None
    created_at: datetime
