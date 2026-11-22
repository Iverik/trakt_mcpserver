"""Tests for calendar formatters."""

from datetime import date

from models.calendars.calendar import CalendarMovieEntry, CalendarShowEntry
from models.formatters.calendars import CalendarFormatters


def _show(
    aired: str, season: int, number: int, title: str | None, network: str | None
) -> CalendarShowEntry:
    return CalendarShowEntry.model_validate(
        {
            "first_aired": aired,
            "episode": {"season": season, "number": number, "title": title},
            "show": {"title": "Show A", "network": network, "ids": {"trakt": 1}},
        }
    )


def test_show_calendar_grouped_by_utc_date() -> None:
    """Entries are grouped by UTC date, sorted, with UTC times."""
    entries = [
        _show("2026-11-23T20:30:00.000Z", 1, 2, "Second", "HBO"),
        _show("2026-11-22T21:00:00.000Z", 1, 1, "First", "HBO"),
        _show("2026-11-23T01:00:00.000Z", 3, 10, None, None),
    ]

    text = CalendarFormatters.format_show_calendar(
        "shows", entries, date(2026, 11, 22), 7
    )

    assert "# My Calendar: Shows" in text
    assert "2026-11-22 to 2026-11-28 (7 days)" in text
    assert "UTC" in text
    assert text.index("## 2026-11-22") < text.index("## 2026-11-23")
    assert '- **Show A** S01E01 "First" (HBO, 21:00 UTC)' in text
    assert "- **Show A** S03E10 (01:00 UTC)" in text
    assert text.index("S03E10") < text.index("S01E02")
    assert "reduced" not in text


def test_clamp_note_shown() -> None:
    """A clamped request is reported."""
    text = CalendarFormatters.format_show_calendar(
        "finales", [], date(2026, 11, 22), 33, clamped_from=100
    )

    assert "requested 100 days, reduced to max 33" in text
    assert "2026-11-22 to 2026-12-24" in text


def test_empty_calendars() -> None:
    """Empty results say so instead of printing nothing."""
    shows = CalendarFormatters.format_show_calendar(
        "premieres", [], date(2026, 11, 22), 7
    )
    movies = CalendarFormatters.format_movie_calendar([], date(2026, 11, 22), 7)

    assert "Nothing scheduled in this period." in shows
    assert "Nothing scheduled in this period." in movies


def test_movie_calendar() -> None:
    """Movies are grouped by release date, one line each."""
    entries = [
        CalendarMovieEntry.model_validate(
            {"released": "2026-11-25", "movie": {"title": "B Movie", "year": 2026}}
        ),
        CalendarMovieEntry.model_validate(
            {"released": "2026-11-24", "movie": {"title": "A Movie", "year": None}}
        ),
    ]

    text = CalendarFormatters.format_movie_calendar(entries, date(2026, 11, 22), 7)

    assert "# My Calendar: Movies" in text
    assert text.index("## 2026-11-24") < text.index("## 2026-11-25")
    assert "- A Movie\n" in text
    assert "- B Movie (2026)" in text
