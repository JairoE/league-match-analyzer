from __future__ import annotations

from uuid import UUID

from sqlmodel import Field, SQLModel


class ChampionResponse(SQLModel):
    """Response model for champion metadata."""

    id: UUID = Field(description="Unique identifier for the champion record.")
    champ_id: int = Field(description="Riot champion numeric identifier.")
    name: str = Field(description="Champion name used for display.")
    nickname: str = Field(description="Champion title or nickname.")
    image_url: str = Field(description="Image URL for champion assets.")

    model_config = {"from_attributes": True}
