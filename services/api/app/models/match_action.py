"""SQLModel for discrete match actions linked to pre/post game states.

Stores item purchases and objective kills with references to the minute-level
state vectors used for ΔW computation.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, Column, Float, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class MatchActionRecord(SQLModel, table=True):
    """Action event with pre/post state references for ΔW pipeline.

    Attributes:
        id: Primary key UUID.
        match_id: FK to the match table.
        game_id: Riot match ID (denormalized).
        action_type: ITEM_PURCHASE or OBJECTIVE_KILL.
        timestamp_ms: When the action occurred (in-game ms).
        participant_id: 1-based participant ID of the acting player.
        team_id: 100 or 200.
        action_detail: Action-specific metadata (item_id, monster_type, etc.).
        pre_state_minute: Minute of the pre-action state vector.
        post_state_minute: Minute of the post-action state vector.
        was_undone: Whether this item purchase was later undone.
        delta_w: Computed ΔW value (null until scored).
        pre_win_prob: Win probability at pre-action state (null until scored).
        post_win_prob: Win probability at post-action state (null until scored).
    """

    __tablename__ = "match_action"

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
    action_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    timestamp_ms: int = Field(sa_column=Column(BigInteger, nullable=False))
    participant_id: int = Field(sa_column=Column(SmallInteger, nullable=False))
    team_id: int = Field(sa_column=Column(SmallInteger, nullable=False))
    action_detail: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
    )
    pre_state_minute: int = Field(sa_column=Column(SmallInteger, nullable=False))
    post_state_minute: int | None = Field(
        default=None,
        sa_column=Column(SmallInteger, nullable=True),
    )
    was_undone: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))

    # Scoring columns — populated by the win probability model
    delta_w: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    pre_win_prob: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    post_win_prob: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
