"""Tests for action extraction from timeline data."""

from __future__ import annotations

from app.services.action_extraction import LEGENDARY_ITEM_IDS, ActionType, extract_actions
from app.services.state_vector import GameStateVector


def _make_timeline(frames: list[dict]) -> dict:
    return {"info": {"frames": frames}}


def _make_frame(events: list[dict] | None = None) -> dict:
    frame: dict = {"timestamp": 0}
    if events is not None:
        frame["events"] = events
    return frame


def _make_state_vectors(count: int) -> list[GameStateVector]:
    return [
        GameStateVector(timestamp_ms=i * 60_000, minute=i)
        for i in range(count)
    ]


# Pick a known legendary item for tests
_TEST_ITEM = next(iter(LEGENDARY_ITEM_IDS))


class TestItemPurchaseExtraction:
    def test_extracts_legendary_item_purchase(self) -> None:
        frames = [
            _make_frame(events=[{
                "type": "ITEM_PURCHASED",
                "timestamp": 600_000,  # minute 10
                "participantId": 1,
                "itemId": _TEST_ITEM,
            }]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 1
        a = actions[0]
        assert a.action_type == ActionType.ITEM_PURCHASE
        assert a.participant_id == 1
        assert a.team_id == 100
        assert a.action_detail["item_id"] == _TEST_ITEM
        assert a.pre_state_minute == 10
        print(
            f"[test_legendary_purchase] item={_TEST_ITEM} pid={a.participant_id} "
            f"team={a.team_id} pre_min={a.pre_state_minute} type={a.action_type.value}"
        )

    def test_ignores_non_legendary_items(self) -> None:
        frames = [
            _make_frame(events=[{
                "type": "ITEM_PURCHASED",
                "timestamp": 60_000,
                "participantId": 1,
                "itemId": 1001,  # boots component, not legendary
            }]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(10)

        actions = extract_actions(timeline, vectors)
        assert len(actions) == 0
        print("[test_ignores_non_legendary] item=1001 (non-legendary) -> 0 actions")

    def test_item_sold_sets_post_state(self) -> None:
        frames = [
            _make_frame(events=[
                {
                    "type": "ITEM_PURCHASED",
                    "timestamp": 600_000,  # minute 10
                    "participantId": 1,
                    "itemId": _TEST_ITEM,
                },
                {
                    "type": "ITEM_SOLD",
                    "timestamp": 1200_000,  # minute 20
                    "participantId": 1,
                    "itemId": _TEST_ITEM,
                },
            ]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 1
        assert actions[0].post_state_minute == 20
        print(
            f"[test_item_sold] item={_TEST_ITEM} purchased@min10, sold@min20 -> "
            f"pre_min={actions[0].pre_state_minute} post_min={actions[0].post_state_minute}"
        )

    def test_item_undo_flags_action(self) -> None:
        frames = [
            _make_frame(events=[
                {
                    "type": "ITEM_PURCHASED",
                    "timestamp": 600_000,
                    "participantId": 1,
                    "itemId": _TEST_ITEM,
                },
                {
                    "type": "ITEM_UNDO",
                    "timestamp": 605_000,
                    "participantId": 1,
                    "beforeId": _TEST_ITEM,
                    "afterId": 0,
                },
            ]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 1
        assert actions[0].was_undone is True
        print(
            f"[test_item_undo] item={_TEST_ITEM} purchased then undone -> "
            f"was_undone={actions[0].was_undone}"
        )

    def test_team_200_for_high_participant_ids(self) -> None:
        frames = [
            _make_frame(events=[{
                "type": "ITEM_PURCHASED",
                "timestamp": 600_000,
                "participantId": 8,
                "itemId": _TEST_ITEM,
            }]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 1
        assert actions[0].team_id == 200
        print(f"[test_team_200] pid=8 -> team_id={actions[0].team_id}")


class TestObjectiveKillExtraction:
    def test_extracts_dragon_kill(self) -> None:
        frames = [
            _make_frame(events=[{
                "type": "ELITE_MONSTER_KILL",
                "timestamp": 900_000,  # minute 15
                "killerId": 3,
                "killerTeamId": 100,
                "monsterType": "DRAGON",
                "monsterSubType": "FIRE_DRAGON",
            }]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 1
        a = actions[0]
        assert a.action_type == ActionType.OBJECTIVE_KILL
        assert a.participant_id == 3
        assert a.team_id == 100
        assert a.action_detail["monster_type"] == "DRAGON"
        assert a.pre_state_minute == 15
        assert a.post_state_minute == 19  # 15 + 4 buff window
        print(
            f"[test_dragon_kill] DRAGON(FIRE) by pid={a.participant_id} team={a.team_id} "
            f"pre_min={a.pre_state_minute} post_min={a.post_state_minute} (buff window=4)"
        )

    def test_extracts_baron_kill(self) -> None:
        frames = [
            _make_frame(events=[{
                "type": "ELITE_MONSTER_KILL",
                "timestamp": 1500_000,
                "killerId": 7,
                "killerTeamId": 200,
                "monsterType": "BARON_NASHOR",
            }]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 1
        assert actions[0].action_detail["monster_type"] == "BARON_NASHOR"
        print(
            f"[test_baron_kill] BARON by pid={actions[0].participant_id} "
            f"team={actions[0].team_id}"
        )

    def test_ignores_voidgrubs(self) -> None:
        """HORDE (voidgrubs) are tracked in state vectors, not as ΔW actions."""
        frames = [
            _make_frame(events=[{
                "type": "ELITE_MONSTER_KILL",
                "timestamp": 300_000,
                "killerId": 2,
                "killerTeamId": 100,
                "monsterType": "HORDE",
            }]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(10)

        actions = extract_actions(timeline, vectors)
        assert len(actions) == 0
        print("[test_ignores_voidgrubs] HORDE event -> 0 actions (tracked in state vectors only)")

    def test_post_state_clamped_to_max_minute(self) -> None:
        """Post-state should not exceed available state vector range."""
        frames = [
            _make_frame(events=[{
                "type": "ELITE_MONSTER_KILL",
                "timestamp": 1680_000,  # minute 28
                "killerId": 1,
                "killerTeamId": 100,
                "monsterType": "BARON_NASHOR",
            }]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)  # max minute = 29

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 1
        # 28 + 4 = 32, but clamped to 29
        assert actions[0].post_state_minute == 29
        print(
            f"[test_post_state_clamped] BARON at min28, 28+4=32 but max=29 -> "
            f"post_min={actions[0].post_state_minute}"
        )


class TestExtractActionsCombined:
    def test_empty_timeline(self) -> None:
        actions = extract_actions({"info": {"frames": []}}, [])
        assert actions == []
        print("[test_empty_timeline] 0 frames -> 0 actions")

    def test_actions_sorted_by_timestamp(self) -> None:
        frames = [
            _make_frame(events=[
                {
                    "type": "ELITE_MONSTER_KILL",
                    "timestamp": 900_000,
                    "killerId": 1,
                    "killerTeamId": 100,
                    "monsterType": "DRAGON",
                },
                {
                    "type": "ITEM_PURCHASED",
                    "timestamp": 600_000,
                    "participantId": 1,
                    "itemId": _TEST_ITEM,
                },
            ]),
        ]
        timeline = _make_timeline(frames)
        vectors = _make_state_vectors(30)

        actions = extract_actions(timeline, vectors)

        assert len(actions) == 2
        assert actions[0].timestamp_ms < actions[1].timestamp_ms
        print(
            f"[test_sorted] 2 actions: "
            f"{actions[0].action_type.value}@{actions[0].timestamp_ms}ms, "
            f"{actions[1].action_type.value}@{actions[1].timestamp_ms}ms (sorted)"
        )
