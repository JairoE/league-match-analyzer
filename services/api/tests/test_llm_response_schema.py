"""Tests for LLM response schema validation."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.services.llm_response_schema import LLMAnalysisResponse, Recommendation


def _valid_recommendation(*, rank: int = 1, **overrides: object) -> dict:
    """Build a valid recommendation dict with sensible defaults."""
    base = {
        "rank": rank,
        "title": "Switch from Infinity Edge to Kraken Slayer",
        "current_choice": "Infinity Edge",
        "recommended_choice": "Kraken Slayer",
        "delta_w_gap": 0.0168,
        "explanation": "Kraken Slayer provides a higher win probability increase.",
        "category": "item_purchase",
    }
    base.update(overrides)
    return base


def _valid_response(**overrides: object) -> dict:
    """Build a valid LLMAnalysisResponse dict."""
    base = {
        "recommendations": [
            _valid_recommendation(rank=1),
            _valid_recommendation(rank=2, title="Second rec"),
            _valid_recommendation(rank=3, title="Third rec"),
        ],
        "selection_bias_summary": None,
        "overall_assessment": "Focus on itemization improvements.",
    }
    base.update(overrides)
    return base


class TestRecommendation:
    def test_valid_recommendation_parses(self) -> None:
        rec = Recommendation(**_valid_recommendation())
        assert rec.rank == 1
        assert rec.category == "item_purchase"

    def test_invalid_category_rejected(self) -> None:
        with pytest.raises(ValidationError, match="category"):
            Recommendation(**_valid_recommendation(category="invalid_type"))

    def test_rank_below_1_rejected(self) -> None:
        with pytest.raises(ValidationError, match="rank"):
            Recommendation(**_valid_recommendation(rank=0))

    def test_rank_above_5_rejected(self) -> None:
        with pytest.raises(ValidationError, match="rank"):
            Recommendation(**_valid_recommendation(rank=6))

    def test_all_categories_accepted(self) -> None:
        for cat in ("item_purchase", "objective_kill", "selection_bias"):
            rec = Recommendation(**_valid_recommendation(category=cat))
            assert rec.category == cat


class TestLLMAnalysisResponse:
    def test_valid_response_parses(self) -> None:
        resp = LLMAnalysisResponse(**_valid_response())
        assert len(resp.recommendations) == 3
        assert resp.overall_assessment == "Focus on itemization improvements."

    def test_parse_from_json_string(self) -> None:
        raw = json.dumps(_valid_response())
        resp = LLMAnalysisResponse.model_validate_json(raw)
        assert len(resp.recommendations) == 3

    def test_empty_recommendations_accepted(self) -> None:
        resp = LLMAnalysisResponse(**_valid_response(recommendations=[]))
        assert resp.recommendations == []

    def test_too_many_recommendations_rejected(self) -> None:
        recs = [_valid_recommendation(rank=i) for i in range(1, 7)]
        with pytest.raises(ValidationError):
            LLMAnalysisResponse(**_valid_response(recommendations=recs))

    def test_missing_overall_assessment_rejected(self) -> None:
        data = _valid_response()
        del data["overall_assessment"]
        with pytest.raises(ValidationError, match="overall_assessment"):
            LLMAnalysisResponse(**data)

    def test_selection_bias_summary_nullable(self) -> None:
        resp = LLMAnalysisResponse(**_valid_response(selection_bias_summary=None))
        assert resp.selection_bias_summary is None

        resp2 = LLMAnalysisResponse(
            **_valid_response(selection_bias_summary="Player over-buys Heartsteel.")
        )
        assert resp2.selection_bias_summary == "Player over-buys Heartsteel."

    def test_model_dump_roundtrip(self) -> None:
        resp = LLMAnalysisResponse(**_valid_response())
        dumped = resp.model_dump()
        resp2 = LLMAnalysisResponse(**dumped)
        assert resp2 == resp
