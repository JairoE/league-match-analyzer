"""Integration tests using a real Riot timeline fixture.

Validates that extraction logic handles actual Riot API payload shapes,
catching field renames, missing keys, and structural changes that
synthetic tests cannot detect.

Fixture: tests/fixtures/timeline_sample.json (~830KB, 41 frames, 10 players)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.action_extraction import ActionType, extract_actions
from app.services.state_vector import extract_state_vectors

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "timeline_sample.json"


@pytest.fixture(scope="module")
def timeline() -> dict:
    """Load the real timeline fixture once per module."""
    if not FIXTURE_PATH.exists():
        pytest.skip("Timeline fixture not found — run fixture fetch script first")
    with open(FIXTURE_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def state_vectors(timeline: dict) -> list:
    """Extract state vectors from the real timeline."""
    return extract_state_vectors(timeline, average_rank="GOLD")


@pytest.fixture(scope="module")
def actions(timeline: dict, state_vectors: list) -> list:
    """Extract actions from the real timeline."""
    return extract_actions(timeline, state_vectors)


class TestRealTimelineStateVectors:
    """Validate state vector extraction against real Riot data."""

    def test_produces_vectors_for_every_frame(
        self, timeline: dict, state_vectors: list
    ) -> None:
        frame_count = len(timeline["info"]["frames"])
        assert len(state_vectors) == frame_count
        assert frame_count > 0

    def test_every_frame_has_10_players(self, state_vectors: list) -> None:
        for sv in state_vectors:
            assert len(sv.players) == 10, (
                f"Minute {sv.minute}: expected 10 players, got {len(sv.players)}"
            )

    def test_player_ids_are_1_through_10(self, state_vectors: list) -> None:
        for sv in state_vectors:
            pids = sorted(p.participant_id for p in sv.players)
            assert pids == list(range(1, 11)), (
                f"Minute {sv.minute}: unexpected participant IDs {pids}"
            )

    def test_team_assignment_consistent(self, state_vectors: list) -> None:
        for sv in state_vectors:
            for p in sv.players:
                expected = 100 if p.participant_id <= 5 else 200
                assert p.team_id == expected

    def test_both_teams_present_in_objectives(self, state_vectors: list) -> None:
        for sv in state_vectors:
            assert 100 in sv.teams
            assert 200 in sv.teams

    def test_gold_increases_over_time(self, state_vectors: list) -> None:
        """Total gold across all players should generally increase."""
        if len(state_vectors) < 5:
            pytest.skip("Too few frames to test gold progression")
        early_gold = sum(p.total_gold for p in state_vectors[2].players)
        late_gold = sum(p.total_gold for p in state_vectors[-2].players)
        assert late_gold > early_gold, (
            f"Expected late gold ({late_gold}) > early gold ({early_gold})"
        )

    def test_levels_increase_over_time(self, state_vectors: list) -> None:
        """Average level should increase from start to end."""
        if len(state_vectors) < 10:
            pytest.skip("Too few frames to test level progression")
        early_avg = sum(p.level for p in state_vectors[1].players) / 10
        late_avg = sum(p.level for p in state_vectors[-2].players) / 10
        assert late_avg > early_avg

    def test_kda_totals_are_consistent(self, state_vectors: list) -> None:
        """Total kills across all players should equal total deaths."""
        final = state_vectors[-1]
        total_kills = sum(p.kills for p in final.players)
        total_deaths = sum(p.deaths for p in final.players)
        # Kills should equal deaths (every kill has a corresponding death)
        # Executions (turret/minion kills) increment deaths but not kills,
        # so deaths >= kills
        assert total_deaths >= total_kills
        # But they should be close — most deaths are from champion kills
        assert total_kills > 0, "Expected at least some kills in a real game"

    def test_kda_is_cumulative(self, state_vectors: list) -> None:
        """KDA should never decrease between minutes."""
        for i in range(1, len(state_vectors)):
            for p_prev, p_curr in zip(
                sorted(state_vectors[i - 1].players, key=lambda p: p.participant_id),
                sorted(state_vectors[i].players, key=lambda p: p.participant_id),
            ):
                assert p_curr.kills >= p_prev.kills, (
                    f"Kills decreased for p{p_curr.participant_id} "
                    f"at minute {state_vectors[i].minute}"
                )
                assert p_curr.deaths >= p_prev.deaths, (
                    f"Deaths decreased for p{p_curr.participant_id} "
                    f"at minute {state_vectors[i].minute}"
                )

    def test_objectives_are_cumulative(self, state_vectors: list) -> None:
        """Objective counts should never decrease between minutes."""
        for i in range(1, len(state_vectors)):
            for team_id in (100, 200):
                prev = state_vectors[i - 1].teams[team_id]
                curr = state_vectors[i].teams[team_id]
                assert curr.dragons_killed >= prev.dragons_killed
                assert curr.barons_killed >= prev.barons_killed
                assert curr.turrets_destroyed >= prev.turrets_destroyed

    def test_feature_dict_has_expected_keys(self, state_vectors: list) -> None:
        """Feature dict should have all expected key prefixes."""
        features = state_vectors[5].to_feature_dict()

        # Global
        assert "timestamp_ms" in features
        assert "minute" in features
        assert "average_rank" in features

        # All 10 players
        for pid in range(1, 11):
            prefix = f"p{pid}"
            assert f"{prefix}_level" in features
            assert f"{prefix}_total_gold" in features
            assert f"{prefix}_kills" in features
            assert f"{prefix}_position_x" in features

        # Both teams
        for tid in (100, 200):
            prefix = f"t{tid}"
            assert f"{prefix}_dragons" in features
            assert f"{prefix}_barons" in features
            assert f"{prefix}_turrets" in features

    def test_timestamps_are_monotonically_increasing(
        self, state_vectors: list
    ) -> None:
        for i in range(1, len(state_vectors)):
            assert state_vectors[i].timestamp_ms >= state_vectors[i - 1].timestamp_ms


class TestRealTimelineActions:
    """Validate action extraction against real Riot data."""

    def test_extracts_some_item_purchases(self, actions: list) -> None:
        item_actions = [a for a in actions if a.action_type == ActionType.ITEM_PURCHASE]
        # A real 40-min game should have many legendary purchases
        assert len(item_actions) > 0, "Expected at least one legendary item purchase"

    def test_extracts_some_objectives(self, actions: list) -> None:
        obj_actions = [a for a in actions if a.action_type == ActionType.OBJECTIVE_KILL]
        # A real 40-min game should have dragons/barons
        assert len(obj_actions) > 0, "Expected at least one objective kill"

    def test_all_actions_have_valid_participant_ids(self, actions: list) -> None:
        for a in actions:
            assert 1 <= a.participant_id <= 10, (
                f"Invalid participant_id {a.participant_id} for {a.action_type}"
            )

    def test_all_actions_have_valid_team_ids(self, actions: list) -> None:
        for a in actions:
            assert a.team_id in (100, 200)

    def test_pre_state_minute_within_bounds(
        self, actions: list, state_vectors: list
    ) -> None:
        max_minute = len(state_vectors) - 1
        for a in actions:
            assert 0 <= a.pre_state_minute <= max_minute, (
                f"pre_state_minute {a.pre_state_minute} out of bounds "
                f"(max {max_minute}) for {a.action_type}"
            )

    def test_post_state_minute_within_bounds(
        self, actions: list, state_vectors: list
    ) -> None:
        max_minute = len(state_vectors) - 1
        for a in actions:
            if a.post_state_minute is not None:
                assert 0 <= a.post_state_minute <= max_minute, (
                    f"post_state_minute {a.post_state_minute} out of bounds "
                    f"(max {max_minute}) for {a.action_type}"
                )

    def test_actions_sorted_by_timestamp(self, actions: list) -> None:
        timestamps = [a.timestamp_ms for a in actions]
        assert timestamps == sorted(timestamps)

    def test_item_purchases_have_item_id(self, actions: list) -> None:
        for a in actions:
            if a.action_type == ActionType.ITEM_PURCHASE:
                assert "item_id" in a.action_detail
                assert isinstance(a.action_detail["item_id"], int)

    def test_objective_kills_have_monster_type(self, actions: list) -> None:
        for a in actions:
            if a.action_type == ActionType.OBJECTIVE_KILL:
                assert "monster_type" in a.action_detail
                assert a.action_detail["monster_type"] in (
                    "DRAGON", "BARON_NASHOR", "RIFTHERALD",
                )

    def test_both_teams_have_actions(self, actions: list) -> None:
        """Both teams should have performed actions in a real game."""
        teams_with_actions = {a.team_id for a in actions}
        assert 100 in teams_with_actions, "Team 100 had no actions"
        assert 200 in teams_with_actions, "Team 200 had no actions"

    def test_print_extraction_summary(
        self, actions: list, state_vectors: list
    ) -> None:
        """Not a real assertion — prints a summary for manual review."""
        item_actions = [a for a in actions if a.action_type == ActionType.ITEM_PURCHASE]
        obj_actions = [a for a in actions if a.action_type == ActionType.OBJECTIVE_KILL]
        undone = [a for a in item_actions if a.was_undone]

        print("\n--- Real Timeline Extraction Summary ---")
        print(f"State vectors: {len(state_vectors)} minutes")
        print(f"Total actions: {len(actions)}")
        print(f"  Item purchases: {len(item_actions)} ({len(undone)} undone)")
        print(f"  Objective kills: {len(obj_actions)}")

        # Objective breakdown
        obj_types: dict[str, int] = {}
        for a in obj_actions:
            mt = a.action_detail["monster_type"]
            obj_types[mt] = obj_types.get(mt, 0) + 1
        for mt, count in sorted(obj_types.items()):
            print(f"    {mt}: {count}")

        # Final game state
        final = state_vectors[-1]
        t100 = final.teams[100]
        t200 = final.teams[200]
        print("\nFinal objectives:")
        print(
            f"  Team 100: {t100.dragons_killed}D "
            f"{t100.barons_killed}B {t100.turrets_destroyed}T"
        )
        print(
            f"  Team 200: {t200.dragons_killed}D "
            f"{t200.barons_killed}B {t200.turrets_destroyed}T"
        )

        total_kills = sum(p.kills for p in final.players)
        total_deaths = sum(p.deaths for p in final.players)
        print(f"  Total kills: {total_kills}, deaths: {total_deaths}")
