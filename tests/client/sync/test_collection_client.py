# pyright: reportPrivateUsage=false
"""Tests for the client.sync.collection_client module."""

from collections.abc import Callable
from typing import Any, Literal
from unittest.mock import AsyncMock

import httpx
import pytest

import client.sync.all_pages_client as collection_module
from client.sync.client import SyncClient
from client.sync.collection_client import SyncCollectionClient
from models.sync.collection import CollectionFetchResult
from utils.api.error_types import AuthenticationRequiredError

TOTAL_MOVIES = 600


def _movie(index: int, *, metadata: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {
        "collected_at": "2024-01-15T10:30:00.000Z",
        "updated_at": "2024-01-15T10:30:00.000Z",
        "movie": {
            "title": f"Movie {index}",
            "year": 2000 + index % 20,
            "ids": {"trakt": index + 1, "slug": f"movie-{index}"},
        },
    }
    if metadata:
        item["metadata"] = {
            "media_type": "bluray",
            "resolution": "uhd_4k",
            "hdr": "dolby_vision",
            "audio": "dolby_atmos",
            "audio_channels": "7.1",
            "3d": False,
        }
    return item


def _show() -> dict[str, Any]:
    return {
        "last_collected_at": "2024-02-01T00:00:00.000Z",
        "last_updated_at": "2024-02-01T00:00:00.000Z",
        "show": {
            "title": "Breaking Bad",
            "year": 2008,
            "ids": {"trakt": 1, "slug": "breaking-bad"},
        },
        "seasons": [
            {
                "number": 1,
                "episodes": [
                    {
                        "number": 1,
                        "collected_at": "2024-02-01T00:00:00.000Z",
                        "metadata": {"resolution": "hd_1080p", "audio": "aac"},
                    },
                    {"number": 2, "collected_at": "2024-02-01T00:00:00.000Z"},
                ],
            },
            {
                "number": 2,
                "episodes": [{"number": 1, "collected_at": "2024-02-02T00:00:00.000Z"}],
            },
        ],
    }


def _paged_handler(
    total: int, seen: list[httpx.Request], *, headers: bool = True
) -> Callable[[httpx.Request], httpx.Response]:
    """Serve `total` movies in pages of the requested limit."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        page = int(request.url.params.get("page", "1"))
        limit = int(request.url.params.get("limit", "10"))
        start = (page - 1) * limit
        body = [
            _movie(i, metadata="extended" in request.url.params)
            for i in range(start, min(start + limit, total))
        ]
        response_headers: dict[str, str] = {}
        if headers:
            response_headers = {
                "X-Pagination-Page": str(page),
                "X-Pagination-Limit": str(limit),
                "X-Pagination-Page-Count": str(-(-total // limit)),
                "X-Pagination-Item-Count": str(total),
            }
        return httpx.Response(200, json=body, headers=response_headers)

    return handler


def _client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    authenticated: bool = True,
) -> SyncCollectionClient:
    monkeypatch.setenv("TRAKT_CLIENT_ID", "test_client_id")
    client = SyncClient()
    client.ensure_authenticated = AsyncMock(return_value=authenticated)
    client._client = httpx.AsyncClient(
        base_url=client.BASE_URL, transport=httpx.MockTransport(handler)
    )
    return client


async def _fetch(
    client: SyncCollectionClient,
    collection_type: Literal["movies", "shows"] = "movies",
    *,
    include_metadata: bool = False,
) -> CollectionFetchResult:
    result = await client.get_collection(collection_type, include_metadata)
    assert isinstance(result, CollectionFetchResult)
    return result


class TestGetCollection:
    """Tests for SyncCollectionClient.get_collection."""

    @pytest.mark.asyncio
    async def test_fetches_every_page_past_the_safety_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Items beyond the page size are returned: the fetch-all cap does not apply."""
        seen: list[httpx.Request] = []
        client = _client(monkeypatch, _paged_handler(TOTAL_MOVIES, seen))

        result = await _fetch(client, "movies")

        assert len(result.items) == TOTAL_MOVIES
        assert result.pages_fetched == 3
        assert result.truncated is False
        titles = [item.movie.title for item in result.items if item.movie]
        assert titles[250] == "Movie 250"
        assert titles[-1] == f"Movie {TOTAL_MOVIES - 1}"
        assert [r.url.params["page"] for r in seen] == ["1", "2", "3"]
        assert all(r.url.path == "/sync/collection/movies" for r in seen)
        assert all(r.url.params["limit"] == "250" for r in seen)
        assert all("extended" not in r.url.params for r in seen)

    @pytest.mark.asyncio
    async def test_no_pagination_headers_is_one_complete_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A response without X-Pagination headers is a single page."""
        seen: list[httpx.Request] = []
        client = _client(monkeypatch, _paged_handler(7, seen, headers=False))

        result = await _fetch(client, "movies")

        assert len(result.items) == 7
        assert result.pages_fetched == 1
        assert result.truncated is False
        assert len(seen) == 1

    @pytest.mark.asyncio
    async def test_empty_collection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty collection returns no items and one page read."""
        client = _client(monkeypatch, _paged_handler(0, [], headers=False))

        result = await _fetch(client, "movies")

        assert result.items == []
        assert result.pages_fetched == 1

    @pytest.mark.asyncio
    async def test_metadata_flag_sends_extended_and_parses_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """include_metadata sends extended=metadata and parses every field."""
        seen: list[httpx.Request] = []
        client = _client(monkeypatch, _paged_handler(2, seen))

        result = await _fetch(client, "movies", include_metadata=True)

        assert seen[0].url.params["extended"] == "metadata"
        metadata = result.items[0].metadata
        assert metadata is not None
        assert metadata.media_type == "bluray"
        assert metadata.resolution == "uhd_4k"
        assert metadata.hdr == "dolby_vision"
        assert metadata.audio == "dolby_atmos"
        assert metadata.audio_channels == "7.1"
        assert metadata.three_d is False

    @pytest.mark.asyncio
    async def test_details_flag_sends_extended_full(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """include_details sends extended=full, combined with metadata."""
        seen: list[httpx.Request] = []
        client = _client(monkeypatch, _paged_handler(2, seen))

        await client.get_collection("movies", include_details=True)
        await client.get_collection("movies", True, True)

        assert seen[0].url.params["extended"] == "full"
        assert seen[1].url.params["extended"] == "full,metadata"

    @pytest.mark.asyncio
    async def test_metadata_is_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Items without metadata parse with metadata unset."""
        client = _client(monkeypatch, _paged_handler(2, []))

        result = await _fetch(client, "movies")

        assert all(item.metadata is None for item in result.items)

    @pytest.mark.asyncio
    async def test_shows_parse_nested_seasons_and_episodes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Shows keep season and episode nesting, with per-episode metadata."""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=[_show()])

        client = _client(monkeypatch, handler)

        result = await _fetch(client, "shows", include_metadata=True)

        assert seen[0].url.path == "/sync/collection/shows"
        item = result.items[0]
        assert item.show is not None
        assert item.show.title == "Breaking Bad"
        assert item.seasons is not None
        assert [len(season.episodes) for season in item.seasons] == [2, 1]
        assert item.collected_episode_count == 3
        episode_metadata = item.seasons[0].episodes[0].metadata
        assert episode_metadata is not None
        assert episode_metadata.resolution == "hd_1080p"
        assert item.seasons[0].episodes[1].metadata is None

    @pytest.mark.asyncio
    async def test_page_guard_reports_truncation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Hitting the page-count guard flags the result instead of hiding it."""
        monkeypatch.setattr(collection_module, "MAX_COLLECTION_PAGES", 2)
        seen: list[httpx.Request] = []
        client = _client(monkeypatch, _paged_handler(TOTAL_MOVIES, seen))

        result = await _fetch(client, "movies")

        assert result.truncated is True
        assert result.pages_fetched == 2
        assert len(result.items) == 500
        assert len(seen) == 2

    @pytest.mark.asyncio
    async def test_requires_authentication(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unauthenticated callers get AuthenticationRequiredError."""
        client = _client(monkeypatch, _paged_handler(1, []), authenticated=False)

        with pytest.raises(AuthenticationRequiredError):
            await client.get_collection("movies")
