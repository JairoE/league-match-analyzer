"""SQLModel for per-minute game state vectors extracted from timelines.

Each row captures the full game state at a specific minute of a match,
flattened into a JSONB column for flexible model input.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Column, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class MatchStateVector(SQLModel, table=True):
    """Per-minute game state snapshot for win probability modeling.

    Attributes:
        id: Primary key UUID.
        match_id: FK to the match table.
        game_id: Riot match ID (denormalized for query convenience).
        minute: In-game minute (0-indexed).
        timestamp_ms: In-game timestamp in milliseconds.
        features: Flattened feature dict from GameStateVector.to_feature_dict().
    """

    __tablename__ = "match_state_vector"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    match_id: UUID = Field(
        sa_column=Column(
            "match_id",
            ForeignKey("match.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    game_id: str = Field(sa_column=Column(String, nullable=False, index=True))
    minute: int = Field(sa_column=Column(SmallInteger, nullable=False))
    timestamp_ms: int = Field(sa_column=Column(BigInteger, nullable=False))
    features: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
