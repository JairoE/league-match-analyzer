from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("league_api.services.riot_match_id")


def normalize_match_id(match_id: str) -> tuple[str, bool]:
    """Ensure match id includes platform prefix.

    Retrieves: Default platform from settings when prefix missing.
    Transforms: Adds platform prefix to match id when absent.
    Why: Prevents incorrect hardcoded platform usage across regions.

    Args:
        match_id: Riot match id with or without platform prefix.

    Returns:
        Tuple of (normalized_match_id, was_normalized).
    """
    if "_" in match_id:
        return match_id, False

    settings = get_settings()
    platform = settings.riot_default_platform.upper()
    normalized = f"{platform}_{match_id}"
    logger.warning(
        "riot_match_id_missing_platform",
        extra={"match_id": match_id, "platform": platform, "normalized": normalized},
    )
    return normalized, True
