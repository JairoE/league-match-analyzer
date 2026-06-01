"""Tests for RAG retrieval service (pipeline step 6.5)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.rag_retrieval import (
    build_embedding_text,
    format_few_shot_examples,
    retrieve_few_shot_examples,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_OPPORTUNITIES = [
    {
        "better_alternative": {
            "action_key": "3091",
            "action_name": "Kraken Slayer",
            "effective_delta_w": 0.025,
        },
        "summoner_action": {
            "action_key": "3031",
            "action_name": "Infinity Edge",
            "effective_delta_w": 0.005,
        },
        "delta_w_gap": 0.020,
    }
]

_DEFAULT_BIAS_FLAGS = [
    {
        "action_key": "3031",
        "action_name": "Infinity Edge",
        "mean_pre_win_prob": 0.62,
        "effective_delta_w": 0.003,
    }
]


def _make_comparison_dict(
    *,
    opportunities: list | None = None,
    bias_flags: list | None = None,
) -> dict:
    return {
        "top_improvement_opportunities": (
            _DEFAULT_OPPORTUNITIES if opportunities is None else opportunities
        ),
        "top_selection_bias_flags": (
            _DEFAULT_BIAS_FLAGS if bias_flags is None else bias_flags
        ),
        "groups": [],
    }


def _make_analysis(
    *,
    champion_name: str = "Yasuo",
    rank_tier: str = "GOLD",
    recommendations: list | None = None,
    output_payload: dict | None = None,
) -> object:
    return SimpleNamespace(
        champion_name=champion_name,
        rank_tier=rank_tier,
        recommendations=recommendations or [
            {
                "rank": 1,
                "title": "Switch to Kraken Slayer",
                "current_choice": "Infinity Edge",
                "recommended_choice": "Kraken Slayer",
                "delta_w_gap": 0.02,
                "explanation": "Better true damage.",
                "category": "item_purchase",
            }
        ],
        output_payload=output_payload or {"overall_assessment": "Focus on itemization."},
        embedding=[0.1] * 1536,
    )


# ---------------------------------------------------------------------------
# build_embedding_text
# ---------------------------------------------------------------------------


class TestBuildEmbeddingText:
    def test_includes_champion_and_rank(self) -> None:
        comp = _make_comparison_dict()
        text = build_embedding_text("Yasuo", "GOLD", comp)
        assert "Yasuo" in text
        assert "GOLD" in text

    def test_includes_gap_action_name(self) -> None:
        comp = _make_comparison_dict()
        text = build_embedding_text("Yasuo", "GOLD", comp)
        assert "Kraken Slayer" in text

    def test_includes_delta_w_gap(self) -> None:
        comp = _make_comparison_dict()
        text = build_embedding_text("Yasuo", "GOLD", comp)
        assert "gap=" in text
        assert "+0.0200" in text

    def test_includes_bias_flag_name(self) -> None:
        comp = _make_comparison_dict()
        text = build_embedding_text("Yasuo", "GOLD", comp)
        assert "bias" in text
        assert "Infinity Edge" in text

    def test_unknown_rank_when_none(self) -> None:
        comp = _make_comparison_dict()
        text = build_embedding_text("Yasuo", None, comp)
        assert "UNKNOWN" in text

    def test_pipe_separated_sections(self) -> None:
        comp = _make_comparison_dict()
        text = build_embedding_text("Yasuo", "GOLD", comp)
        parts = text.split(" | ")
        assert len(parts) >= 2

    def test_no_opportunities(self) -> None:
        comp = _make_comparison_dict(opportunities=[], bias_flags=[])
        text = build_embedding_text("Yasuo", "GOLD", comp)
        # Should still produce a valid (minimal) text
        assert "Yasuo GOLD" in text
        assert "gaps" not in text
        assert "bias" not in text

    def test_missing_action_name_falls_back_to_key(self) -> None:
        comp = _make_comparison_dict(
            opportunities=[
                {
                    "better_alternative": {"action_key": "3091"},
                    "summoner_action": {"action_key": "3031"},
                    "delta_w_gap": 0.01,
                }
            ]
        )
        text = build_embedding_text("Yasuo", "GOLD", comp)
        assert "3091" in text

    def test_caps_at_three_opportunities(self) -> None:
        opp = {
            "better_alternative": {"action_key": "1", "action_name": "Item"},
            "summoner_action": {"action_key": "2"},
            "delta_w_gap": 0.01,
        }
        comp = _make_comparison_dict(opportunities=[opp] * 5, bias_flags=[])
        text = build_embedding_text("Yasuo", "GOLD", comp)
        # "Item" should appear at most 3 times in the gaps section
        assert text.count("Item") <= 3


# ---------------------------------------------------------------------------
# retrieve_few_shot_examples
# ---------------------------------------------------------------------------


class TestRetrieveFewShotExamples:
    async def test_returns_ordered_results(self) -> None:
        """Retrieval should return examples ordered by cosine similarity."""
        ex1 = _make_analysis(champion_name="Yasuo", rank_tier="GOLD")
        ex2 = _make_analysis(champion_name="Yasuo", rank_tier="SILVER")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [ex1, ex2]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        query_embedding = [0.1] * 1536
        results = await retrieve_few_shot_examples(
            mock_session, "Yasuo", query_embedding, limit=3
        )

        assert len(results) == 2
        assert results[0].champion_name == "Yasuo"
        assert results[0].rank_tier == "GOLD"

    async def test_returns_empty_on_db_error(self) -> None:
        """Retrieval should return [] rather than raising on DB errors."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))

        results = await retrieve_few_shot_examples(
            mock_session, "Yasuo", [0.1] * 1536
        )
        assert results == []

    async def test_returns_empty_when_no_rows(self) -> None:
        """Empty result set (cold start) should return empty list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        results = await retrieve_few_shot_examples(
            mock_session, "Yasuo", [0.1] * 1536
        )
        assert results == []


# ---------------------------------------------------------------------------
# format_few_shot_examples
# ---------------------------------------------------------------------------


class TestFormatFewShotExamples:
    def test_serializes_champion_and_rank(self) -> None:
        ex = _make_analysis(champion_name="Yasuo", rank_tier="GOLD")
        result = format_few_shot_examples([ex])
        assert len(result) == 1
        assert result[0]["champion_name"] == "Yasuo"
        assert result[0]["rank_tier"] == "GOLD"

    def test_includes_recommendations(self) -> None:
        ex = _make_analysis()
        result = format_few_shot_examples([ex])
        assert result[0]["recommendations"][0]["title"] == "Switch to Kraken Slayer"

    def test_includes_overall_assessment(self) -> None:
        ex = _make_analysis(output_payload={"overall_assessment": "Itemize better."})
        result = format_few_shot_examples([ex])
        assert result[0]["overall_assessment"] == "Itemize better."

    def test_null_rank_tier_becomes_unknown(self) -> None:
        ex = SimpleNamespace(
            champion_name="Yasuo",
            rank_tier=None,
            recommendations=[],
            output_payload={},
            embedding=[0.1] * 1536,
        )
        result = format_few_shot_examples([ex])
        assert result[0]["rank_tier"] == "UNKNOWN"

    def test_empty_list_returns_empty(self) -> None:
        assert format_few_shot_examples([]) == []
