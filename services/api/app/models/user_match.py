from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.user import User

logger = get_logger("league_api.models.user_match")
logger.debug("user_match_model_loaded")


class UserMatch(SQLModel, table=True):
    """Join table for associating users with matches."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, nullable=False)
    match_id: UUID = Field(foreign_key="match.id", index=True, nullable=False)

    user: "User" = Relationship(back_populates="user_matches")
    match: "Match" = Relationship(back_populates="user_matches")
