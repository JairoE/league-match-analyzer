from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import Field, SQLModel


class MatchResponse(SQLModel):
    """Response model for a full match payload."""

    id: UUID = Field(description="Unique identifier for the match record.")
    game_id: str = Field(description="Riot game ID tied to the match.")
    game_info: dict[str, Any] | None = Field(
        default=None,
        description="Raw Riot match payload used for deeper analysis.",
    )

    model_config = {"from_attributes": True}


class MatchListItem(SQLModel):
    """Response model for match list items."""

    id: UUID = Field(description="Unique identifier for the match record.")
    game_id: str = Field(description="Riot game ID used for detail lookups.")
    game_info: dict[str, Any] | None = Field(
        default=None,
        description="Optional cached payload used for list summaries.",
    )

    model_config = {"from_attributes": True}
