"""SQLModel model package for database entities."""

from app.core.logging import get_logger
from app.models.champion import Champion
from app.models.llm_analysis import LLMAnalysis
from app.models.match import Match
from app.models.match_action import MatchActionRecord
from app.models.match_state_vector import MatchStateVector
from app.models.riot_account import RiotAccount
from app.models.riot_account_match import RiotAccountMatch
from app.models.user import User
from app.models.user_riot_account import UserRiotAccount

logger = get_logger("league_api.models")
logger.debug("models_loaded")

__all__ = [
    "Champion",
    "LLMAnalysis",
    "Match",
    "MatchActionRecord",
    "MatchStateVector",
    "RiotAccount",
    "RiotAccountMatch",
    "User",
    "UserRiotAccount",
]
