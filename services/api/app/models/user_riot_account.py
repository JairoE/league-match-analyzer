from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.models.riot_account import RiotAccount
    from app.models.user import User

logger = get_logger("league_api.models.user_riot_account")
logger.debug("user_riot_account_model_loaded")


class UserRiotAccount(SQLModel, table=True):
    """Join table granting a user access to a riot account's data."""

    __tablename__ = "user_riot_account"
    __table_args__ = (
        UniqueConstraint("user_id", "riot_account_id", name="uq_user_riot_account"),
    )

    id: UUID | None = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, nullable=False)
    riot_account_id: UUID = Field(foreign_key="riot_account.id", index=True, nullable=False)

    user: "User" = Relationship(
        sa_relationship=relationship(
            "User",
            back_populates="riot_account_links",
        )
    )

    riot_account: "RiotAccount" = Relationship(
        sa_relationship=relationship(
            "RiotAccount",
            back_populates="user_links",
        )
    )
