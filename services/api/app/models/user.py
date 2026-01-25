from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, String
from sqlmodel import Field, Relationship, SQLModel

from app.core.logging import get_logger
from app.models.user_match import UserMatch

if TYPE_CHECKING:
    from app.models.match import Match

logger = get_logger("league_api.models.user")
logger.debug("user_model_loaded")


class User(SQLModel, table=True):
    """User identity record for a summoner profile."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True, index=True)
    summoner_name: str = Field(sa_column=Column(String, nullable=False))
    riot_id: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    puuid: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    profile_icon_id: int | None = Field(default=None)
    summoner_level: int | None = Field(default=None)
    email: str | None = Field(default=None)

    matches: list["Match"] = Relationship(back_populates="users", link_model=UserMatch)
    user_matches: list[UserMatch] = Relationship(back_populates="user")
