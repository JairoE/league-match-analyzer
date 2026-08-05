"""Tests for enqueue_missing_extraction_jobs.

Focus areas (adversarial-review findings):
  - DB and ARQ pool failures must be swallowed, not propagated into a
    Starlette BackgroundTasks callback (which has zero error handling).
  - arq's enqueue_job returns None (not a raise) on a deduped job id; that
    must be counted separately from a genuine enqueue.
"""
from __future__ import annotations

import logging

import pytest

from app.services import enqueue_timeline_extraction
from app.services.enqueue_timeline_extraction import enqueue_missing_extraction_jobs


class _Result:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[str]]:
        return self._rows


class _DummySession:
    """Returns canned results in call order: already_extracted, then game_info."""

    def __init__(self, results: list[_Result]) -> None:
        self._results = list(results)

    async def execute(self, stmt: object) -> _Result:
        return self._results.pop(0)


class _DummyDbContext:
    def __init__(self, session: _DummySession) -> None:
        self._session = session

    async def __aenter__(self) -> _DummySession:
        return self._session

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _RaisingDbContext:
    async def __aenter__(self) -> _DummySession:
        raise OSError("db connection refused")

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _FakePool:
    """Fake ARQ pool whose enqueue_job return value is scripted per call."""

    def __init__(self, results: list[object]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, tuple, dict]] = []

    async def enqueue_job(self, function_name: str, *args: object, **kwargs: object) -> object:
        self.calls.append((function_name, args, kwargs))
        return self._results.pop(0)


def _all_have_game_info(match_ids: list[str]) -> list[_Result]:
    return [
        _Result([]),  # already_extracted: none
        _Result([(mid,) for mid in match_ids]),  # has_game_info: all
    ]


async def test_enqueue_missing_extraction_jobs_empty_input() -> None:
    result = await enqueue_missing_extraction_jobs([])
    assert result == 0


async def test_enqueue_missing_extraction_jobs_db_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A DB error must return 0 and log a warning, never propagate.

    Starlette's BackgroundTasks has zero error handling: an uncaught
    exception here would blow up the ASGI app after the response is
    already flushed.
    """
    monkeypatch.setattr(
        enqueue_timeline_extraction, "async_session_factory", lambda: _RaisingDbContext()
    )

    with caplog.at_level(logging.WARNING):
        result = await enqueue_missing_extraction_jobs(["NA1_1", "NA1_2"])

    assert result == 0
    assert any(
        record.message == "enqueue_missing_extraction_db_unavailable"
        for record in caplog.records
    )


async def test_enqueue_missing_extraction_jobs_pool_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """get_arq_pool raising (e.g. Redis down) must return 0, not propagate."""
    match_ids = ["NA1_1"]
    session = _DummySession(_all_have_game_info(match_ids))
    monkeypatch.setattr(
        enqueue_timeline_extraction, "async_session_factory", lambda: _DummyDbContext(session)
    )

    async def _raising_get_arq_pool() -> object:
        raise OSError("redis connection refused")

    monkeypatch.setattr(enqueue_timeline_extraction, "get_arq_pool", _raising_get_arq_pool)

    with caplog.at_level(logging.WARNING):
        result = await enqueue_missing_extraction_jobs(match_ids)

    assert result == 0
    assert any(
        record.message == "enqueue_missing_extraction_pool_unavailable"
        for record in caplog.records
    )


async def test_enqueue_missing_extraction_jobs_none_job_counts_as_deduped(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """arq returns None (no raise) when the job id is already queued/retained.

    That must not be counted as a successful enqueue.
    """
    match_ids = ["NA1_1"]
    session = _DummySession(_all_have_game_info(match_ids))
    monkeypatch.setattr(
        enqueue_timeline_extraction, "async_session_factory", lambda: _DummyDbContext(session)
    )
    pool = _FakePool([None])

    result = await enqueue_missing_extraction_jobs(match_ids, pool=pool)

    assert result == 0
    assert len(pool.calls) == 1


async def test_enqueue_missing_extraction_jobs_truthy_job_counts_as_enqueued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truthy Job object from enqueue_job is a genuine new enqueue."""
    match_ids = ["NA1_1", "NA1_2"]
    session = _DummySession(_all_have_game_info(match_ids))
    monkeypatch.setattr(
        enqueue_timeline_extraction, "async_session_factory", lambda: _DummyDbContext(session)
    )
    fake_job = object()
    pool = _FakePool([fake_job, fake_job])

    result = await enqueue_missing_extraction_jobs(match_ids, pool=pool)

    assert result == 2
    assert len(pool.calls) == 2


async def test_enqueue_missing_extraction_jobs_mixed_enqueued_and_deduped(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Deduped and genuinely-enqueued ids are counted separately in the log."""
    match_ids = ["NA1_1", "NA1_2", "NA1_3"]
    session = _DummySession(_all_have_game_info(match_ids))
    monkeypatch.setattr(
        enqueue_timeline_extraction, "async_session_factory", lambda: _DummyDbContext(session)
    )
    # sorted order: NA1_1, NA1_2, NA1_3 -> enqueued, deduped, enqueued
    pool = _FakePool([object(), None, object()])

    with caplog.at_level(logging.INFO):
        result = await enqueue_missing_extraction_jobs(match_ids, pool=pool)

    assert result == 2
    done_record = next(
        record for record in caplog.records if record.message == "enqueue_missing_extraction_done"
    )
    assert done_record.enqueued == 2
    assert done_record.deduped == 1
