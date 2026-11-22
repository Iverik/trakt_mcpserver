"""Tool-level tests for fetch_movie_recommendations.

These run the real tool and the real client against a mocked HTTP layer, so
they assert on the request that would go to Trakt.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from client.recommendations import RecommendationsClient
from models.auth import TraktAuthToken
from server.recommendations.tools import fetch_movie_recommendations
from server.sync.cache import COLLECTED_MOVIES_CACHE, CollectedMovieIds

FIXTURE: list[dict[str, Any]] = [
    {
        "title": "Short Comedy",
        "year": 2020,
        "ids": {"trakt": 1, "slug": "short-comedy-2020"},
        "runtime": 90,
        "genres": ["comedy"],
    },
    {
        "title": "Long Sci-Fi",
        "year": 2021,
        "ids": {"trakt": 2, "slug": "long-sci-fi-2021"},
        "runtime": 160,
        "genres": ["science-fiction", "drama"],
    },
    {
        "title": "Short Sci-Fi",
        "year": 2022,
        "ids": {"trakt": 3, "slug": "short-sci-fi-2022"},
        "runtime": 95,
        "genres": ["science-fiction"],
    },
    {
        "title": "Another Short Sci-Fi",
        "year": 2023,
        "ids": {"trakt": 4, "slug": "another-short-sci-fi-2023"},
        "runtime": 85,
        "genres": ["Science-Fiction"],
    },
]


@pytest.fixture
def collection() -> Iterator[AsyncMock]:
    """Stub the collection lookup: nothing collected unless a test says so."""
    lookup = AsyncMock(return_value=CollectedMovieIds(frozenset(), truncated=False))
    with patch("server.recommendations.tools.collected_movie_ids", lookup):
        yield lookup


@pytest.fixture
def http(
    patched_httpx_client: MagicMock,
    mock_auth_token: TraktAuthToken,
    collection: AsyncMock,
) -> Iterator[MagicMock]:
    """Mocked HTTP layer with the tool wired to an authenticated client."""
    authenticated_client = RecommendationsClient()
    authenticated_client.auth_token = mock_auth_token
    response = MagicMock()
    response.json.return_value = FIXTURE
    response.raise_for_status = MagicMock()
    patched_httpx_client.get.return_value = response
    with patch(
        "server.recommendations.tools.get_client", return_value=authenticated_client
    ):
        yield patched_httpx_client


def _params(http: MagicMock) -> dict[str, Any]:
    return http.get.call_args[1].get("params", {})


@pytest.mark.asyncio
async def test_tool_default_sends_ignore_collected_true(http: MagicMock) -> None:
    """The tool default (ignore_collected=True) reaches the request."""
    await fetch_movie_recommendations()
    assert _params(http)["ignore_collected"] == "true"


@pytest.mark.asyncio
async def test_tool_passes_ignore_collected_false_through(http: MagicMock) -> None:
    """ignore_collected=False must drop the param from the request."""
    await fetch_movie_recommendations(ignore_collected=False)
    assert "ignore_collected" not in _params(http)


@pytest.mark.asyncio
async def test_no_filters_leaves_request_and_output_unchanged(http: MagicMock) -> None:
    result = await fetch_movie_recommendations(
        limit=5, ignore_collected=False, ignore_watchlisted=False
    )
    params = _params(http)
    assert params["limit"] == 5
    assert "extended" not in params
    assert "Filters" not in result
    assert "### Short Comedy (2020)" in result
    assert "### Long Sci-Fi (2021)" in result


@pytest.mark.asyncio
async def test_max_runtime_requests_full_and_max_limit(http: MagicMock) -> None:
    result = await fetch_movie_recommendations(limit=2, max_runtime=100)
    params = _params(http)
    assert params["extended"] == "full"
    assert params["limit"] == 100
    assert "Long Sci-Fi" not in result
    assert "1 filtered out (0 as collected, 1 by runtime)" in result
    # Trimmed to the requested limit of 2 out of 3 matches.
    assert "3 matched, showing 2" in result
    assert "Short Comedy" in result
    assert "Another Short Sci-Fi" not in result


@pytest.mark.asyncio
async def test_genres_include_is_case_insensitive_and_matches_any(
    http: MagicMock,
) -> None:
    result = await fetch_movie_recommendations(genres_include=["SCIENCE-FICTION"])
    assert _params(http)["extended"] == "full"
    assert "Short Comedy" not in result
    assert "Long Sci-Fi" in result
    assert "Short Sci-Fi" in result
    assert "Another Short Sci-Fi" in result
    assert "1 filtered out (0 as collected, 1 by genre)" in result

    result = await fetch_movie_recommendations(genres_include=["comedy", "drama"])
    assert "Short Comedy" in result
    assert "Long Sci-Fi" in result
    assert "Short Sci-Fi (2022)" not in result


@pytest.mark.asyncio
async def test_filters_combine(http: MagicMock) -> None:
    result = await fetch_movie_recommendations(
        max_runtime=100, genres_include=["science-fiction"]
    )
    assert "Short Sci-Fi (2022)" in result
    assert "Another Short Sci-Fi" in result
    assert "Short Comedy" not in result
    assert "Long Sci-Fi" not in result
    assert "2 matched, showing 2" in result


@pytest.mark.asyncio
async def test_no_match_says_so(http: MagicMock) -> None:
    result = await fetch_movie_recommendations(max_runtime=10)
    assert "4 filtered out" in result
    assert "No recommendations matched the filters." in result


@pytest.mark.asyncio
async def test_empty_genre_list_is_no_filter(http: MagicMock) -> None:
    await fetch_movie_recommendations(genres_include=[])
    assert "extended" not in _params(http)


@pytest.mark.asyncio
async def test_invalid_genre_rejected_before_any_request(http: MagicMock) -> None:
    with pytest.raises(ValueError, match="Invalid genre slug"):
        await fetch_movie_recommendations(genres_include=["not a slug"])
    http.get.assert_not_called()


@pytest.mark.asyncio
async def test_collected_movies_are_dropped_and_counted(
    http: MagicMock, collection: AsyncMock
) -> None:
    collection.return_value = CollectedMovieIds(frozenset({1, 3}), truncated=False)
    result = await fetch_movie_recommendations(limit=10)
    params = _params(http)
    # Still asked of Trakt, over-fetched, but no extended metadata needed.
    assert params["ignore_collected"] == "true"
    assert params["limit"] == 100
    assert "extended" not in params
    assert "Short Comedy" not in result
    assert "Short Sci-Fi (2022)" not in result
    assert "Long Sci-Fi" in result
    assert "Another Short Sci-Fi" in result
    assert "not collected" in result
    assert "2 filtered out (2 as collected)" in result
    assert "2 matched, showing 2" in result


@pytest.mark.asyncio
async def test_collected_filter_trims_to_limit_after_dropping(
    http: MagicMock, collection: AsyncMock
) -> None:
    collection.return_value = CollectedMovieIds(frozenset({1}), truncated=False)
    result = await fetch_movie_recommendations(limit=2)
    assert "Short Comedy" not in result
    assert "3 matched, showing 2" in result
    assert "Another Short Sci-Fi" not in result


@pytest.mark.asyncio
async def test_collected_combines_with_runtime_filter(
    http: MagicMock, collection: AsyncMock
) -> None:
    collection.return_value = CollectedMovieIds(frozenset({1}), truncated=False)
    result = await fetch_movie_recommendations(max_runtime=100)
    assert _params(http)["extended"] == "full"
    assert "1 as collected, 1 by runtime" in result
    assert "2 matched" in result


@pytest.mark.asyncio
async def test_ignore_collected_false_keeps_collected_and_skips_lookup(
    http: MagicMock, collection: AsyncMock
) -> None:
    collection.return_value = CollectedMovieIds(
        frozenset({1, 2, 3, 4}), truncated=False
    )
    result = await fetch_movie_recommendations(ignore_collected=False)
    assert "Short Comedy" in result
    assert "Filters" not in result
    collection.assert_not_called()
    assert _params(http)["limit"] == 10


@pytest.mark.asyncio
async def test_collection_failure_still_returns_recommendations(
    http: MagicMock, collection: AsyncMock
) -> None:
    collection.side_effect = RuntimeError("boom")
    result = await fetch_movie_recommendations(limit=10)
    assert "Short Comedy" in result
    assert "Long Sci-Fi" in result
    assert "Collected items could not be filtered" in result
    assert "as collected" not in result


@pytest.mark.asyncio
async def test_nothing_collected_says_zero_dropped(http: MagicMock) -> None:
    result = await fetch_movie_recommendations(limit=10)
    assert "0 as collected" in result
    assert "Short Comedy" in result


@pytest.mark.asyncio
async def test_collection_is_loaded_once_across_calls(
    patched_httpx_client: MagicMock, mock_auth_token: TraktAuthToken
) -> None:
    """The real lookup goes through the shared cache, not one fetch per call."""
    from models.sync.collection import (
        CollectionFetchResult,
        CollectionItem,
        CollectionMovie,
    )
    from models.types.ids import TraktIds

    fetched = CollectionFetchResult(
        items=[
            CollectionItem(
                movie=CollectionMovie(title="Short Comedy", ids=TraktIds(trakt=1))
            )
        ],
        pages_fetched=1,
    )
    loader = AsyncMock(return_value=fetched)
    client = RecommendationsClient()
    client.auth_token = mock_auth_token
    response = MagicMock()
    response.json.return_value = FIXTURE
    response.raise_for_status = MagicMock()
    patched_httpx_client.get.return_value = response
    COLLECTED_MOVIES_CACHE.invalidate()
    try:
        with (
            patch("server.recommendations.tools.get_client", return_value=client),
            patch("server.sync.cache.load_collected_movies", loader),
        ):
            first = await fetch_movie_recommendations()
            await fetch_movie_recommendations()
    finally:
        COLLECTED_MOVIES_CACHE.invalidate()
    assert "Short Comedy" not in first
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_truncated_collection_adds_a_note(
    http: MagicMock, collection: AsyncMock
) -> None:
    collection.return_value = CollectedMovieIds(frozenset({1}), truncated=True)
    result = await fetch_movie_recommendations()
    assert "Collection read was cut short" in result
    assert "Short Comedy" not in result


@pytest.mark.asyncio
async def test_unauthenticated_fails_before_the_collection_is_read(
    http: MagicMock, collection: AsyncMock
) -> None:
    with patch.object(
        RecommendationsClient, "ensure_authenticated", AsyncMock(return_value=False)
    ):
        result = await fetch_movie_recommendations()
    assert "Short Comedy" not in result
    collection.assert_not_called()
