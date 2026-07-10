"""Tests for the AI Coach analysis router.

Covers: enqueue happy path with deterministic day-bucketed job id,
24h cache short-circuit, 404s, duplicate-enqueue tolerance, GET result
shaping (including parse_error rows), and GET null when no row exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routers import analysis
from app.models.llm_analysis import LLMAnalysis
from app.schemas.analysis import AnalysisEnqueueRequest

# ── Helpers ───────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def scalars(self) -> _FakeResult:
        return self

    def first(self) -> object | None:
        return self._row


class _FakeSession:
    """Session whose execute() always resolves to a canned row (or None)."""

    def __init__(self, row: object | None = None) -> None:
        self.row = row

    async def execute(self, statement: object) -> _FakeResult:
        return _FakeResult(self.row)


class _FakePool:
    def __init__(self, enqueue_result: object = "job") -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.enqueue_result = enqueue_result

    async def enqueue_job(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return self.enqueue_result


def _account() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


def _champion(name: str = "Jhin") -> SimpleNamespace:
    return SimpleNamespace(champ_id=202, name=name)


def _analysis_row(**overrides: object) -> LLMAnalysis:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "riot_account_id": uuid4(),
        "champion_name": "Jhin",
        "rank_tier": "SILVER",
        "match_ids": ["NA1_1", "NA1_2"],
        "input_payload": {},
        "output_payload": {
            "overall_assessment": "Solid fundamentals.",
            "selection_bias_summary": "Buys crit when ahead.",
        },
        "recommendations": [
            {
                "rank": 1,
                "title": "Buy Collector earlier",
                "current_choice": "Infinity Edge",
                "recommended_choice": "The Collector",
                "delta_w_gap": 0.04,
                "explanation": "Higher ΔW in your bracket.",
                "category": "item_purchase",
            }
        ],
        "model_name": "gpt-4o-mini",
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return LLMAnalysis(**defaults)  # type: ignore[arg-type]


def _patch_lookups(
    monkeypatch: pytest.MonkeyPatch,
    account: SimpleNamespace | None,
    champion: SimpleNamespace | None,
    pool: _FakePool | None = None,
) -> None:
    async def _resolve(session: object, identifier: str) -> SimpleNamespace | None:
        return account

    async def _get_champion(session: object, champ_id: int) -> SimpleNamespace | None:
        return champion

    async def _get_pool() -> _FakePool:
        assert pool is not None
        return pool

    monkeypatch.setattr(analysis, "resolve_riot_account_identifier", _resolve)
    monkeypatch.setattr(analysis, "get_champion_by_id", _get_champion)
    if pool is not None:
        monkeypatch.setattr(analysis, "get_arq_pool", _get_pool)


# ── POST /riot-accounts/{id}/analysis ────────────────────────────────


async def test_enqueue_analysis_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account()
    pool = _FakePool()
    _patch_lookups(monkeypatch, account, _champion(), pool)

    response = await analysis.enqueue_analysis(
        riot_account_id=str(account.id),
        payload=AnalysisEnqueueRequest(champion_id=202, rank_tier="SILVER"),
        session=_FakeSession(row=None),  # type: ignore[arg-type]
    )

    assert response.status == "enqueued"
    assert response.analysis_id is None
    assert response.champion_name == "Jhin"
    assert len(pool.calls) == 1
    args, kwargs = pool.calls[0]
    assert args == ("llm_analysis_job", str(account.id), "202", "SILVER")
    assert kwargs["_job_id"] == f"llm-{account.id}-202-{date.today().isoformat()}"


async def test_enqueue_analysis_cache_hit_skips_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = _account()
    row = _analysis_row(riot_account_id=account.id)
    pool = _FakePool()
    _patch_lookups(monkeypatch, account, _champion(), pool)

    response = await analysis.enqueue_analysis(
        riot_account_id=str(account.id),
        payload=AnalysisEnqueueRequest(champion_id=202),
        session=_FakeSession(row=row),  # type: ignore[arg-type]
    )

    assert response.status == "already_exists"
    assert response.analysis_id == row.id
    assert pool.calls == []


async def test_enqueue_analysis_unknown_account_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lookups(monkeypatch, None, _champion())

    with pytest.raises(HTTPException) as exc_info:
        await analysis.enqueue_analysis(
            riot_account_id="missing#NA1",
            payload=AnalysisEnqueueRequest(champion_id=202),
            session=_FakeSession(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Riot account not found"


async def test_enqueue_analysis_unknown_champion_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lookups(monkeypatch, _account(), None)

    with pytest.raises(HTTPException) as exc_info:
        await analysis.enqueue_analysis(
            riot_account_id="name#NA1",
            payload=AnalysisEnqueueRequest(champion_id=99999),
            session=_FakeSession(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Champion not found"


async def test_enqueue_analysis_duplicate_job_still_enqueued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARQ returns None for an already-enqueued job id — client still sees enqueued."""
    account = _account()
    pool = _FakePool(enqueue_result=None)
    _patch_lookups(monkeypatch, account, _champion(), pool)

    response = await analysis.enqueue_analysis(
        riot_account_id=str(account.id),
        payload=AnalysisEnqueueRequest(champion_id=202),
        session=_FakeSession(row=None),  # type: ignore[arg-type]
    )

    assert response.status == "enqueued"
    assert len(pool.calls) == 1


# ── GET /riot-accounts/{id}/analysis ─────────────────────────────────


async def test_get_analysis_returns_shaped_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = _account()
    row = _analysis_row(riot_account_id=account.id)
    _patch_lookups(monkeypatch, account, _champion())

    response = await analysis.get_analysis(
        riot_account_id=str(account.id),
        champion_name="Jhin",
        session=_FakeSession(row=row),  # type: ignore[arg-type]
    )

    assert response is not None
    assert response.champion_name == "Jhin"
    assert response.match_count == 2
    assert len(response.recommendations) == 1
    assert response.recommendations[0].title == "Buy Collector earlier"
    assert response.overall_assessment == "Solid fundamentals."
    assert response.selection_bias_summary == "Buys crit when ahead."


async def test_get_analysis_none_when_no_row(monkeypatch: pytest.MonkeyPatch) -> None:
    account = _account()
    _patch_lookups(monkeypatch, account, _champion())

    response = await analysis.get_analysis(
        riot_account_id=str(account.id),
        champion_name="Jhin",
        session=_FakeSession(row=None),  # type: ignore[arg-type]
    )

    assert response is None


async def test_get_analysis_unknown_account_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lookups(monkeypatch, None, None)

    with pytest.raises(HTTPException) as exc_info:
        await analysis.get_analysis(
            riot_account_id="missing#NA1",
            champion_name="Jhin",
            session=_FakeSession(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404


# ── build_analysis_response defensiveness ────────────────────────────


def test_build_analysis_response_parse_error_row() -> None:
    """parse_error rows store {"raw": ...} and no recommendations."""
    row = _analysis_row(
        output_payload={"raw": "not json"},
        recommendations=[],
    )

    response = analysis.build_analysis_response(row)

    assert response.recommendations == []
    assert response.overall_assessment is None
    assert response.selection_bias_summary is None


def test_build_analysis_response_skips_invalid_recommendation() -> None:
    valid = {
        "rank": 2,
        "title": "Prioritize dragons",
        "current_choice": "Solo pushing",
        "recommended_choice": "Rotate to dragon",
        "delta_w_gap": 0.03,
        "explanation": "Objectives swing ΔW.",
        "category": "objective_kill",
    }
    row = _analysis_row(recommendations=[{"rank": "not-an-int-x"}, valid])

    response = analysis.build_analysis_response(row)

    assert len(response.recommendations) == 1
    assert response.recommendations[0].rank == 2
