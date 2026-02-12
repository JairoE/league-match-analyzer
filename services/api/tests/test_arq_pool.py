from __future__ import annotations

import asyncio
import pytest

from app.services import arq_pool


class _FakePool:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_get_arq_pool_creates_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePool()

    async def _fake_create_pool(settings: object) -> _FakePool:
        return fake

    monkeypatch.setattr(arq_pool, "create_pool", _fake_create_pool)
    arq_pool._arq_pool_task = None

    pool = await arq_pool.get_arq_pool()
    assert pool is fake

    # Second call returns the same instance (singleton).
    pool2 = await arq_pool.get_arq_pool()
    assert pool2 is fake

    # Cleanup
    arq_pool._arq_pool_task = None


@pytest.mark.asyncio
async def test_close_arq_pool_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePool()

    async def _fake_create_pool(settings: object) -> _FakePool:
        return fake

    monkeypatch.setattr(arq_pool, "create_pool", _fake_create_pool)
    arq_pool._arq_pool_task = None

    await arq_pool.get_arq_pool()

    await arq_pool.close_arq_pool()
    assert fake.closed
    assert arq_pool._arq_pool_task is None


@pytest.mark.asyncio
async def test_close_arq_pool_noop_when_not_created() -> None:
    arq_pool._arq_pool_task = None
    await arq_pool.close_arq_pool()
    assert arq_pool._arq_pool_task is None


@pytest.mark.asyncio
async def test_get_arq_pool_concurrent_creates_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePool()
    create_calls = 0

    async def _fake_create_pool(settings: object) -> _FakePool:
        nonlocal create_calls
        create_calls += 1
        # allow scheduling competition
        await asyncio.sleep(0)
        return fake

    monkeypatch.setattr(arq_pool, "create_pool", _fake_create_pool)
    arq_pool._arq_pool_task = None

    results = await asyncio.gather(
        arq_pool.get_arq_pool(),
        arq_pool.get_arq_pool(),
    )

    assert create_calls == 1
    assert results[0] is fake
    assert results[1] is fake

    # Cleanup
    arq_pool._arq_pool_task = None
