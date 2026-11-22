"""Tests for the cross-domain collected_movie_ids lookup."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from models.shows.show import TraktShow
from models.sync.collection import (
    CollectionFetchResult,
    CollectionItem,
    CollectionMovie,
)
from models.types.ids import TraktIds
from server.sync.cache import COLLECTED_MOVIES_CACHE, collected_movie_ids


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    COLLECTED_MOVIES_CACHE.invalidate()
    yield
    COLLECTED_MOVIES_CACHE.invalidate()


def _movie(trakt: int | None) -> CollectionItem:
    return CollectionItem(
        movie=CollectionMovie(title=f"M{trakt}", ids=TraktIds(trakt=trakt))
    )


@pytest.mark.asyncio
async def test_returns_trakt_ids_skipping_non_movies_and_missing_ids() -> None:
    result = CollectionFetchResult(
        items=[
            _movie(1),
            _movie(None),
            CollectionItem(show=TraktShow(title="S", ids=TraktIds(trakt=9))),
            _movie(3),
        ],
        pages_fetched=1,
        truncated=True,
    )
    loader = AsyncMock(return_value=result)
    with patch("server.sync.cache.load_collected_movies", loader):
        found = await collected_movie_ids()
    assert found.ids == frozenset({1, 3})
    assert found.truncated is True


@pytest.mark.asyncio
async def test_second_call_reuses_the_cache() -> None:
    loader = AsyncMock(
        return_value=CollectionFetchResult(items=[_movie(1)], pages_fetched=1)
    )
    with patch("server.sync.cache.load_collected_movies", loader):
        await collected_movie_ids()
        await collected_movie_ids()
    loader.assert_awaited_once()
