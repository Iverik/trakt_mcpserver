"""Tests for the calendar tools."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from models.calendars.calendar import CalendarMovieEntry, CalendarShowEntry
from server.calendars.tools import fetch_my_calendar, register_calendar_tools

SHOW = CalendarShowEntry.model_validate(
    {
        "first_aired": "2026-11-23T01:00:00.000Z",
        "episode": {"season": 1, "number": 2, "title": "Pilot"},
        "show": {"title": "Show A", "network": "HBO", "ids": {"trakt": 1}},
    }
)
MOVIE = CalendarMovieEntry.model_validate(
    {"released": "2026-11-25", "movie": {"title": "Movie A", "year": 2026}}
)


def _patched_client(shows: Any = None, movies: Any = None) -> Any:
    mock_class = MagicMock()
    mock_class.return_value.get_my_show_calendar = AsyncMock(return_value=shows or [])
    mock_class.return_value.get_my_movie_calendar = AsyncMock(return_value=movies or [])
    return patch("server.calendars.tools.CalendarsClient", mock_class), mock_class


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["shows", "new_shows", "premieres", "finales"])
async def test_show_kinds(kind: str) -> None:
    """Show kinds call the show client with the chosen variant."""
    patcher, mock_class = _patched_client(shows=[SHOW])
    with patcher:
        result = await fetch_my_calendar(kind, "2026-11-22", 7)  # type: ignore[arg-type]

    mock_class.return_value.get_my_show_calendar.assert_awaited_once_with(
        kind, "2026-11-22", 7
    )
    assert '**Show A** S01E02 "Pilot" (HBO, 01:00 UTC)' in result


@pytest.mark.asyncio
async def test_movies_kind() -> None:
    """The movies kind calls the movie client."""
    patcher, mock_class = _patched_client(movies=[MOVIE])
    with patcher:
        result = await fetch_my_calendar("movies", "2026-11-22", 14)

    mock_class.return_value.get_my_movie_calendar.assert_awaited_once_with(
        "2026-11-22", 14
    )
    assert "- Movie A (2026)" in result


@pytest.mark.asyncio
async def test_days_clamped_to_max() -> None:
    """Days above the maximum are reduced, not rejected, and noted."""
    patcher, mock_class = _patched_client()
    with patcher:
        result = await fetch_my_calendar("shows", "2026-11-22", 90)

    mock_class.return_value.get_my_show_calendar.assert_awaited_once_with(
        "shows", "2026-11-22", 33
    )
    assert "requested 90 days, reduced to max 33" in result


@pytest.mark.asyncio
async def test_days_at_max_not_noted() -> None:
    """Exactly the maximum is not reported as clamped."""
    patcher, _ = _patched_client()
    with patcher:
        result = await fetch_my_calendar("movies", "2026-11-22", 33)

    assert "reduced" not in result


@pytest.mark.asyncio
async def test_start_date_defaults_to_today_utc() -> None:
    """Without start_date the current UTC day is used."""
    patcher, mock_class = _patched_client()
    today = datetime.now(UTC).date().isoformat()
    with patcher:
        await fetch_my_calendar("shows")

    args = mock_class.return_value.get_my_show_calendar.await_args.args
    assert args[1] == today
    assert args[2] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_date", ["22-11-2026", "2026/11/22", "20261122", "2026-13-45", "tomorrow"]
)
async def test_invalid_start_date(bad_date: str) -> None:
    """Malformed or impossible dates are rejected before any request."""
    patcher, mock_class = _patched_client()
    with patcher, pytest.raises(ValidationError):
        await fetch_my_calendar("shows", bad_date, 7)

    mock_class.return_value.get_my_show_calendar.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_days", [0, -3])
async def test_invalid_days(bad_days: int) -> None:
    """Days below 1 are rejected."""
    patcher, _ = _patched_client()
    with patcher, pytest.raises(ValidationError):
        await fetch_my_calendar("shows", "2026-11-22", bad_days)


@pytest.mark.asyncio
async def test_invalid_calendar_type() -> None:
    """An unknown calendar type is rejected."""
    patcher, _ = _patched_client()
    with patcher, pytest.raises(ValidationError):
        await fetch_my_calendar("streaming", "2026-11-22", 7)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_empty_results() -> None:
    """Empty calendars produce a clear message."""
    patcher, _ = _patched_client()
    with patcher:
        result = await fetch_my_calendar("movies", "2026-11-22", 7)

    assert "Nothing scheduled in this period." in result


@pytest.mark.asyncio
async def test_api_string_error_raises() -> None:
    """String results from the client become an error message, not a calendar."""
    patcher, _ = _patched_client(shows="boom")
    with patcher:
        result = await fetch_my_calendar("shows", "2026-11-22", 7)

    assert result.startswith("# Error")
    assert "# My Calendar" not in result


def test_register_calendar_tools() -> None:
    """The tool is registered under its name."""
    mock_mcp = MagicMock()

    handlers = register_calendar_tools(mock_mcp)

    assert len(handlers) == 1
    mock_mcp.tool.assert_called_once()
    assert mock_mcp.tool.call_args.kwargs["name"] == "fetch_my_calendar"
