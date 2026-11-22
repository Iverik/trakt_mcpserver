# pyright: reportPrivateUsage=false
"""Tests for UserClient.get_user_stats and the 204 handling it relies on."""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from client.user import UserClient
from models.user.stats import UserStats
from utils.api.error_types import AuthenticationRequiredError


@pytest.fixture
def user_client(monkeypatch: pytest.MonkeyPatch) -> UserClient:
    monkeypatch.setenv("TRAKT_CLIENT_ID", "test_id")
    monkeypatch.setenv("TRAKT_CLIENT_SECRET", "test_secret")
    return UserClient()


def _serve(client: UserClient, response: httpx.Response) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    client._client = httpx.AsyncClient(
        base_url=client.BASE_URL, transport=httpx.MockTransport(record)
    )
    return seen


@pytest.mark.asyncio
async def test_get_user_stats_full(
    user_client: UserClient, user_stats_full: dict[str, Any]
) -> None:
    seen = _serve(user_client, httpx.Response(200, json=user_stats_full))
    with patch.object(
        user_client, "ensure_authenticated", AsyncMock(return_value=True)
    ):
        stats = await user_client.get_user_stats()

    assert isinstance(stats, UserStats)
    assert stats.movies is not None and stats.movies.minutes == 79230
    assert stats.ratings is not None and stats.ratings.distribution is not None
    assert stats.ratings.distribution["8"] == 260
    assert seen[0].url.path == "/users/me/stats"


@pytest.mark.asyncio
async def test_get_user_stats_partial(
    user_client: UserClient, user_stats_partial: dict[str, Any]
) -> None:
    _serve(user_client, httpx.Response(200, json=user_stats_partial))
    with patch.object(
        user_client, "ensure_authenticated", AsyncMock(return_value=True)
    ):
        stats = await user_client.get_user_stats()

    assert isinstance(stats, UserStats)
    assert stats.episodes is None
    assert stats.total_minutes is None


@pytest.mark.asyncio
async def test_get_user_stats_204_is_none(user_client: UserClient) -> None:
    _serve(user_client, httpx.Response(204))
    with patch.object(
        user_client, "ensure_authenticated", AsyncMock(return_value=True)
    ):
        assert await user_client.get_user_stats() is None


@pytest.mark.asyncio
async def test_get_user_stats_empty_200_body_is_none(user_client: UserClient) -> None:
    _serve(user_client, httpx.Response(200, content=b""))
    with patch.object(
        user_client, "ensure_authenticated", AsyncMock(return_value=True)
    ):
        assert await user_client.get_user_stats() is None


@pytest.mark.asyncio
async def test_get_user_stats_requires_auth(user_client: UserClient) -> None:
    with (
        patch.object(
            user_client, "ensure_authenticated", AsyncMock(return_value=False)
        ),
        pytest.raises(AuthenticationRequiredError),
    ):
        await user_client.get_user_stats()


@pytest.mark.asyncio
async def test_make_request_still_fails_on_204_by_default(
    user_client: UserClient,
) -> None:
    """Other callers keep today's behaviour: an empty body is a decode error."""
    _serve(user_client, httpx.Response(204))
    with pytest.raises(Exception):  # noqa: B017
        await user_client._make_request("GET", "/anything")
