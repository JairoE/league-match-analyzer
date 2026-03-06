"""Action extraction from Riot timeline data for ΔW computation.

Extracts discrete actions (item purchases, objective kills) and links them
to pre-action and post-action game state vectors for win probability delta
calculation.

V1 action types:
  - ITEM_PURCHASED: legendary items only (clearest strategic signal)
  - ELITE_MONSTER_KILL: dragon, baron, herald objectives
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.logging import get_logger
from app.services.state_vector import GameStateVector

logger = get_logger("league_api.services.action_extraction")

# Legendary item IDs (Patch 14.x / Season 2026).
# These are completed items with strategic significance — no components or boots.
# Maintained as a set for O(1) lookup; update when new items are added.
LEGENDARY_ITEM_IDS: set[int] = {
    # AD / Crit
    3031,  # Infinity Edge
    3033,  # Mortal Reminder
    3036,  # Lord Dominik's Regards
    3072,  # Bloodthirster
    3094,  # Rapid Firecannon
    3095,  # Stormrazor
    3046,  # Phantom Dancer
    3085,  # Runaan's Hurricane
    3508,  # Essence Reaver
    6672,  # Kraken Slayer
    6673,  # Immortal Shieldbow
    6675,  # Navori Quickblades
    6676,  # The Collector
    6696,  # Axiom Arc
    3161,  # Spear of Shojin
    6609,  # Chempunk Chainsword
    3071,  # Black Cleaver
    3004,  # Manamune
    3042,  # Muramana
    6333,  # Death's Dance
    3156,  # Maw of Malmortius
    3139,  # Mercurial Scimitar
    6035,  # Silvermere Dawn
    6632,  # Divine Sunderer / Iceborn Gauntlet replacement
    3074,  # Ravenous Hydra
    3748,  # Titanic Hydra
    6631,  # Stridebreaker
    3142,  # Youmuu's Ghostblade
    6701,  # Opportunity
    6694,  # Serylda's Grudge
    3179,  # Umbral Glaive
    6695,  # Serpent's Fang
    6692,  # Eclipse
    3026,  # Guardian Angel
    # AP
    3089,  # Rabadon's Deathcap
    3135,  # Void Staff
    3165,  # Morellonomicon
    3152,  # Hextech Rocketbelt
    4628,  # Horizon Focus
    3118,  # Malignance
    3100,  # Lich Bane
    3115,  # Nashor's Tooth
    4629,  # Cosmic Drive
    4645,  # Shadowflame
    3116,  # Rylai's Crystal Scepter
    3907,  # Staff of Flowing Water
    3504,  # Ardent Censer
    3011,  # Chemtech Putrifier / Oblivion Orb upgrade
    6655,  # Luden's Companion
    6653,  # Liandry's Torment
    6657,  # Rod of Ages
    3003,  # Archangel's Staff
    3040,  # Seraph's Embrace
    3802,  # Lost Chapter upgrades
    4633,  # Riftmaker
    3137,  # Cryptbloom
    3145,  # Hextech Alternator upgrades
    # Tank
    3001,  # Evenshroud
    3002,  # Trailblazer
    3005,  # Ghostcrawlers
    3068,  # Sunfire Aegis
    3075,  # Thornmail
    3076,  # Bramble Vest upgrade
    3083,  # Warmog's Armor
    3109,  # Knight's Vow
    3110,  # Frozen Heart
    3143,  # Randuin's Omen
    3190,  # Locket of the Iron Solari
    3193,  # Gargoyle Stoneplate
    3742,  # Dead Man's Plate
    4401,  # Force of Nature
    6665,  # Jak'Sho, The Protean
    3084,  # Heartsteel
    3102,  # Banshee's Veil
    3157,  # Zhonya's Hourglass
    # Support
    3222,  # Mikael's Blessing
    3107,  # Redemption
    2065,  # Shurelya's Battlesong
    3050,  # Zeke's Convergence
    # Jungle
    6698,  # Voltaic Cyclosword
    # Misc
    3814,  # Edge of Night
    3181,  # Hullbreaker
}


class ActionType(StrEnum):
    """Supported action types for ΔW computation."""

    ITEM_PURCHASE = "ITEM_PURCHASE"
    OBJECTIVE_KILL = "OBJECTIVE_KILL"


@dataclass
class MatchAction:
    """A discrete action with linked pre/post game states for ΔW.

    Attributes:
        action_type: Type of action (item purchase or objective kill).
        timestamp_ms: When the action occurred (in-game ms).
        participant_id: Player who performed the action.
        team_id: Team of the acting player.
        action_detail: Action-specific metadata (item_id, monster_type, etc.).
        pre_state_minute: Minute index of the pre-action state vector.
        post_state_minute: Minute index of the post-action state vector.
        was_undone: Whether this item purchase was later undone (ITEMUNDO).
    """

    action_type: ActionType
    timestamp_ms: int
    participant_id: int
    team_id: int
    action_detail: dict = field(default_factory=dict)
    pre_state_minute: int = 0
    post_state_minute: int | None = None
    was_undone: bool = False


# Buff window in minutes for objective kills (effective duration of buffs)
OBJECTIVE_BUFF_WINDOW_MINUTES = 4


def _extract_item_purchases(
    frames: list[dict],
    game_duration_minutes: int,
) -> list[MatchAction]:
    """Extract legendary item purchase actions from timeline frames.

    Focuses on legendary items only (clearest strategic signal per thesis).
    Tracks ITEMUNDO events to flag corrected decisions.

    For each purchase, the post-state is determined by:
    - When the item is sold (ITEM_SOLD)
    - When the item is destroyed (ITEM_DESTROYED)
    - Terminal match state (game end)

    Args:
        frames: Timeline frames from Riot API.
        game_duration_minutes: Total game duration in minutes.

    Returns:
        List of MatchAction for legendary item purchases.
    """
    actions: list[MatchAction] = []
    # Track active items per participant: item_id -> purchase action index
    active_items: dict[int, dict[int, int]] = {}  # participant_id -> {item_id -> action_idx}
    # Track undone items
    undone_items: set[tuple[int, int, int]] = set()  # (participant_id, item_id, minute)

    # First pass: collect ITEMUNDO events
    for frame in frames:
        for event in frame.get("events", []):
            if event.get("type") == "ITEM_UNDO":
                pid = event.get("participantId", 0)
                before_id = event.get("beforeId", 0)
                minute = event.get("timestamp", 0) // 60_000
                undone_items.add((pid, before_id, minute))

    # Second pass: process purchases, sales, and destruction
    for frame in frames:
        for event in frame.get("events", []):
            etype = event.get("type", "")
            pid = event.get("participantId", 0)
            item_id = event.get("itemId", 0)
            ts = event.get("timestamp", 0)
            minute = ts // 60_000

            if etype == "ITEM_PURCHASED" and item_id in LEGENDARY_ITEM_IDS:
                team_id = 100 if 1 <= pid <= 5 else 200
                was_undone = (pid, item_id, minute) in undone_items

                action = MatchAction(
                    action_type=ActionType.ITEM_PURCHASE,
                    timestamp_ms=ts,
                    participant_id=pid,
                    team_id=team_id,
                    action_detail={
                        "item_id": item_id,
                    },
                    pre_state_minute=minute,
                    post_state_minute=game_duration_minutes,  # default to game end
                    was_undone=was_undone,
                )
                actions.append(action)
                action_idx = len(actions) - 1
                active_items.setdefault(pid, {})[item_id] = action_idx

            elif etype in ("ITEM_SOLD", "ITEM_DESTROYED"):
                if item_id in LEGENDARY_ITEM_IDS and pid in active_items:
                    if item_id in active_items[pid]:
                        action_idx = active_items[pid].pop(item_id)
                        actions[action_idx].post_state_minute = minute

    return actions


def _extract_objective_kills(frames: list[dict]) -> list[MatchAction]:
    """Extract elite monster kill actions from timeline frames.

    Covers dragon, baron, and rift herald kills. Post-state is set to
    ~4 minutes after the kill (the objective's effective buff window).

    Args:
        frames: Timeline frames from Riot API.

    Returns:
        List of MatchAction for objective kills.
    """
    actions: list[MatchAction] = []

    for frame in frames:
        for event in frame.get("events", []):
            if event.get("type") != "ELITE_MONSTER_KILL":
                continue

            monster_type = event.get("monsterType", "")
            if monster_type not in ("DRAGON", "BARON_NASHOR", "RIFTHERALD"):
                continue

            ts = event.get("timestamp", 0)
            minute = ts // 60_000
            killer_id = event.get("killerId", 0)
            team_id = event.get("killerTeamId", 0)
            if team_id not in (100, 200):
                team_id = 100 if 1 <= killer_id <= 5 else 200

            actions.append(MatchAction(
                action_type=ActionType.OBJECTIVE_KILL,
                timestamp_ms=ts,
                participant_id=killer_id,
                team_id=team_id,
                action_detail={
                    "monster_type": monster_type,
                    "monster_sub_type": event.get("monsterSubType", ""),
                },
                pre_state_minute=minute,
                post_state_minute=minute + OBJECTIVE_BUFF_WINDOW_MINUTES,
            ))

    return actions


def extract_actions(
    timeline: dict,
    state_vectors: list[GameStateVector],
) -> list[MatchAction]:
    """Extract all V1 actions from a timeline and link to state vectors.

    Combines item purchases and objective kills. Clamps post-state minutes
    to the available state vector range.

    Args:
        timeline: Raw Riot timeline payload.
        state_vectors: Pre-extracted per-minute state vectors for this match.

    Returns:
        List of MatchAction with pre/post state minute indices.
    """
    info = timeline.get("info") or {}
    frames: list[dict] = info.get("frames") or []
    if not frames:
        logger.warning("extract_actions_no_frames")
        return []

    max_minute = len(state_vectors) - 1 if state_vectors else 0
    game_duration_minutes = max_minute

    item_actions = _extract_item_purchases(frames, game_duration_minutes)
    objective_actions = _extract_objective_kills(frames)

    all_actions = item_actions + objective_actions

    # Clamp post-state minutes to valid range
    for action in all_actions:
        if action.post_state_minute is not None:
            action.post_state_minute = min(action.post_state_minute, max_minute)

    # Sort by timestamp
    all_actions.sort(key=lambda a: a.timestamp_ms)

    logger.info(
        "extract_actions_done",
        extra={
            "item_purchases": len(item_actions),
            "objective_kills": len(objective_actions),
            "total": len(all_actions),
        },
    )
    return all_actions
