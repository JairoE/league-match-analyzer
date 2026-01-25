from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

from app.core.logging import get_logger
from app.models.user_match import UserMatch

if TYPE_CHECKING:
    from app.models.user import User

logger = get_logger("league_api.models.match")
logger.debug("match_model_loaded")


class Match(SQLModel, table=True):
    """Match record storing Riot payloads and identifiers."""

    id: UUID | None = Field(default_factory=uuid4, primary_key=True, index=True)
    game_id: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    game_info: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))

    users: list["User"] = Relationship(back_populates="matches", link_model=UserMatch)
    user_matches: list[UserMatch] = Relationship(back_populates="match")

    def to_embedding_text(self) -> str:
        """Serialize match details into a natural language summary.

        Returns:
            Natural language description for embedding generation.
        """
        info = self.game_info or {}
        metadata = info.get("metadata") or {}
        match_label = metadata.get("matchId") or self.game_id or "unknown"
        game_mode = info.get("info", {}).get("gameMode") if info else None
        duration = info.get("info", {}).get("gameDuration") if info else None
        logger.info(
            "match_embedding_text_generated",
            extra={"match_id": self.id, "game_id": self.game_id, "mode": game_mode},
        )
        parts = [f"Match {match_label}"]
        if game_mode:
            parts.append(f"Mode {game_mode}")
        if duration:
            parts.append(f"Duration {duration} seconds")
        return ", ".join(parts)
