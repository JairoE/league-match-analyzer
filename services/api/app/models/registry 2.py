"""Model registry loader for SQLModel relationship resolution."""

from app.core.logging import get_logger
from app.models import champion, match, user, user_match

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
                user.User.__name__,
                user_match.UserMatch.__name__,
            ]
        },
    )
