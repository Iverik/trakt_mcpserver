"""Formatters for calendar data."""

from collections import defaultdict
from datetime import date, timedelta

from models.calendars.calendar import (
    CalendarKind,
    CalendarMovieEntry,
    CalendarShowEntry,
)

CALENDAR_TITLES: dict[CalendarKind, str] = {
    "shows": "Shows",
    "new_shows": "New Shows",
    "premieres": "Premieres",
    "finales": "Finales",
    "movies": "Movies",
}


class CalendarFormatters:
    """Helper class for formatting calendar data for MCP responses."""

    @staticmethod
    def _header(
        kind: CalendarKind,
        start_date: date,
        days: int,
        clamped_from: int | None,
    ) -> list[str]:
        end_date = start_date + timedelta(days=days - 1)
        window = f"{start_date.isoformat()} to {end_date.isoformat()}"
        lines = [
            f"# My Calendar: {CALENDAR_TITLES[kind]}",
            "",
            f"_{window} ({days} days). All dates and times are UTC._",
            "",
        ]
        if clamped_from is not None:
            note = f"_Note: requested {clamped_from} days, reduced to max {days}._"
            lines.extend([note, ""])
        return lines

    @staticmethod
    def _show_line(entry: CalendarShowEntry) -> str:
        episode = entry.episode
        code = f"S{episode.season:02d}E{episode.number:02d}"
        title = f' "{episode.title}"' if episode.title else ""
        meta = entry.first_aired.strftime("%H:%M UTC")
        if entry.show.network:
            meta = f"{entry.show.network}, {meta}"
        return f"- **{entry.show.title}** {code}{title} ({meta})"

    @staticmethod
    def _movie_line(entry: CalendarMovieEntry) -> str:
        year = f" ({entry.movie.year})" if entry.movie.year else ""
        return f"- {entry.movie.title}{year}"

    @staticmethod
    def format_show_calendar(
        kind: CalendarKind,
        entries: list[CalendarShowEntry],
        start_date: date,
        days: int,
        clamped_from: int | None = None,
    ) -> str:
        """Format a show calendar grouped by UTC air date.

        Args:
            kind: Which show calendar this is.
            entries: Calendar entries from the API.
            start_date: First day of the window.
            days: Number of days actually requested.
            clamped_from: The originally requested days, when it was reduced.

        Returns:
            Formatted markdown text.
        """
        lines = CalendarFormatters._header(kind, start_date, days, clamped_from)
        if not entries:
            lines.append("Nothing scheduled in this period.")
            return "\n".join(lines)

        by_day: dict[date, list[CalendarShowEntry]] = defaultdict(list)
        for entry in sorted(entries, key=lambda item: item.first_aired):
            by_day[entry.first_aired.date()].append(entry)
        for day, day_entries in sorted(by_day.items()):
            lines.append(f"## {day.isoformat()}")
            lines.extend(CalendarFormatters._show_line(e) for e in day_entries)
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def format_movie_calendar(
        entries: list[CalendarMovieEntry],
        start_date: date,
        days: int,
        clamped_from: int | None = None,
    ) -> str:
        """Format the movie calendar grouped by release date.

        Args:
            entries: Calendar entries from the API.
            start_date: First day of the window.
            days: Number of days actually requested.
            clamped_from: The originally requested days, when it was reduced.

        Returns:
            Formatted markdown text.
        """
        lines = CalendarFormatters._header(
            kind="movies", start_date=start_date, days=days, clamped_from=clamped_from
        )
        if not entries:
            lines.append("Nothing scheduled in this period.")
            return "\n".join(lines)

        by_day: dict[date, list[CalendarMovieEntry]] = defaultdict(list)
        for entry in sorted(
            entries, key=lambda item: (item.released, item.movie.title)
        ):
            by_day[entry.released].append(entry)
        for day, day_entries in sorted(by_day.items()):
            lines.append(f"## {day.isoformat()}")
            lines.extend(CalendarFormatters._movie_line(e) for e in day_entries)
            lines.append("")
        return "\n".join(lines)
