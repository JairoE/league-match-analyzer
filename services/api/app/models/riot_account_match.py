from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.logging import get_logger

logger = get_logger("league_api.models.riot_account_match")
logger.debug("riot_account_match_model_loaded")


class RiotAccountMatch(SQLModel, table=True):
    """Join table for associating riot accounts with matches."""

    __tablename__ = "riot_account_match"
    __table_args__ = (
        UniqueConstraint("riot_account_id", "match_id", name="uq_riot_account_match"),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    riot_account_id: UUID = Field(foreign_key="riot_account.id", index=True, nullable=False)
    match_id: UUID = Field(foreign_key="match.id", index=True, nullable=False)
