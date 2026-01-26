from __future__ import annotations

from sqlmodel import Field, SQLModel


class ChampionPublic(SQLModel):
    """Public response model for champion metadata."""

    champ_id: int = Field(description="Riot champion numeric identifier.")
    name: str = Field(description="Champion name used for display.")
    nickname: str = Field(description="Champion title or nickname.")
    image_url: str = Field(description="Image URL for champion assets.")

    model_config = {"from_attributes": True}


class ChampionResponse(ChampionPublic):
    """Response model including internal champion identifiers."""

    id: str | None = Field(
        default=None,
        description="Internal identifier for the champion record.",
    )
