"""Feature order and encoding for the V1 win probability model.

Must match the CSV produced by scripts/export_training_data.py so that
training and inference use the same feature vector layout.
"""

from __future__ import annotations

PLAYER_FEATURE_KEYS = [
    "position_x",
    "position_y",
    "level",
    "total_gold",
    "damage_dealt",
    "damage_taken",
    "kills",
    "deaths",
    "assists",
]
TEAM_FEATURE_KEYS = [
    "voidgrubs",
    "dragons",
    "barons",
    "turrets",
    "inhibitors",
]
PARTICIPANT_IDS = list(range(1, 11))
TEAM_IDS = [100, 200]

# Ordinal encoding for average_rank (empty/missing -> 0)
RANK_ORDER = [
    "",
    "IRON",
    "BRONZE",
    "SILVER",
    "GOLD",
    "PLATINUM",
    "EMERALD",
    "DIAMOND",
    "MASTER",
    "GRANDMASTER",
    "CHALLENGER",
]


def _build_feature_order() -> list[str]:
    """Build feature column order matching export_training_data CSV (without id/outcome)."""
    order: list[str] = []
    for pid in PARTICIPANT_IDS:
        for key in PLAYER_FEATURE_KEYS:
            order.append(f"p{pid}_{key}")
    for tid in TEAM_IDS:
        for key in TEAM_FEATURE_KEYS:
            order.append(f"t{tid}_{key}")
    order.append("average_rank")
    return order


FEATURE_ORDER: list[str] = _build_feature_order()


def encode_rank(rank: str | None) -> int:
    """Encode average_rank string to ordinal for model input.

    Args:
        rank: Rank tier string (e.g. "GOLD") or empty/None.

    Returns:
        Integer index 0..10; 0 for missing/empty.
    """
    if not rank:
        return 0
    r = (rank or "").strip().upper()
    for i, tier in enumerate(RANK_ORDER):
        if tier == r:
            return i
    return 0
