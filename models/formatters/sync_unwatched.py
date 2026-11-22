"""Formatting for the unwatched-in-collection list."""

from typing import Final

from models.formatters.utils import format_title_year
from models.sync.collection import CollectionItem
from models.sync.unwatched import UnwatchedSelection

RESOLUTION_LABELS: Final[dict[str, str]] = {
    "uhd_4k": "4K",
    "hd_1080p": "1080p",
    "hd_1080i": "1080i",
    "hd_720p": "720p",
    "sd_576p": "576p",
    "sd_576i": "576i",
    "sd_480p": "480p",
    "sd_480i": "480i",
}
UNKNOWN_VALUE: Final[str] = "-"
MINUTES_PER_HOUR: Final[int] = 60


class SyncUnwatchedFormatters:
    """Helper class for formatting the unwatched collection list."""

    @staticmethod
    def format_unwatched(selection: UnwatchedSelection) -> str:
        """Format counts, then one line per film.

        Args:
            selection: Counts and the films chosen to show

        Returns:
            Markdown with a counts header and one pipe-separated line per film
        """
        lines: list[str] = [
            "# Unwatched in your collection (movies)",
            "",
            f"Collected: {selection.collected} | Watched: {selection.watched} | "
            + f"Unwatched matching filters: {selection.matching} | "
            + f"Shown: {len(selection.items)}",
        ]
        if selection.items:
            lines.append("")
            lines.extend(
                SyncUnwatchedFormatters._format_item(item) for item in selection.items
            )
        return "\n".join(lines)

    @staticmethod
    def format_runtime(minutes: int | None) -> str:
        """Format minutes as ``1h 52m``, ``2h`` or ``45m``."""
        if minutes is None:
            return UNKNOWN_VALUE
        hours, remainder = divmod(minutes, MINUTES_PER_HOUR)
        if hours == 0:
            return f"{remainder}m"
        return f"{hours}h" if remainder == 0 else f"{hours}h {remainder}m"

    @staticmethod
    def _format_item(item: CollectionItem) -> str:
        movie = item.movie
        if movie is None:
            return UNKNOWN_VALUE
        genres = ", ".join(movie.genres) if movie.genres else UNKNOWN_VALUE
        rating = f"{movie.rating:.1f}" if movie.rating is not None else UNKNOWN_VALUE
        parts = [
            format_title_year(movie.title, movie.year),
            SyncUnwatchedFormatters.format_runtime(movie.runtime),
            genres,
            rating,
        ]
        resolution = item.metadata.resolution if item.metadata else None
        if resolution:
            parts.append(RESOLUTION_LABELS.get(resolution, resolution))
        return " | ".join(parts)
