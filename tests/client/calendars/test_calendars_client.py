"""Tests for the calendars client."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from client.calendars import CalendarsClient
from models.calendars.calendar import CalendarKind
from utils.api.error_types import AuthenticationRequiredError

SHOW_ENTRY: dict[str, Any] = {
    "first_aired": "2026-11-23T01:00:00.000Z",
    "episode": {"season": 1, "number": 2, "title": "Pilot", "ids": {"trakt": 5}},
    "show": {
        "title": "Show A",
        "year": 2026,
        "network": "HBO",
        "ids": {"trakt": 1, "slug": "show-a"},
    },
}
MOVIE_ENTRY: dict[str, Any] = {
    "released": "2026-11-25",
    "movie": {"title": "Movie A", "year": 2026, "ids": {"trakt": 9, "slug": "m"}},
}


def _respond(client_mock: MagicMock, payload: list[dict[str, Any]]) -> None:
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status = MagicMock()
    client_mock.get.return_value = response


SHOW_PATHS: list[tuple[CalendarKind, str]] = [
    ("shows", "/calendars/my/shows/2026-11-22/7"),
    ("new_shows", "/calendars/my/shows/new/2026-11-22/7"),
    ("premieres", "/calendars/my/shows/premieres/2026-11-22/7"),
    ("finales", "/calendars/my/shows/finales/2026-11-22/7"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "path"), SHOW_PATHS)
async def test_show_calendar_variants(
    patched_httpx_client: MagicMock,
    authenticated_client: CalendarsClient,
    kind: CalendarKind,
    path: str,
) -> None:
    """Each show variant hits its own endpoint and parses the entries."""
    _respond(patched_httpx_client, [SHOW_ENTRY])

    result = await authenticated_client.get_my_show_calendar(kind, "2026-11-22", 7)
    assert not isinstance(result, str)

    assert len(result) == 1
    assert result[0].show.network == "HBO"
    assert result[0].episode.number == 2
    call = patched_httpx_client.get.call_args
    assert call[0][0].endswith(path)
    assert call[1]["params"] == {"extended": "full"}


@pytest.mark.asyncio
async def test_movie_calendar(
    patched_httpx_client: MagicMock,
    authenticated_client: CalendarsClient,
) -> None:
    """The movie calendar hits /calendars/my/movies and parses releases."""
    _respond(patched_httpx_client, [MOVIE_ENTRY])

    result = await authenticated_client.get_my_movie_calendar("2026-11-22", 14)
    assert not isinstance(result, str)

    assert result[0].movie.title == "Movie A"
    assert result[0].released.isoformat() == "2026-11-25"
    call = patched_httpx_client.get.call_args
    assert call[0][0].endswith("/calendars/my/movies/2026-11-22/14")


@pytest.mark.asyncio
async def test_empty_calendar(
    patched_httpx_client: MagicMock,
    authenticated_client: CalendarsClient,
) -> None:
    """An empty response yields an empty list."""
    _respond(patched_httpx_client, [])

    result = await authenticated_client.get_my_show_calendar("shows", "2026-11-22", 7)

    assert result == []


@pytest.mark.asyncio
async def test_show_calendar_rejects_movies_kind(
    authenticated_client: CalendarsClient,
) -> None:
    """The show client refuses the movies kind."""
    with pytest.raises(ValueError, match="Not a show calendar"):
        await authenticated_client.get_my_show_calendar("movies", "2026-11-22", 7)


@pytest.mark.asyncio
async def test_calendars_require_authentication() -> None:
    """Both calendar calls require authentication."""
    client = CalendarsClient()
    client.ensure_authenticated = AsyncMock(return_value=False)
    with pytest.raises(AuthenticationRequiredError):
        await client.get_my_show_calendar("shows", "2026-11-22", 7)
    with pytest.raises(AuthenticationRequiredError):
        await client.get_my_movie_calendar("2026-11-22", 7)
