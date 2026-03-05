"""Game state vector extraction from Riot timeline data.

Extracts per-minute state vectors from participantFrames and events,
following the xPetu thesis framework (Table 5: 75.9% accuracy, 0.90% ECE).

Feature groups:
  - Per-player (x10): position, level, gold, damage dealt/taken, KDA
  - Per-team (x2): voidgrubs, dragons, barons, turrets, inhibitors
  - Global: timestamp, average rank
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import get_logger

logger = get_logger("league_api.services.state_vector")


@dataclass
class PlayerState:
    """Per-player features at a given minute."""

    participant_id: int
    team_id: int
    position_x: int = 0
    position_y: int = 0
    level: int = 1
    total_gold: int = 0
    damage_dealt_to_champions: int = 0
    damage_taken: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0


@dataclass
class TeamState:
    """Per-team objective features at a given minute."""

    team_id: int
    voidgrubs_killed: int = 0
    dragons_killed: int = 0
    barons_killed: int = 0
    turrets_destroyed: int = 0
    inhibitors_destroyed: int = 0


@dataclass
class GameStateVector:
    """Full game state at a specific minute.

    Contains per-player features for all 10 players, per-team objectives
    for both teams, and global features (timestamp, rank).
    """

    timestamp_ms: int
    minute: int
    players: list[PlayerState] = field(default_factory=list)
    teams: dict[int, TeamState] = field(default_factory=dict)
    average_rank: str | None = None

    def to_feature_dict(self) -> dict:
        """Flatten state vector into a dict suitable for model input.

        Returns:
            Dict with named features keyed by player/team/global prefix.
        """
        features: dict = {
            "timestamp_ms": self.timestamp_ms,
            "minute": self.minute,
        }
        if self.average_rank:
            features["average_rank"] = self.average_rank

        for p in self.players:
            prefix = f"p{p.participant_id}"
            features[f"{prefix}_position_x"] = p.position_x
            features[f"{prefix}_position_y"] = p.position_y
            features[f"{prefix}_level"] = p.level
            features[f"{prefix}_total_gold"] = p.total_gold
            features[f"{prefix}_damage_dealt"] = p.damage_dealt_to_champions
            features[f"{prefix}_damage_taken"] = p.damage_taken
            features[f"{prefix}_kills"] = p.kills
            features[f"{prefix}_deaths"] = p.deaths
            features[f"{prefix}_assists"] = p.assists

        for team_id, t in self.teams.items():
            prefix = f"t{team_id}"
            features[f"{prefix}_voidgrubs"] = t.voidgrubs_killed
            features[f"{prefix}_dragons"] = t.dragons_killed
            features[f"{prefix}_barons"] = t.barons_killed
            features[f"{prefix}_turrets"] = t.turrets_destroyed
            features[f"{prefix}_inhibitors"] = t.inhibitors_destroyed

        return features


def _build_kda_tracker(
    events: list[dict],
    total_minutes: int,
) -> dict[int, dict[int, dict[str, int]]]:
    """Build cumulative KDA per player per minute from CHAMPION_KILL events.

    Args:
        events: Flat list of all timeline events across all frames.
        total_minutes: Total number of minute frames to cover.

    Returns:
        Nested dict: minute -> participant_id -> {"kills", "deaths", "assists"}.
        Values are cumulative up to and including that minute.
    """
    # Accumulate raw event counts per minute
    raw: dict[int, list[dict]] = {}
    for event in events:
        if event.get("type") != "CHAMPION_KILL":
            continue
        minute = event.get("timestamp", 0) // 60_000
        raw.setdefault(minute, []).append(event)

    # Build cumulative tracker
    cumulative: dict[int, dict[str, int]] = {}  # participant_id -> running totals
    result: dict[int, dict[int, dict[str, int]]] = {}

    for minute in range(total_minutes):
        for event in raw.get(minute, []):
            killer_id = event.get("killerId", 0)
            victim_id = event.get("victimId", 0)
            assisting = event.get("assistingParticipantIds", [])

            if killer_id > 0:
                cumulative.setdefault(killer_id, {"kills": 0, "deaths": 0, "assists": 0})
                cumulative[killer_id]["kills"] += 1
            if victim_id > 0:
                cumulative.setdefault(victim_id, {"kills": 0, "deaths": 0, "assists": 0})
                cumulative[victim_id]["deaths"] += 1
            for aid in assisting:
                if aid > 0:
                    cumulative.setdefault(aid, {"kills": 0, "deaths": 0, "assists": 0})
                    cumulative[aid]["assists"] += 1

        # Snapshot cumulative state at this minute
        result[minute] = {
            pid: dict(stats) for pid, stats in cumulative.items()
        }

    return result


def _build_objective_tracker(
    events: list[dict],
    total_minutes: int,
) -> dict[int, dict[int, TeamState]]:
    """Build cumulative team objective counts per minute.

    Args:
        events: Flat list of all timeline events across all frames.
        total_minutes: Total number of minute frames to cover.

    Returns:
        Nested dict: minute -> team_id -> TeamState (cumulative).
    """
    team_totals: dict[int, TeamState] = {
        100: TeamState(team_id=100),
        200: TeamState(team_id=200),
    }
    result: dict[int, dict[int, TeamState]] = {}

    objective_events: dict[int, list[dict]] = {}
    for event in events:
        etype = event.get("type", "")
        if etype not in ("ELITE_MONSTER_KILL", "BUILDING_KILL"):
            continue
        minute = event.get("timestamp", 0) // 60_000
        objective_events.setdefault(minute, []).append(event)

    for minute in range(total_minutes):
        for event in objective_events.get(minute, []):
            etype = event.get("type", "")
            # Determine team from killerTeamId or killerId
            team_id = event.get("killerTeamId", 0)
            if team_id not in (100, 200):
                killer_id = event.get("killerId", 0)
                team_id = 100 if 1 <= killer_id <= 5 else 200

            if team_id not in team_totals:
                continue

            ts = team_totals[team_id]

            if etype == "ELITE_MONSTER_KILL":
                monster = event.get("monsterType", "")
                if monster == "DRAGON":
                    ts.dragons_killed += 1
                elif monster == "BARON_NASHOR":
                    ts.barons_killed += 1
                elif monster == "RIFTHERALD":
                    pass  # Herald tracked separately if needed
                elif monster == "HORDE":
                    ts.voidgrubs_killed += 1

            elif etype == "BUILDING_KILL":
                building = event.get("buildingType", "")
                if building == "TOWER_BUILDING":
                    ts.turrets_destroyed += 1
                elif building == "INHIBITOR_BUILDING":
                    ts.inhibitors_destroyed += 1

        # Snapshot: deep-copy current state for this minute
        result[minute] = {
            tid: TeamState(
                team_id=tid,
                voidgrubs_killed=ts.voidgrubs_killed,
                dragons_killed=ts.dragons_killed,
                barons_killed=ts.barons_killed,
                turrets_destroyed=ts.turrets_destroyed,
                inhibitors_destroyed=ts.inhibitors_destroyed,
            )
            for tid, ts in team_totals.items()
        }

    return result


def _collect_all_events(frames: list[dict]) -> list[dict]:
    """Flatten all events from timeline frames into a single list.

    Args:
        frames: Timeline frames from Riot API.

    Returns:
        Flat list of event dicts.
    """
    all_events: list[dict] = []
    for frame in frames:
        all_events.extend(frame.get("events", []))
    return all_events


def extract_state_vectors(
    timeline: dict,
    average_rank: str | None = None,
) -> list[GameStateVector]:
    """Extract per-minute game state vectors from a Riot timeline payload.

    Uses nearest-frame snapping (1-min resolution). No sub-minute interpolation
    per the thesis: momentum effects are negligible (Markov assumption holds).

    Args:
        timeline: Raw Riot timeline payload (from fetch_match_timeline).
        average_rank: Average rank tier of players (e.g., "GOLD", "PLATINUM").

    Returns:
        List of GameStateVector, one per minute frame.
    """
    info = timeline.get("info") or {}
    frames: list[dict] = info.get("frames") or []
    if not frames:
        logger.warning("extract_state_vectors_no_frames")
        return []

    all_events = _collect_all_events(frames)
    total_minutes = len(frames)
    kda_tracker = _build_kda_tracker(all_events, total_minutes)
    objective_tracker = _build_objective_tracker(all_events, total_minutes)

    # Map participantId -> teamId from timeline metadata
    participant_team_map: dict[int, int] = {}
    for p in info.get("participants") or []:
        pid = p.get("participantId", 0)
        # Timeline participants don't always have teamId; infer from ID
        # Participants 1-5 are team 100, 6-10 are team 200
        participant_team_map[pid] = 100 if pid <= 5 else 200

    vectors: list[GameStateVector] = []

    for minute, frame in enumerate(frames):
        timestamp_ms = frame.get("timestamp", minute * 60_000)
        participant_frames = frame.get("participantFrames") or {}

        players: list[PlayerState] = []
        for pid_str, pf in participant_frames.items():
            pid = int(pid_str)
            team_id = participant_team_map.get(pid, 100 if pid <= 5 else 200)

            # KDA from cumulative event tracker
            kda = kda_tracker.get(minute, {}).get(pid, {})

            position = pf.get("position") or {}
            damage_stats = pf.get("damageStats") or {}

            players.append(PlayerState(
                participant_id=pid,
                team_id=team_id,
                position_x=position.get("x", 0),
                position_y=position.get("y", 0),
                level=pf.get("level", 1),
                total_gold=pf.get("totalGold", 0),
                damage_dealt_to_champions=damage_stats.get(
                    "totalDamageDoneToChampions", 0
                ),
                damage_taken=damage_stats.get("totalDamageTaken", 0),
                kills=kda.get("kills", 0),
                deaths=kda.get("deaths", 0),
                assists=kda.get("assists", 0),
            ))

        # Sort by participant_id for deterministic ordering
        players.sort(key=lambda p: p.participant_id)

        # Team objectives at this minute
        teams = objective_tracker.get(minute, {
            100: TeamState(team_id=100),
            200: TeamState(team_id=200),
        })

        vectors.append(GameStateVector(
            timestamp_ms=timestamp_ms,
            minute=minute,
            players=players,
            teams=teams,
            average_rank=average_rank,
        ))

    logger.info(
        "extract_state_vectors_done",
        extra={"frame_count": len(vectors)},
    )
    return vectors


def get_nearest_state_vector(
    vectors: list[GameStateVector],
    timestamp_ms: int,
) -> GameStateVector | None:
    """Find the state vector nearest to a given timestamp.

    Uses nearest-frame snapping as specified in the pipeline doc.

    Args:
        vectors: List of per-minute state vectors.
        timestamp_ms: Target timestamp in milliseconds.

    Returns:
        Nearest GameStateVector, or None if vectors is empty.
    """
    if not vectors:
        return None

    target_minute = timestamp_ms // 60_000
    # Clamp to valid range
    target_minute = max(0, min(target_minute, len(vectors) - 1))
    return vectors[target_minute]
