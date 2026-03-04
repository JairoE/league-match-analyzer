from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from sqlmodel import Field, SQLModel


class PaginationMeta(SQLModel):
    """Pagination metadata included in paginated responses."""

    page: int = Field(description="Current page number (1-based).")
    limit: int = Field(description="Items per page.")
    total: int = Field(description="Total matching items in the database.")
    last_page: int = Field(description="Last available page number.")

    @classmethod
    def build(cls, *, page: int, limit: int, total: int) -> PaginationMeta:
        return cls(
            page=page,
            limit=limit,
            total=total,
            last_page=max(1, math.ceil(total / limit)),
        )


class MatchResponse(SQLModel):
    """Response model for a full match payload."""

    id: UUID = Field(description="Unique identifier for the match record.")
    game_id: str = Field(description="Riot game ID tied to the match.")
    game_start_timestamp: int | None = Field(
        default=None,
        description="Game start epoch in ms from Riot info.gameStartTimestamp.",
    )
    game_info: dict[str, Any] | None = Field(
        default=None,
        description="Raw Riot match payload used for deeper analysis.",
    )

    model_config = {"from_attributes": True}


class MatchListItem(SQLModel):
    """Response model for match list items."""

    id: UUID = Field(description="Unique identifier for the match record.")
    game_id: str = Field(description="Riot game ID used for detail lookups.")
    game_start_timestamp: int | None = Field(
        default=None,
        description="Game start epoch in ms from Riot info.gameStartTimestamp.",
    )
    game_info: dict[str, Any] | None = Field(
        default=None,
        description="Optional cached payload used for list summaries.",
    )

    model_config = {"from_attributes": True}


class PaginatedMatchList(SQLModel):
    """Paginated response wrapping a list of match items."""

    data: list[MatchListItem] = Field(description="Match items for the current page.")
    meta: PaginationMeta = Field(description="Pagination metadata.")
