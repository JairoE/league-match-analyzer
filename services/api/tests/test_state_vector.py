"""Tests for game state vector extraction from timeline data."""

from __future__ import annotations

from app.services.state_vector import (
    GameStateVector,
    extract_state_vectors,
    get_nearest_state_vector,
)


def _make_timeline(frames: list[dict], participants: list[dict] | None = None) -> dict:
    """Build a minimal timeline payload for testing."""
    info: dict = {"frames": frames}
    if participants:
        info["participants"] = participants
    return {"info": info}


def _make_frame(
    timestamp_ms: int,
    participant_frames: dict | None = None,
    events: list[dict] | None = None,
) -> dict:
    frame: dict = {"timestamp": timestamp_ms}
    if participant_frames is not None:
        frame["participantFrames"] = participant_frames
    if events is not None:
        frame["events"] = events
    return frame


def _make_participant_frame(
    pid: int,
    level: int = 1,
    total_gold: int = 0,
    position_x: int = 0,
    position_y: int = 0,
    damage_dealt: int = 0,
    damage_taken: int = 0,
) -> tuple[str, dict]:
    return str(pid), {
        "participantId": pid,
        "level": level,
        "totalGold": total_gold,
        "position": {"x": position_x, "y": position_y},
        "damageStats": {
            "totalDamageDoneToChampions": damage_dealt,
            "totalDamageTaken": damage_taken,
        },
    }


class TestExtractStateVectors:
    def test_empty_timeline_returns_empty(self) -> None:
        result = extract_state_vectors({"info": {"frames": []}})
        assert result == []
        print("[test_empty_timeline] Input: 0 frames -> Output: 0 vectors")

    def test_missing_info_returns_empty(self) -> None:
        result = extract_state_vectors({})
        assert result == []
        print("[test_missing_info] Input: no 'info' key -> Output: 0 vectors")

    def test_single_frame_extracts_player_features(self) -> None:
        pid_key, pf = _make_participant_frame(
            1, level=6, total_gold=3000, position_x=100, position_y=200,
            damage_dealt=500, damage_taken=300,
        )
        timeline = _make_timeline([
            _make_frame(0, participant_frames={pid_key: pf}),
        ])

        vectors = extract_state_vectors(timeline)

        assert len(vectors) == 1
        v = vectors[0]
        assert v.minute == 0
        assert v.timestamp_ms == 0
        assert len(v.players) == 1

        p = v.players[0]
        assert p.participant_id == 1
        assert p.team_id == 100
        assert p.level == 6
        assert p.total_gold == 3000
        assert p.position_x == 100
        assert p.position_y == 200
        assert p.damage_dealt_to_champions == 500
        assert p.damage_taken == 300
        print(
            f"[test_single_frame] Extracted {len(vectors)} vector, "
            f"{len(v.players)} player: pid={p.participant_id} team={p.team_id} "
            f"level={p.level} gold={p.total_gold} pos=({p.position_x},{p.position_y}) "
            f"dmg_dealt={p.damage_dealt_to_champions} dmg_taken={p.damage_taken}"
        )

    def test_kda_from_champion_kill_events(self) -> None:
        """KDA should be derived from CHAMPION_KILL events, not participantFrames."""
        pid1_key, pf1 = _make_participant_frame(1)
        pid2_key, pf2 = _make_participant_frame(6)  # team 200

        kill_event = {
            "type": "CHAMPION_KILL",
            "timestamp": 30_000,  # minute 0
            "killerId": 1,
            "victimId": 6,
            "assistingParticipantIds": [2, 3],
        }

        timeline = _make_timeline([
            _make_frame(0, {pid1_key: pf1, pid2_key: pf2}, events=[kill_event]),
            _make_frame(60_000, {pid1_key: pf1, pid2_key: pf2}),
        ])

        vectors = extract_state_vectors(timeline)

        # At minute 0, killer (pid 1) has 1 kill
        p1_m0 = next(p for p in vectors[0].players if p.participant_id == 1)
        assert p1_m0.kills == 1
        assert p1_m0.deaths == 0

        # Victim (pid 6) has 1 death at minute 0
        p6_m0 = next(p for p in vectors[0].players if p.participant_id == 6)
        assert p6_m0.deaths == 1
        assert p6_m0.kills == 0

        # KDA is cumulative — minute 1 should still show the same totals
        p1_m1 = next(p for p in vectors[1].players if p.participant_id == 1)
        assert p1_m1.kills == 1
        print(
            f"[test_kda] Kill event at t=30s: "
            f"killer(pid=1) kills={p1_m0.kills} deaths={p1_m0.deaths}, "
            f"victim(pid=6) kills={p6_m0.kills} deaths={p6_m0.deaths} | "
            f"Cumulative check min1: killer kills={p1_m1.kills}"
        )

    def test_objective_tracking(self) -> None:
        """Team objectives should accumulate from ELITE_MONSTER_KILL events."""
        pid1_key, pf1 = _make_participant_frame(1)

        dragon_event = {
            "type": "ELITE_MONSTER_KILL",
            "timestamp": 90_000,  # minute 1
            "killerId": 1,
            "killerTeamId": 100,
            "monsterType": "DRAGON",
            "monsterSubType": "FIRE_DRAGON",
        }

        timeline = _make_timeline([
            _make_frame(0, {pid1_key: pf1}),
            _make_frame(60_000, {pid1_key: pf1}, events=[dragon_event]),
            _make_frame(120_000, {pid1_key: pf1}),
        ])

        vectors = extract_state_vectors(timeline)

        # Minute 0: no objectives yet
        assert vectors[0].teams[100].dragons_killed == 0

        # Minute 1: dragon killed
        assert vectors[1].teams[100].dragons_killed == 1
        assert vectors[1].teams[200].dragons_killed == 0

        # Minute 2: still 1 (cumulative)
        assert vectors[2].teams[100].dragons_killed == 1
        print(
            f"[test_objectives] Dragon event at t=90s: "
            f"min0 t100_dragons={vectors[0].teams[100].dragons_killed}, "
            f"min1 t100_dragons={vectors[1].teams[100].dragons_killed}, "
            f"min2 t100_dragons={vectors[2].teams[100].dragons_killed} (cumulative) | "
            f"t200_dragons={vectors[1].teams[200].dragons_killed} (unaffected)"
        )

    def test_team_assignment_by_participant_id(self) -> None:
        """Participants 1-5 should be team 100, 6-10 should be team 200."""
        frames_data = {}
        for pid in range(1, 11):
            key, pf = _make_participant_frame(pid)
            frames_data[key] = pf

        timeline = _make_timeline([_make_frame(0, frames_data)])
        vectors = extract_state_vectors(timeline)

        for p in vectors[0].players:
            expected_team = 100 if p.participant_id <= 5 else 200
            assert p.team_id == expected_team
        team_map = {p.participant_id: p.team_id for p in vectors[0].players}
        print(f"[test_team_assignment] 10 players -> team map: {team_map}")

    def test_average_rank_propagates(self) -> None:
        pid1_key, pf1 = _make_participant_frame(1)
        timeline = _make_timeline([_make_frame(0, {pid1_key: pf1})])
        vectors = extract_state_vectors(timeline, average_rank="PLATINUM")
        assert vectors[0].average_rank == "PLATINUM"
        print(f"[test_avg_rank] average_rank='PLATINUM' -> extracted: '{vectors[0].average_rank}'")

    def test_feature_dict_keys(self) -> None:
        pid1_key, pf1 = _make_participant_frame(1, level=5, total_gold=2000)
        timeline = _make_timeline([_make_frame(0, {pid1_key: pf1})])
        vectors = extract_state_vectors(timeline, average_rank="GOLD")

        features = vectors[0].to_feature_dict()
        assert features["timestamp_ms"] == 0
        assert features["minute"] == 0
        assert features["average_rank"] == "GOLD"
        assert features["p1_level"] == 5
        assert features["p1_total_gold"] == 2000
        assert "t100_dragons" in features
        assert "t200_barons" in features
        print(
            f"[test_feature_dict] {len(features)} keys | "
            f"timestamp_ms={features['timestamp_ms']} minute={features['minute']} "
            f"avg_rank={features['average_rank']} "
            f"p1_level={features['p1_level']} p1_gold={features['p1_total_gold']}"
        )


class TestGetNearestStateVector:
    def test_returns_none_for_empty(self) -> None:
        assert get_nearest_state_vector([], 60_000) is None
        print("[test_nearest_empty] Empty vectors + ts=60000 -> None")

    def test_returns_correct_minute(self) -> None:
        vectors = [
            GameStateVector(timestamp_ms=0, minute=0),
            GameStateVector(timestamp_ms=60_000, minute=1),
            GameStateVector(timestamp_ms=120_000, minute=2),
        ]
        result = get_nearest_state_vector(vectors, 90_000)
        assert result is not None
        assert result.minute == 1
        print(f"[test_nearest_correct] ts=90000 across [0,1,2] -> minute={result.minute}")

    def test_clamps_to_max_minute(self) -> None:
        vectors = [
            GameStateVector(timestamp_ms=0, minute=0),
            GameStateVector(timestamp_ms=60_000, minute=1),
        ]
        result = get_nearest_state_vector(vectors, 500_000)
        assert result is not None
        assert result.minute == 1
        print(f"[test_nearest_clamp_max] ts=500000 across [0,1] -> minute={result.minute}")

    def test_clamps_to_zero(self) -> None:
        vectors = [GameStateVector(timestamp_ms=0, minute=0)]
        result = get_nearest_state_vector(vectors, -10_000)
        assert result is not None
        assert result.minute == 0
        print(f"[test_nearest_clamp_zero] ts=-10000 across [0] -> minute={result.minute}")
