from __future__ import annotations

from uuid import UUID

from sqlmodel import Field, SQLModel


class UserCreate(SQLModel):
    """Payload for creating a user profile."""

    summoner_name: str = Field(
        alias="summonerName",
        description="Summoner name provided by the user during onboarding.",
    )
    riot_id: str = Field(
        description="Riot ID in the format gameName#tagLine for lookups.",
    )
    puuid: str = Field(
        description="Riot PUUID used as the internal identity for the user.",
    )
    profile_icon_id: int | None = Field(
        default=None,
        alias="profileIconId",
        description="Optional profile icon identifier from Riot.",
    )
    summoner_level: int | None = Field(
        default=None,
        alias="summonerLevel",
        description="Optional summoner level snapshot for the user.",
    )
    email: str | None = Field(
        default=None,
        description="Optional email address for account recovery.",
    )

    model_config = {"populate_by_name": True}


class UserResponse(SQLModel):
    """Response model for user profile data."""

    id: UUID = Field(description="Unique identifier for the user record.")
    summoner_name: str = Field(
        alias="summonerName",
        description="Summoner name for display.",
    )
    riot_id: str = Field(description="Riot ID in gameName#tagLine format.")
    puuid: str = Field(description="Persistent Riot PUUID for the user.")
    profile_icon_id: int | None = Field(
        default=None,
        alias="profileIconId",
        description="Profile icon identifier if known.",
    )
    summoner_level: int | None = Field(
        default=None,
        alias="summonerLevel",
        description="Latest summoner level value if known.",
    )
    email: str | None = Field(
        default=None,
        description="Email address attached to the account, if any.",
    )

    model_config = {"from_attributes": True, "populate_by_name": True}
