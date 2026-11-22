"""Shared fixtures for sync tool tests."""

from collections.abc import Iterator

import pytest

from server.sync.cache import invalidate_all_caches


@pytest.fixture(autouse=True)
def _fresh_sync_caches() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Start and end every test with empty process-wide sync caches."""
    invalidate_all_caches()
    yield
    invalidate_all_caches()
