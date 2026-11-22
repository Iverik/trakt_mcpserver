"""Tests for the have_i_seen tool in server.sync.tools."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from models.movies.movie import TraktMovie
from models.sync.base import TraktSyncRating
from models.sync.collection import CollectionMovie
from models.sync.ratings import SyncRatingsSummary, SyncRatingsSummaryCount
from models.sync.watched import WatchedMovieItem
from models.types.ids import TraktIds
from server.sync.tools import (
    UserRatingIdentifier,
    UserRatingRequestItem,
    add_user_ratings,
    have_i_seen,
    register_sync_tools,
    remove_user_ratings,
)
from utils.api.errors import InternalError


def _watched(trakt: int, title: str, plays: int, last: str) -> WatchedMovieItem:
    return WatchedMovieItem(
        plays=plays,
        last_watched_at=datetime.fromisoformat(last),
        movie=CollectionMovie(title=title, year=2010, ids=TraktIds(trakt=trakt)),
    )


def _rated(trakt: int, title: str, rating: int) -> TraktSyncRating:
    return TraktSyncRating(
        rated_at=datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
        rating=rating,
        type="movie",
        movie=TraktMovie(title=title, year=1999, ids=TraktIds(trakt=trakt)),
    )


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.ensure_authenticated = AsyncMock(return_value=True)
    client.get_watched_movies = AsyncMock(
        return_value=[
            _watched(1, "Inception", 3, "2024-03-01T20:00:00+00:00"),
            _watched(2, "Heat", 1, "2023-05-06T20:00:00+00:00"),
        ]
    )
    client.get_all_sync_ratings = AsyncMock(
        return_value=[_rated(1, "Inception", 9), _rated(3, "Memento", 8)]
    )
    return client


@pytest.mark.asyncio
async def test_mixes_watched_unwatched_and_rated() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client_class.return_value = _mock_client()

        output = await have_i_seen([1, 2, 3, 4])

    assert "Checked: 4 | Watched: 2 | Not watched: 2" in output
    assert "1 | Inception (2010) | watched 3x | last 2024-03-01 | rated 9/10" in output
    assert "2 | Heat (2010) | watched 1x | last 2023-05-06" in output
    assert "2 | Heat (2010) | watched 1x | last 2023-05-06 | rated" not in output
    assert "3 | Memento (1999) | not watched | rated 8/10" in output
    assert "\n4 | not found in your watch history or ratings" in output


@pytest.mark.asyncio
async def test_duplicate_ids_are_reported_once_in_order() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client_class.return_value = _mock_client()

        output = await have_i_seen([2, 1, 2])

    assert output.index("\n2 |") < output.index("\n1 |")
    assert output.count("\n2 |") == 1


@pytest.mark.asyncio
async def test_repeated_calls_fetch_watched_and_ratings_once() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client()

        await have_i_seen([1])
        await have_i_seen([2, 3])

    assert client.get_watched_movies.await_count == 1
    assert client.get_all_sync_ratings.await_count == 1


@pytest.mark.asyncio
async def test_rating_writes_invalidate_the_ratings_cache() -> None:
    summary = SyncRatingsSummary(added=SyncRatingsSummaryCount(movies=1))
    item = UserRatingRequestItem(rating=9, trakt_id="1")
    removal = UserRatingIdentifier(trakt_id="1")
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client()
        client.add_sync_ratings = AsyncMock(return_value=summary)
        client.remove_sync_ratings = AsyncMock(return_value=summary)

        await have_i_seen([1])
        await add_user_ratings("movies", [item])
        await have_i_seen([1])
        await remove_user_ratings("movies", [removal])
        await have_i_seen([1])

    assert client.get_all_sync_ratings.await_count == 3
    assert client.get_watched_movies.await_count == 1


@pytest.mark.asyncio
async def test_rating_write_that_raises_still_drops_the_ratings_cache() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client()
        client.add_sync_ratings = AsyncMock(side_effect=TimeoutError("timed out"))

        await have_i_seen([1])
        with pytest.raises(InternalError):
            await add_user_ratings(
                "movies", [UserRatingRequestItem(rating=9, trakt_id="1")]
            )
        await have_i_seen([1])

    assert client.get_all_sync_ratings.await_count == 2


@pytest.mark.asyncio
async def test_logged_out_session_is_not_served_cached_data() -> None:
    with patch("server.sync.tools.SyncClient") as client_class:
        client = client_class.return_value = _mock_client()
        await have_i_seen([1])

        client.ensure_authenticated = AsyncMock(return_value=False)
        output = await have_i_seen([1])

    assert "Inception" not in output
    assert "authenticat" in output.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_ids",
    [[], [0], [-5], list(range(1, 102))],
    ids=["empty", "zero", "neg", "many"],
)
async def test_invalid_ids_are_rejected(bad_ids: list[int]) -> None:
    with pytest.raises(ValidationError):
        await have_i_seen(bad_ids)


@pytest.mark.asyncio
async def test_tool_is_registered_with_bounded_schema() -> None:
    mcp = FastMCP("test")
    register_sync_tools(mcp)

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    schema = json.loads(json.dumps(tools["have_i_seen"].inputSchema))
    assert schema["required"] == ["trakt_ids"]
    assert schema["properties"]["trakt_ids"]["maxItems"] == 100
    assert schema["properties"]["trakt_ids"]["minItems"] == 1
