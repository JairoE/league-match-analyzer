"""SQLModel for persisted LLM analysis outputs.

Stores the LLM's recommendations alongside the input context,
schema version, and request metadata for auditability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel


class LLMAnalysis(SQLModel, table=True):
    """Persisted LLM analysis output with metadata.

    Attributes:
        id: Primary key UUID.
        riot_account_id: FK to the riot account being analyzed.
        champion_name: Champion the analysis is for.
        rank_tier: Rank tier at time of analysis (e.g., "GOLD").
        match_ids: List of Riot match IDs included in the analysis.
        schema_version: Version of the input schema sent to the LLM.
        input_payload: The structured gap analysis sent to the LLM.
        output_payload: The raw LLM response.
        recommendations: Parsed list of recommendations from the LLM.
        model_name: LLM model used (e.g., "claude-sonnet-4-20250514").
        token_count_input: Input token count.
        token_count_output: Output token count.
        created_at: When this analysis was generated.
    """

    __tablename__ = "llm_analysis"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    riot_account_id: UUID = Field(
        sa_column=Column(
            "riot_account_id",
            ForeignKey("riot_account.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    champion_name: str = Field(sa_column=Column(String, nullable=False, index=True))
    rank_tier: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    match_ids: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False),
    )
    schema_version: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    input_payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    output_payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    recommendations: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
    )
    model_name: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    token_count_input: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    token_count_output: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
