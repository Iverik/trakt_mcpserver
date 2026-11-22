"""User formatting methods for the Trakt MCP server."""

from typing import Final

from ..types import UserWatchedMovie, UserWatchedShow
from ..user.stats import UserStats

NO_STATS_MESSAGE: Final[str] = (
    "Trakt returned no stats for this account (204 No Content). "
    "Trakt only precomputes stats for some accounts (VIP)."
)


def _hours(minutes: int) -> str:
    return f"{minutes / 60:,.1f} h"


def _count(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:g}"


class UserFormatters:
    """Helper class for formatting user-related data for MCP responses."""

    @staticmethod
    def format_user_watched_shows(shows: list[UserWatchedShow]) -> str:
        """Format user watched shows data for MCP resource."""
        lines: list[str] = ["# Your Watched Shows on Trakt"]
        lines.append("")

        if not shows:
            lines.append(
                "You haven't watched any shows yet, or you need to authenticate first."
            )
            return "\n".join(lines)

        for item in shows:
            show = item.get("show", {})
            last_watched = item.get("last_watched_at", "Unknown")
            plays = item.get("plays", 0)

            title = show.get("title", "Unknown")
            year = show.get("year", "")
            year_str = f" ({year})" if year else ""

            lines.append(
                f"- **{title}{year_str}** - Watched: {last_watched}, Plays: {plays}"
            )

            if overview := show.get("overview"):
                lines.append(f"  {overview}")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def format_user_watched_movies(movies: list[UserWatchedMovie]) -> str:
        """Format user watched movies data for MCP resource."""
        lines: list[str] = ["# Your Watched Movies on Trakt"]
        lines.append("")

        if not movies:
            lines.append(
                "You haven't watched any movies yet, or you need to authenticate first."
            )
            return "\n".join(lines)

        for item in movies:
            movie = item.get("movie", {})
            last_watched = item.get("last_watched_at", "Unknown")
            plays = item.get("plays", 0)

            title = movie.get("title", "Unknown")
            year = movie.get("year", "")
            year_str = f" ({year})" if year else ""

            lines.append(
                f"- **{title}{year_str}** - Watched: {last_watched}, Plays: {plays}"
            )

            if overview := movie.get("overview"):
                lines.append(f"  {overview}")

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def format_user_stats(stats: UserStats | None) -> str:
        """Format user stats as a compact markdown summary."""
        lines: list[str] = ["# Your Trakt Stats", ""]
        if stats is None:
            lines.append(NO_STATS_MESSAGE)
            return "\n".join(lines)

        if stats.total_minutes is not None or stats.total_plays is not None:
            parts: list[str] = []
            if stats.total_plays is not None:
                parts.append(f"{stats.total_plays:,} plays")
            if stats.total_minutes is not None:
                parts.append(_hours(stats.total_minutes))
            lines.append(f"**Total:** {', '.join(parts)}")
            lines.append("")

        for label, section in (("Movies", stats.movies), ("Episodes", stats.episodes)):
            if section is None:
                continue
            parts = []
            if section.watched is not None:
                parts.append(f"{section.watched:,} watched")
            if section.plays is not None:
                parts.append(f"{section.plays:,} plays")
            if section.minutes is not None:
                parts.append(_hours(section.minutes))
            if section.collected is not None:
                parts.append(f"{section.collected:,} collected")
            if section.ratings is not None:
                parts.append(f"{section.ratings:,} rated")
            if section.comments is not None:
                parts.append(f"{section.comments:,} comments")
            if parts:
                lines.append(f"- **{label}:** {', '.join(parts)}")

        if stats.shows is not None:
            parts = []
            if stats.shows.watched is not None:
                parts.append(f"{stats.shows.watched:,} watched")
            if stats.shows.collected is not None:
                parts.append(f"{stats.shows.collected:,} collected")
            if stats.shows.ratings is not None:
                parts.append(f"{stats.shows.ratings:,} rated")
            if stats.shows.comments is not None:
                parts.append(f"{stats.shows.comments:,} comments")
            if parts:
                lines.append(f"- **Shows:** {', '.join(parts)}")

        if stats.seasons is not None:
            parts = []
            if stats.seasons.ratings is not None:
                parts.append(f"{stats.seasons.ratings:,} rated")
            if stats.seasons.comments is not None:
                parts.append(f"{stats.seasons.comments:,} comments")
            if parts:
                lines.append(f"- **Seasons:** {', '.join(parts)}")

        if stats.network is not None:
            parts = []
            for name, value in (
                ("friends", stats.network.friends),
                ("followers", stats.network.followers),
                ("following", stats.network.following),
            ):
                if value is not None:
                    parts.append(f"{value:,} {name}")
            if parts:
                lines.append(f"- **Network:** {', '.join(parts)}")

        if stats.progress is not None:
            parts = []
            for name, value in (
                ("started", stats.progress.started),
                ("finished", stats.progress.finished),
                ("dropped", stats.progress.dropped),
            ):
                if value is not None:
                    parts.append(f"{value:,} {name}")
            if parts:
                lines.append(f"- **Show progress:** {', '.join(parts)}")

        if stats.ratings is not None:
            lines.append("")
            total = stats.ratings.total
            lines.append(
                "## Ratings" + (f" ({total:,} total)" if total is not None else "")
            )
            distribution = stats.ratings.distribution or {}
            ordered = sorted(distribution, key=lambda k: int(k) if k.isdigit() else 0)
            lines.extend(f"- {key}: {_count(distribution[key])}" for key in ordered)

        return "\n".join(lines)
