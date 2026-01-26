from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger("league_api.services.riot_id_parser")


@dataclass(frozen=True)
class ParsedRiotId:
    """Normalized Riot ID components.

    Attributes:
        game_name: Normalized game name for the Riot ID.
        tag_line: Normalized tag line for the Riot ID.
    """

    game_name: str
    tag_line: str

    @property
    def canonical(self) -> str:
        """Return the canonical Riot ID string.

        Returns:
            Canonical Riot ID in the format gameName#tagLine.
        """

        return f"{self.game_name}#{self.tag_line}"


def parse_riot_id(raw: str) -> ParsedRiotId:
    """Parse a Riot ID into canonical pieces.

    Args:
        raw: User-provided Riot ID or summoner name.

    Returns:
        ParsedRiotId with normalized game name and tag line.

    Raises:
        ValueError: Raised when the Riot ID cannot be normalized.
    """

    value = str(raw or "").strip()
    game_name, tag_line = value.split("#", 1) if "#" in value else (value, "")
    game_name = game_name.strip()
    tag_line = tag_line.strip() or "NA1"

    logger.info(
        "parse_riot_id",
        extra={"raw": raw, "game_name": game_name, "tag_line": tag_line},
    )

    if not game_name or not tag_line:
        logger.info("parse_riot_id_invalid", extra={"raw": raw})
        raise ValueError("invalid_riot_id")

    return ParsedRiotId(game_name=game_name, tag_line=tag_line)
