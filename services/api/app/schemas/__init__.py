"""Pydantic schema package for API payloads."""

from app.schemas.auth import UserFetchRequest, UserSignInRequest, UserSignUpRequest
from app.schemas.champion import ChampionPublic, ChampionResponse
from app.schemas.match import MatchListItem, MatchResponse
from app.schemas.reset import ResetResult
from app.schemas.user import AuthResponse, RiotAccountResponse, UserCreate

__all__ = [
    "AuthResponse",
    "ChampionPublic",
    "ChampionResponse",
    "MatchListItem",
    "MatchResponse",
    "ResetResult",
    "RiotAccountResponse",
    "UserCreate",
    "UserFetchRequest",
    "UserSignInRequest",
    "UserSignUpRequest",
]
