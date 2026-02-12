"""SQLModel model package for database entities."""

from app.core.logging import get_logger
from app.models.champion import Champion
from app.models.match import Match
from app.models.riot_account import RiotAccount
from app.models.riot_account_match import RiotAccountMatch
from app.models.user import User
from app.models.user_riot_account import UserRiotAccount

logger = get_logger("league_api.models")
logger.debug("models_loaded")

__all__ = [
    "Champion",
    "Match",
    "RiotAccount",
    "RiotAccountMatch",
    "User",
    "UserRiotAccount",
]
