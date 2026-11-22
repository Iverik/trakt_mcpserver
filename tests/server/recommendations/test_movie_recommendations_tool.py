"""Tool-level tests for fetch_movie_recommendations.

These run the real tool and the real client against a mocked HTTP layer, so
they assert on the request that would go to Trakt.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from client.recommendations import RecommendationsClient
from models.auth import TraktAuthToken
from server.recommendations.tools import fetch_movie_recommendations

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
def http(
    patched_httpx_client: MagicMock, mock_auth_token: TraktAuthToken
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
    result = await fetch_movie_recommendations(limit=5)
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
    assert "1 filtered out (1 by runtime, 0 by genre)" in result
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
    assert "1 filtered out (0 by runtime, 1 by genre)" in result

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
