from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from app.core.logging import get_logger
from app.models.riot_account_match import RiotAccountMatch

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.user import User
    from app.models.user_riot_account import UserRiotAccount

logger = get_logger("league_api.models.riot_account")
logger.debug("riot_account_model_loaded")


class RiotAccount(SQLModel, table=True):
    """Riot identity record for a summoner profile."""

    __tablename__ = "riot_account"

    id: UUID | None = Field(default_factory=uuid4, primary_key=True, index=True)
    riot_id: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    puuid: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    summoner_name: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    profile_icon_id: int | None = Field(default=None)
    summoner_level: int | None = Field(default=None)

    matches: list["Match"] = Relationship(
        sa_relationship=relationship(
            "Match",
            back_populates="riot_accounts",
            secondary=RiotAccountMatch.__table__,
        )
    )

    user_links: list["UserRiotAccount"] = Relationship(
        sa_relationship=relationship(
            "UserRiotAccount",
            back_populates="riot_account",
        )
    )
