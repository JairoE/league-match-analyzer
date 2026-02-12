from __future__ import annotations

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
    arq_pool._arq_pool = None

    pool = await arq_pool.get_arq_pool()
    assert pool is fake

    # Second call returns the same instance (singleton).
    pool2 = await arq_pool.get_arq_pool()
    assert pool2 is fake

    # Cleanup
    arq_pool._arq_pool = None


@pytest.mark.asyncio
async def test_close_arq_pool_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePool()

    async def _fake_create_pool(settings: object) -> _FakePool:
        return fake

    monkeypatch.setattr(arq_pool, "create_pool", _fake_create_pool)
    arq_pool._arq_pool = None

    await arq_pool.get_arq_pool()
    assert arq_pool._arq_pool is fake

    await arq_pool.close_arq_pool()
    assert fake.closed
    assert arq_pool._arq_pool is None


@pytest.mark.asyncio
async def test_close_arq_pool_noop_when_not_created() -> None:
    arq_pool._arq_pool = None
    await arq_pool.close_arq_pool()
    assert arq_pool._arq_pool is None
