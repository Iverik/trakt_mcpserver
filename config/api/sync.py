"""Sync API constants for the Trakt MCP server."""

from typing import Final

# Rating constants
RATING_MIN: Final[int] = 1
RATING_MAX: Final[int] = 10

# Valid rating types
RATING_TYPES: Final[tuple[str, ...]] = ("movies", "shows", "seasons", "episodes")

# Number of most recent ratings shown in a ratings summary
RATINGS_SUMMARY_RECENT_COUNT: Final[int] = 20
