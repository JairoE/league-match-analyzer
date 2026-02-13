from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.models.user_riot_account import UserRiotAccount

logger = get_logger("league_api.models.user")
logger.debug("user_model_loaded")


class User(SQLModel, table=True):
    """App user identity record. Riot data lives in riot_account."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True, index=True)
    email: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))

    riot_account_links: list["UserRiotAccount"] = Relationship(
        sa_relationship=relationship(
            "UserRiotAccount",
            back_populates="user",
        )
    )
