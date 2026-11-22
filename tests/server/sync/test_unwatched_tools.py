"""Tests for the unwatched_in_collection tool in server.sync.tools."""

import json
import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from models.sync.collection import (
    CollectionFetchResult,
    CollectionItem,
    CollectionMovie,
)
from models.sync.history import HistorySummary, HistorySummaryCount
from models.sync.watched import WatchedMovieItem
from models.types.ids import TraktIds
from server.sync.tools import (
    HistoryRemoveItem,
    HistoryRequestItem,
    add_to_history,
    register_sync_tools,
    remove_from_history,
    unwatched_in_collection,
)
from utils.api.errors import InternalError


def _collected(trakt: int, title: str, rating: float) -> CollectionItem:
    return CollectionItem(
        movie=CollectionMovie(
            title=title,
            year=2010,
            ids=TraktIds(trakt=trakt),
            runtime=100,
            genres=["drama"],
            rating=rating,
        )
    )


def _watched(trakt: int) -> WatchedMovieItem:
    return WatchedMovieItem(
        plays=1, movie=CollectionMovie(title=f"W{trakt}", ids=TraktIds(trakt=trakt))
    )


def _mock_client(watched: list[WatchedMovieItem]) -> MagicMock:
    client = MagicMock()
    client.ensure_authenticated = AsyncMock(return_value=True)
    client.get_collection = AsyncMock(
        return_value=CollectionFetchResult(
            items=[
                _collected(1, "Alpha", 6.0),
                _collected(2, "Beta", 8.0),
                _collected(3, "Gamma", 7.0),
            ],
            pages_fetched=1,
        )
    )
    client.get_watched_movies = AsyncMock(return_value=watched)
    return client


@pytest.mark.asyncio
async def test_lists_unwatched_sorted_with_counts() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client([_watched(2)])

        output = await unwatched_in_collection(sort="rating", limit=1)

    client.get_collection.assert_awaited_once_with(
        "movies", include_metadata=True, include_details=True
    )
    assert "Collected: 3 | Watched: 1 | Unwatched matching filters: 2 | Shown: 1" in (
        output
    )
    assert "Gamma (2010) | 1h 40m | drama | 7.0" in output
    assert "Beta" not in output


@pytest.mark.asyncio
async def test_random_sort_uses_the_injected_source() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client_class.return_value = _mock_client([])

        first = await unwatched_in_collection(
            sort="random",
            rng=random.Random(5),  # noqa: S311
        )
        second = await unwatched_in_collection(
            sort="random",
            rng=random.Random(5),  # noqa: S311
        )

    assert first == second


@pytest.mark.asyncio
async def test_repeated_calls_fetch_once() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client([])

        await unwatched_in_collection()
        await unwatched_in_collection(sort="runtime")

    assert client.get_collection.await_count == 1
    assert client.get_watched_movies.await_count == 1


@pytest.mark.asyncio
async def test_add_to_history_invalidates_the_watched_cache() -> None:
    summary = HistorySummary(added=HistorySummaryCount(movies=1))
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client([])
        client.add_to_history = AsyncMock(return_value=summary)

        await unwatched_in_collection()
        await add_to_history("movies", [HistoryRequestItem(trakt_id="2")])
        await unwatched_in_collection()

    assert client.get_watched_movies.await_count == 2
    assert client.get_collection.await_count == 1


@pytest.mark.asyncio
async def test_remove_from_history_invalidates_the_watched_cache() -> None:
    summary = HistorySummary(deleted=HistorySummaryCount(movies=1))
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client([_watched(2)])
        client.remove_from_history = AsyncMock(return_value=summary)

        await unwatched_in_collection()
        await remove_from_history("movies", [HistoryRemoveItem(trakt_id="2")])
        await unwatched_in_collection()

    assert client.get_watched_movies.await_count == 2


@pytest.mark.asyncio
async def test_failed_history_write_still_drops_the_cache() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client([])
        client.add_to_history = AsyncMock(return_value="API error")

        await unwatched_in_collection()
        output = await add_to_history("movies", [HistoryRequestItem(trakt_id="2")])
        assert output.startswith("# Error")
        await unwatched_in_collection()

    assert client.get_watched_movies.await_count == 2


@pytest.mark.asyncio
async def test_history_write_that_raises_still_drops_the_cache() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client([])
        client.add_to_history = AsyncMock(side_effect=TimeoutError("timed out"))

        await unwatched_in_collection()
        with pytest.raises(InternalError):
            await add_to_history("movies", [HistoryRequestItem(trakt_id="2")])
        await unwatched_in_collection()

    assert client.get_watched_movies.await_count == 2


@pytest.mark.asyncio
async def test_logged_out_session_is_not_served_cached_data() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client([])
        await unwatched_in_collection()

        client.ensure_authenticated = AsyncMock(return_value=False)
        output = await unwatched_in_collection()

    assert "Collected:" not in output
    assert "authenticat" in output.lower()
    assert client.get_collection.await_count == 1


@pytest.mark.asyncio
async def test_invalid_parameters_are_rejected() -> None:
    with pytest.raises(ValidationError):
        await unwatched_in_collection(min_runtime=120, max_runtime=90)


@pytest.mark.asyncio
async def test_tool_is_registered_with_bounded_schema() -> None:
    mcp = FastMCP("test")
    register_sync_tools(mcp)

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    schema = json.loads(json.dumps(tools["unwatched_in_collection"].inputSchema))
    assert set(schema["properties"]) == {
        "collection_type",
        "min_runtime",
        "max_runtime",
        "genres_include",
        "genres_exclude",
        "min_trakt_rating",
        "sort",
        "limit",
    }
    assert schema["properties"]["limit"]["maximum"] == 100
    assert schema["properties"]["collection_type"].get("const") == "movies" or (
        schema["properties"]["collection_type"].get("enum") == ["movies"]
    )
    assert "required" not in schema
