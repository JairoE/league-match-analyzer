from __future__ import annotations

from uuid import UUID

from sqlmodel import Field, SQLModel


class UserCreate(SQLModel):
    """Payload for creating a user profile."""

    email: str = Field(description="Email address for the user account.")
    summoner_name: str = Field(
        alias="summonerName",
        description="Summoner name or Riot ID in gameName#tagLine format.",
    )

    model_config = {"populate_by_name": True}


class RiotAccountResponse(SQLModel):
    """Response model for riot account data."""

    id: UUID = Field(description="Unique identifier for the riot account record.")
    summoner_name: str | None = Field(
        default=None,
        alias="summonerName",
        description="Summoner name for display.",
    )
    riot_id: str = Field(description="Riot ID in gameName#tagLine format.")
    puuid: str = Field(description="Persistent Riot PUUID for the account.")
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

    model_config = {"from_attributes": True, "populate_by_name": True}


class AuthResponse(SQLModel):
    """Response model for sign-up/sign-in flows.

    Returns both the app user and the linked riot account.
    """

    id: UUID = Field(description="Unique identifier for the user record.")
    email: str = Field(description="Email address for the user.")
    riot_account: RiotAccountResponse = Field(
        description="Linked riot account data.",
    )

    model_config = {"populate_by_name": True}
