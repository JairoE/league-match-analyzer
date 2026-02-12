"""Model registry loader for SQLModel relationship resolution."""

from app.core.logging import get_logger
from app.models import champion, match, riot_account, riot_account_match, user, user_riot_account

logger = get_logger("league_api.models.registry")


def load_model_registry() -> None:
    """Import all models so SQLAlchemy can resolve relationships.

    Returns:
        None.
    """
    logger.debug(
        "model_registry_loaded",
        extra={
            "models": [
                champion.Champion.__name__,
                match.Match.__name__,
                riot_account.RiotAccount.__name__,
                riot_account_match.RiotAccountMatch.__name__,
                user.User.__name__,
                user_riot_account.UserRiotAccount.__name__,
            ]
        },
    )
