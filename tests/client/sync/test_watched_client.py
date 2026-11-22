# pyright: reportPrivateUsage=false
"""Tests for the client.sync.watched_client module."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

import client.sync.all_pages_client as all_pages_module
from client.sync.client import SyncClient
from models.sync.watched import WatchedMovieItem
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import InternalError

TOTAL_WATCHED = 549


def _watched(index: int) -> dict[str, Any]:
    return {
        "plays": 1 + index % 3,
        "last_watched_at": "2024-03-01T20:00:00.000Z",
        "last_updated_at": "2024-03-01T20:00:00.000Z",
        "movie": {
            "title": f"Movie {index}",
            "year": 2000 + index % 20,
            "ids": {"trakt": index + 1, "slug": f"movie-{index}"},
        },
    }


def _paged_handler(
    total: int, seen: list[httpx.Request]
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params.get("page", "1"))
        limit = int(request.url.params.get("limit", "10"))
        start = (page - 1) * limit
        body = [_watched(i) for i in range(start, min(start + limit, total))]
        headers = {
            "X-Pagination-Page": str(page),
            "X-Pagination-Limit": str(limit),
            "X-Pagination-Page-Count": str(-(-total // limit)),
            "X-Pagination-Item-Count": str(total),
        }
        return httpx.Response(200, json=body, headers=headers)

    return handler


def _client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    authenticated: bool = True,
) -> SyncClient:
    monkeypatch.setenv("TRAKT_CLIENT_ID", "test_client_id")
    client = SyncClient()
    client.ensure_authenticated = AsyncMock(return_value=authenticated)
    client._client = httpx.AsyncClient(
        base_url=client.BASE_URL, transport=httpx.MockTransport(handler)
    )
    return client


class TestGetWatchedMovies:
    """Tests for SyncWatchedClient.get_watched_movies."""

    @pytest.mark.asyncio
    async def test_follows_every_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[httpx.Request] = []
        client = _client(monkeypatch, _paged_handler(TOTAL_WATCHED, seen))

        result = await client.get_watched_movies()

        assert isinstance(result, list)
        assert len(result) == TOTAL_WATCHED
        assert all(isinstance(item, WatchedMovieItem) for item in result)
        assert [r.url.params["page"] for r in seen] == ["1", "2", "3"]
        assert all(r.url.path == "/sync/watched/movies" for r in seen)
        assert all(r.url.params["limit"] == "250" for r in seen)
        assert result[0].plays == 1
        assert result[0].movie.ids.trakt == 1

    @pytest.mark.asyncio
    async def test_page_guard_raises_instead_of_returning_a_partial_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(all_pages_module, "MAX_COLLECTION_PAGES", 1)
        client = _client(monkeypatch, _paged_handler(TOTAL_WATCHED, []))

        with pytest.raises(InternalError, match="incomplete"):
            await client.get_watched_movies()

    @pytest.mark.asyncio
    async def test_requires_authentication(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(monkeypatch, _paged_handler(1, []), authenticated=False)

        with pytest.raises(AuthenticationRequiredError):
            await client.get_watched_movies()
