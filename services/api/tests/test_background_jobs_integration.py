from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.jobs import match_ingestion, scheduled
from app.jobs.scheduled import sync_all_users_matches
from app.services.background_jobs import WorkerSettings


class _DummySessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _FakeRedisQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def enqueue_job(self, function_name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((function_name, args, kwargs))


def test_worker_settings_registers_cron_job() -> None:
    settings = get_settings()
    cron_job = WorkerSettings.cron_jobs[0]
    assert cron_job.coroutine is scheduled.sync_all_users_matches
    assert cron_job.run_at_startup is settings.arq_cron_run_at_startup
    assert 0 in cron_job.minute
    assert 21 not in cron_job.minute


@pytest.mark.asyncio
async def test_sync_all_users_matches_enqueues_all_active_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = [
        SimpleNamespace(id=uuid4(), riot_id="user#one"),
        SimpleNamespace(id=uuid4(), riot_id="user#two"),
    ]
    redis = _FakeRedisQueue()

    async def _fake_list_all_active_users(
        session: object, active_window_days: int = 7
    ) -> list[SimpleNamespace]:
        assert active_window_days == 7
        return users

    async def _noop_metric(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(scheduled, "async_session_factory", lambda: _DummySessionContext())
    monkeypatch.setattr(scheduled, "list_all_active_users", _fake_list_all_active_users)
    monkeypatch.setattr(scheduled, "increment_metric_safe", _noop_metric)

    result = await sync_all_users_matches({"redis": redis})

    assert result["status"] == "ok"
    assert result["total_users"] == 2
    assert result["users_queued"] == 2
    assert len(redis.calls) == 2
    assert all(name == "fetch_user_matches_job" for name, _, _ in redis.calls)
    assert all("_job_id" in kwargs for _, _, kwargs in redis.calls)


@pytest.mark.asyncio
async def test_enqueue_detail_jobs_batches_of_five(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FakeRedisQueue()
    match_ids = [f"NA1_{index}" for index in range(12)]

    class _Result:
        def fetchall(self) -> list[tuple[str]]:
            return [(match_id,) for match_id in match_ids]

    class _DummySession:
        async def execute(self, stmt: object) -> _Result:
            return _Result()

    class _DummyDbContext:
        async def __aenter__(self) -> _DummySession:
            return _DummySession()

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    async def _noop_metric(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(match_ingestion, "async_session_factory", lambda: _DummyDbContext())
    monkeypatch.setattr(match_ingestion, "increment_metric_safe", _noop_metric)

    await match_ingestion._enqueue_detail_jobs({"redis": redis}, match_ids)

    assert len(redis.calls) == 3
    assert [len(args[0]) for _, args, _ in redis.calls] == [5, 5, 2]
    assert all(name == "fetch_match_details_job" for name, _, _ in redis.calls)
