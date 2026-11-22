"""Tests that recommendation query params reach the outgoing request."""

from unittest.mock import MagicMock

import pytest

from client.recommendations import RecommendationsClient


def _ok_response(items: list[dict[str, object]]) -> MagicMock:
    response = MagicMock()
    response.json.return_value = items
    response.raise_for_status = MagicMock()
    return response


async def _sent_params(
    client: RecommendationsClient, http: MagicMock, **kwargs: object
) -> dict[str, object]:
    http.get.return_value = _ok_response([])
    await client.get_movie_recommendations(**kwargs)  # type: ignore[arg-type]
    return http.get.call_args[1].get("params", {})


@pytest.mark.asyncio
async def test_ignore_collected_true_is_sent(
    patched_httpx_client: MagicMock,
    authenticated_client: RecommendationsClient,
) -> None:
    """ignore_collected=True puts ignore_collected=true in the request."""
    params = await _sent_params(
        authenticated_client, patched_httpx_client, ignore_collected=True
    )
    assert params["ignore_collected"] == "true"


@pytest.mark.asyncio
async def test_ignore_collected_false_is_absent(
    patched_httpx_client: MagicMock,
    authenticated_client: RecommendationsClient,
) -> None:
    """ignore_collected=False leaves the param out of the request entirely."""
    params = await _sent_params(
        authenticated_client, patched_httpx_client, ignore_collected=False
    )
    assert "ignore_collected" not in params


@pytest.mark.asyncio
async def test_default_request_has_no_extended_param(
    patched_httpx_client: MagicMock,
    authenticated_client: RecommendationsClient,
) -> None:
    """Without filters the request is unchanged: only limit is sent."""
    params = await _sent_params(authenticated_client, patched_httpx_client, limit=10)
    assert params == {"limit": 10}


@pytest.mark.asyncio
async def test_extended_sends_extended_full(
    patched_httpx_client: MagicMock,
    authenticated_client: RecommendationsClient,
) -> None:
    """extended=True sends extended=full."""
    params = await _sent_params(
        authenticated_client, patched_httpx_client, limit=100, extended=True
    )
    assert params == {"limit": 100, "extended": "full"}


@pytest.mark.asyncio
async def test_extended_response_parses_runtime_and_genres(
    patched_httpx_client: MagicMock,
    authenticated_client: RecommendationsClient,
) -> None:
    """Runtime and genres from an extended response land on the model."""
    patched_httpx_client.get.return_value = _ok_response(
        [
            {
                "title": "Arrival",
                "year": 2016,
                "ids": {"trakt": 1, "slug": "arrival-2016"},
                "runtime": 116,
                "genres": ["drama", "science-fiction"],
            }
        ]
    )
    result = await authenticated_client.get_movie_recommendations(extended=True)
    assert not isinstance(result, str)
    assert result[0].runtime == 116
    assert result[0].genres == ["drama", "science-fiction"]
