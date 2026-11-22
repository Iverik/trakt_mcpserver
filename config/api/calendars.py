"""Calendar API constants."""

from typing import Final

CALENDAR_DEFAULT_DAYS: Final[int] = 7  # Trakt default when days is omitted
CALENDAR_MAX_DAYS: Final[int] = 33  # Trakt rejects larger windows
