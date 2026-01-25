from __future__ import annotations

from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from app.core.logging import get_logger

logger = get_logger("league_api.models.user_match")
logger.debug("user_match_model_loaded")


class UserMatch(SQLModel, table=True):
    """Join table for associating users with matches."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, nullable=False)
    match_id: UUID = Field(foreign_key="match.id", index=True, nullable=False)

    # Link model only; relationships defined on User/Match via link_model.
