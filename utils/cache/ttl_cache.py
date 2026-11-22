"""Single-value async cache with a time-to-live."""

import asyncio
import time
from collections.abc import Awaitable, Callable


class TTLCache[T]:
    """Holds one value for ``ttl_seconds`` and loads it at most once at a time.

    Concurrent callers share a lock, so a cold cache triggers one load, not one
    per caller. A failed load is not cached. ``invalidate`` drops the value and
    also keeps a load that was already in flight from storing a stale result.
    """

    def __init__(
        self,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = asyncio.Lock()
        self._value: T | None = None
        self._expires_at = 0.0
        self._has_value = False
        self._generation = 0

    async def get_or_load(self, loader: Callable[[], Awaitable[T]]) -> T:
        """Return the cached value, calling ``loader`` when it is missing or old."""
        async with self._lock:
            if self._has_value and self._clock() < self._expires_at:
                return self._value  # pyright: ignore[reportReturnType]
            generation = self._generation
            value = await loader()
            if generation == self._generation:
                self._value = value
                self._has_value = True
                self._expires_at = self._clock() + self._ttl_seconds
            return value

    def invalidate(self) -> None:
        """Drop the cached value so the next call loads a fresh one."""
        self._generation += 1
        self._value = None
        self._has_value = False
