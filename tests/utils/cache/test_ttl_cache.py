"""Tests for the utils.cache.ttl_cache module."""

import asyncio

import pytest

from utils.cache.ttl_cache import TTLCache


class FakeClock:
    """Manually advanced clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Loader:
    """Counts calls and returns the call number."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> int:
        self.calls += 1
        await asyncio.sleep(0)
        return self.calls


@pytest.mark.asyncio
async def test_second_call_within_ttl_is_a_cache_hit() -> None:
    cache = TTLCache[int](900, FakeClock())
    loader = Loader()

    assert await cache.get_or_load(loader) == 1
    assert await cache.get_or_load(loader) == 1
    assert loader.calls == 1


@pytest.mark.asyncio
async def test_value_reloads_after_ttl_expires() -> None:
    clock = FakeClock()
    cache = TTLCache[int](900, clock)
    loader = Loader()

    await cache.get_or_load(loader)
    clock.now += 899
    assert await cache.get_or_load(loader) == 1
    clock.now += 1
    assert await cache.get_or_load(loader) == 2
    assert loader.calls == 2


@pytest.mark.asyncio
async def test_invalidate_forces_a_reload() -> None:
    cache = TTLCache[int](900, FakeClock())
    loader = Loader()

    await cache.get_or_load(loader)
    cache.invalidate()

    assert await cache.get_or_load(loader) == 2


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_load() -> None:
    cache = TTLCache[int](900, FakeClock())
    loader = Loader()

    results = await asyncio.gather(*(cache.get_or_load(loader) for _ in range(5)))

    assert results == [1] * 5
    assert loader.calls == 1


@pytest.mark.asyncio
async def test_failed_load_is_not_cached() -> None:
    cache = TTLCache[int](900, FakeClock())
    attempts = 0

    async def flaky() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        return 7

    with pytest.raises(RuntimeError):
        await cache.get_or_load(flaky)

    assert await cache.get_or_load(flaky) == 7


@pytest.mark.asyncio
async def test_invalidate_during_load_does_not_store_the_stale_value() -> None:
    cache = TTLCache[int](900, FakeClock())
    loader = Loader()

    async def invalidating() -> int:
        cache.invalidate()
        return 99

    assert await cache.get_or_load(invalidating) == 99
    assert await cache.get_or_load(loader) == 1
