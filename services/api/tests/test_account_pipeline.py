"""Tests for the one-command account pipeline (make up / make pipeline).

Covers: preflight config gating, scoring job ids, the drain wait loop's exit
conditions, per-champion analysis caching/enqueue/fallback, and the top-level
orchestration for dry runs and LLM skipping.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from arq.jobs import ResultNotFound

from app.services import account_pipeline
from app.services.account_pipeline import (
    PipelineConfigError,
    PipelineCounts,
    analyze_champion,
    check_preflight,
    enqueue_scoring_jobs,
    run_account_pipeline,
    wait_for_drain,
)
from app.services.analysis_champions import AnalyzableChampion
from app.services.llm_analyses import analysis_job_id

# ── Helpers ───────────────────────────────────────────────────────────


class _FakeJob:
    def __init__(self, result: object = None, exc: BaseException | None = None) -> None:
        self._result = result
        self._exc = exc

    async def result(self, timeout: float | None = None) -> object:
        if self._exc is not None:
            raise self._exc
        return self._result


class _FakePool:
    def __init__(self, job: object = "job") -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.job = job

    async def enqueue_job(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return self.job


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


def _session_factory() -> _FakeSession:
    return _FakeSession()


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "riot_api_key": "RGAPI-test",
        "win_prob_model_path": "data/win_prob_model.joblib",
        "openai_api_key": "sk-test",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _champion(champion_id: int = 12, name: str = "Alistar") -> AnalyzableChampion:
    return AnalyzableChampion(
        champion_id=champion_id,
        champion_name=name,
        scored_match_count=5,
        scored_action_count=20,
        corpus_example_count=3,
    )


def _patch_latest(monkeypatch: pytest.MonkeyPatch, row: object | None) -> None:
    async def _latest(*args: object, **kwargs: object) -> object | None:
        return row

    monkeypatch.setattr(account_pipeline, "latest_analysis", _latest)


# ── Preflight ─────────────────────────────────────────────────────────


def test_preflight_rejects_placeholder_riot_key() -> None:
    with pytest.raises(PipelineConfigError):
        check_preflight(_settings(riot_api_key="replace-me"))  # type: ignore[arg-type]


def test_preflight_warns_on_missing_model_and_openai_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    warnings = check_preflight(
        _settings(win_prob_model_path="", openai_api_key="")  # type: ignore[arg-type]
    )
    assert any("WIN_PROB_MODEL_PATH" in w for w in warnings)
    assert any("OPENAI_API_KEY" in w for w in warnings)
    assert "account_pipeline_preflight_warning" in caplog.text


def test_preflight_clean_when_fully_configured() -> None:
    assert check_preflight(_settings()) == []  # type: ignore[arg-type]


# ── Scoring enqueue ───────────────────────────────────────────────────


async def test_enqueue_scoring_jobs_uses_manual_namespace_and_counts_dedupes() -> None:
    pool = _FakePool(job=None)  # ARQ returns None when the id is already taken
    enqueued = await enqueue_scoring_jobs(pool, ["NA1_1", "NA1_2"])

    assert enqueued == 0
    assert [call[0] for call in pool.calls] == [
        ("score_actions_job", "NA1_1"),
        ("score_actions_job", "NA1_2"),
    ]
    assert [call[1]["_job_id"] for call in pool.calls] == [
        "score-actions:v0:NA1_1",
        "score-actions:v0:NA1_2",
    ]

    pool.job = "job"
    assert await enqueue_scoring_jobs(pool, ["NA1_3"]) == 1


# ── Drain wait loop ───────────────────────────────────────────────────


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def _sequence(values: list[Any]) -> Any:
    iterator = iter(values)
    last: list[Any] = [None]

    async def _next() -> Any:
        try:
            last[0] = next(iterator)
        except StopIteration:
            pass
        return last[0]

    return _next


async def test_wait_for_drain_completes_when_all_matches_scored() -> None:
    clock = _Clock()
    counts, outcome = await wait_for_drain(
        _sequence([PipelineCounts(3, 1, 0, 0), PipelineCounts(3, 3, 3, 3)]),
        _sequence([5, 1]),
        clock=clock,
        sleep=clock.sleep,
    )
    assert outcome == "complete"
    assert counts.scored == 3


async def test_wait_for_drain_settles_when_queue_empties() -> None:
    clock = _Clock()
    # One match never scores (e.g. timeline 404) but the queue drains.
    stuck = PipelineCounts(3, 3, 2, 2)
    _, outcome = await wait_for_drain(
        _sequence([stuck]),
        _sequence([2, 0, 0]),
        clock=clock,
        sleep=clock.sleep,
    )
    assert outcome == "settled"
    assert clock.now < 30


async def test_wait_for_drain_reports_stall_when_queue_stays_busy() -> None:
    clock = _Clock()
    _, outcome = await wait_for_drain(
        _sequence([PipelineCounts(3, 0, 0, 0)]),
        _sequence([4]),
        stall_s=30,
        timeout_s=900,
        clock=clock,
        sleep=clock.sleep,
    )
    assert outcome == "stalled"
    assert 30 <= clock.now < 40


async def test_wait_for_drain_times_out_while_progressing() -> None:
    clock = _Clock()
    progressing = [PipelineCounts(100, i, 0, 0) for i in range(100)]
    _, outcome = await wait_for_drain(
        _sequence(progressing),
        _sequence([7]),
        timeout_s=12,
        stall_s=60,
        clock=clock,
        sleep=clock.sleep,
    )
    assert outcome == "timeout"


# ── Per-champion analysis ─────────────────────────────────────────────


async def test_analyze_champion_skips_recent_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = SimpleNamespace(id=uuid4())
    _patch_latest(monkeypatch, existing)
    pool = _FakePool()

    outcome = await analyze_champion(_session_factory, pool, uuid4(), _champion())

    assert outcome.status == "cached"
    assert outcome.analysis_id == str(existing.id)
    assert pool.calls == []


async def test_analyze_champion_enqueues_with_endpoint_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_latest(monkeypatch, None)
    account_id = uuid4()
    pool = _FakePool(
        job=_FakeJob(
            {"status": "ok", "analysis_id": "abc", "token_input": 900, "token_output": 200}
        )
    )

    outcome = await analyze_champion(_session_factory, pool, account_id, _champion())

    args, kwargs = pool.calls[0]
    assert args == ("llm_analysis_job", str(account_id), "12", None)
    assert kwargs["_job_id"] == analysis_job_id(account_id, 12, date.today())
    assert kwargs["_job_id"] == f"llm-{account_id}-12-{date.today().isoformat()}"
    assert outcome.status == "ok"
    assert (outcome.analysis_id, outcome.token_input, outcome.token_output) == ("abc", 900, 200)


async def test_analyze_champion_reports_job_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_latest(monkeypatch, None)
    pool = _FakePool(job=_FakeJob({"status": "no_data"}))

    outcome = await analyze_champion(_session_factory, pool, uuid4(), _champion())

    assert outcome.status == "no_data"


async def test_analyze_champion_dry_run_does_not_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_latest(monkeypatch, None)
    pool = _FakePool()

    outcome = await analyze_champion(
        _session_factory, pool, uuid4(), _champion(), dry_run=True
    )

    assert outcome.status == "would_run"
    assert pool.calls == []


@pytest.mark.parametrize("job", [None, _FakeJob(exc=ResultNotFound("expired"))])
async def test_analyze_champion_falls_back_to_db_row(
    monkeypatch: pytest.MonkeyPatch, job: object
) -> None:
    # First lookup (cache check) finds nothing; the fallback poll finds the row
    # written by the in-flight job this run was deduped against.
    row = SimpleNamespace(id=uuid4(), token_count_input=10, token_count_output=5)
    lookups = iter([None, row])

    async def _latest(*args: object, **kwargs: object) -> object | None:
        return next(lookups)

    monkeypatch.setattr(account_pipeline, "latest_analysis", _latest)
    pool = _FakePool(job=job)

    outcome = await analyze_champion(
        _session_factory, pool, uuid4(), _champion(), poll_interval_s=0
    )

    assert outcome.status == "ok"
    assert outcome.analysis_id == str(row.id)


async def test_analyze_champion_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_latest(monkeypatch, None)
    pool = _FakePool(job=_FakeJob(exc=TimeoutError()))

    outcome = await analyze_champion(_session_factory, pool, uuid4(), _champion())

    assert outcome.status == "timeout"


# ── Orchestration ─────────────────────────────────────────────────────


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    pool: _FakePool,
    calls: dict[str, Any],
    champions: list[AnalyzableChampion] | None = None,
) -> UUID:
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, riot_id="tester#NA1")

    async def _resolve(session: object, riot_id: str, *, create: bool) -> tuple[object, bool]:
        calls["create"] = create
        return account, False

    async def _fetch(session: object, rid: str, start: int, count: int) -> tuple[list[str], object]:
        calls["fetch_count"] = count
        return ["NA1_1", "NA1_2"], account

    async def _ids(session: object, rid: UUID) -> list[str]:
        return ["NA1_1", "NA1_2", "NA1_old"]

    async def _unscored(session: object, rid: UUID) -> list[str]:
        return ["NA1_old"]

    async def _counts(session: object, rid: UUID) -> PipelineCounts:
        return PipelineCounts(3, 2, 1, 1)

    async def _details(match_ids: list[str], *, pool: object) -> int:
        calls["details"] = match_ids
        return 1

    async def _extract(match_ids: list[str], *, pool: object) -> int:
        calls["extract"] = match_ids
        return 1

    async def _drain(*args: object, **kwargs: object) -> tuple[PipelineCounts, str]:
        calls["drained"] = True
        return PipelineCounts(3, 3, 3, 3), "complete"

    async def _champions(session: object, rid: UUID) -> list[AnalyzableChampion]:
        return champions or []

    async def _missing(session: object, rid: UUID) -> int:
        return 0

    async def _pool() -> _FakePool:
        return pool

    monkeypatch.setattr(account_pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(account_pipeline, "resolve_or_create_account", _resolve)
    monkeypatch.setattr(account_pipeline, "fetch_match_list_for_riot_account", _fetch)
    monkeypatch.setattr(account_pipeline, "list_account_match_ids", _ids)
    monkeypatch.setattr(account_pipeline, "find_unscored_match_ids", _unscored)
    monkeypatch.setattr(account_pipeline, "get_pipeline_counts", _counts)
    monkeypatch.setattr(account_pipeline, "enqueue_missing_detail_jobs", _details)
    monkeypatch.setattr(account_pipeline, "enqueue_missing_extraction_jobs", _extract)
    monkeypatch.setattr(account_pipeline, "wait_for_drain", _drain)
    monkeypatch.setattr(account_pipeline, "list_analyzable_champions", _champions)
    monkeypatch.setattr(account_pipeline, "count_missing_embeddings", _missing)
    monkeypatch.setattr(account_pipeline, "get_arq_pool", _pool)
    return account_id


async def test_pipeline_fills_every_gap_and_scores_only_unscored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _FakePool()
    calls: dict[str, Any] = {}
    _patch_pipeline(monkeypatch, _settings(), pool, calls)

    report = await run_account_pipeline(
        "tester#NA1", count=40, skip_llm=True, session_factory=_session_factory
    )

    assert calls["create"] is True
    assert calls["fetch_count"] == 40
    # Detail and extraction gap checks cover the full linked history, not just
    # the freshly fetched page, so older unprocessed matches fill in too.
    assert calls["details"] == ["NA1_1", "NA1_2", "NA1_old"]
    assert calls["extract"] == ["NA1_1", "NA1_2", "NA1_old"]
    assert [c[1]["_job_id"] for c in pool.calls] == ["score-actions:v0:NA1_old"]
    assert report.drain_outcome == "complete"
    assert report.llm_skipped_reason == "--skip-llm"
    assert report.champions == []


async def test_pipeline_skips_llm_without_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _FakePool()
    calls: dict[str, Any] = {}
    _patch_pipeline(
        monkeypatch, _settings(openai_api_key=""), pool, calls, champions=[_champion()]
    )

    report = await run_account_pipeline("tester#NA1", session_factory=_session_factory)

    assert report.llm_skipped_reason == "OPENAI_API_KEY not set"
    assert all(call[0][0] != "llm_analysis_job" for call in pool.calls)


async def test_pipeline_dry_run_enqueues_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = _FakePool()
    calls: dict[str, Any] = {}
    _patch_pipeline(monkeypatch, _settings(), pool, calls, champions=[_champion()])
    _patch_latest(monkeypatch, None)

    report = await run_account_pipeline(
        "tester#NA1", dry_run=True, session_factory=_session_factory
    )

    assert calls["create"] is False
    assert "fetch_count" not in calls
    assert "details" not in calls and "drained" not in calls
    assert pool.calls == []
    assert [o.status for o in report.champions] == ["would_run"]


async def test_pipeline_runs_analysis_for_eligible_champions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _FakePool(job=_FakeJob({"status": "ok", "analysis_id": "x"}))
    calls: dict[str, Any] = {}
    cached_row = SimpleNamespace(id=uuid4(), created_at=datetime.now(UTC))
    _patch_pipeline(
        monkeypatch,
        _settings(),
        pool,
        calls,
        champions=[_champion(12, "Alistar"), _champion(99, "Lux")],
    )

    async def _latest(session: object, rid: UUID, name: str, since: object = None) -> object:
        return cached_row if name == "Lux" else None

    monkeypatch.setattr(account_pipeline, "latest_analysis", _latest)

    report = await run_account_pipeline("tester#NA1", session_factory=_session_factory)

    assert [(o.champion_name, o.status) for o in report.champions] == [
        ("Alistar", "ok"),
        ("Lux", "cached"),
    ]
    llm_calls = [c for c in pool.calls if c[0][0] == "llm_analysis_job"]
    assert len(llm_calls) == 1
