from sqlmodel import Field, SQLModel


class UserAuthRequest(SQLModel):
    """Base payload for user identity lookups.

    Attributes:
        summoner_name: Riot identifier provided by the user.
        email: Optional email address attached to the account.
    """

    summoner_name: str = Field(
        alias="summonerName",
        description="Summoner name or Riot ID in the format gameName#tagLine.",
    )
    email: str | None = Field(
        default=None,
        description="Optional email address supplied by the client.",
    )

    model_config = {"populate_by_name": True}


class UserSignUpRequest(UserAuthRequest):
    """Payload for user sign-up requests."""


class UserSignInRequest(UserAuthRequest):
    """Payload for user sign-in requests."""


class UserFetchRequest(SQLModel):
    """Payload for fetching or locating a user."""

    summoner_name: str = Field(
        alias="summonerName",
        description="Summoner name or Riot ID in the format gameName#tagLine.",
    )

    model_config = {"populate_by_name": True}
