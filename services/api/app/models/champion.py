from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Column, Integer, String
from sqlmodel import Field, SQLModel

from app.core.logging import get_logger

logger = get_logger("league_api.models.champion")
logger.debug("champion_model_loaded")


class Champion(SQLModel, table=True):
    """Champion metadata used for rendering names and images."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True, index=True)
    champ_id: int = Field(sa_column=Column(Integer, unique=True, nullable=False, index=True))
    name: str = Field(sa_column=Column(String, nullable=False))
    nickname: str = Field(sa_column=Column(String, nullable=False))
    image_url: str = Field(sa_column=Column(String, nullable=False))
