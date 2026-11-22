"""Shared validation utilities for client modules."""

import re
from typing import Final

_IMDB_PATTERN: Final[re.Pattern[str]] = re.compile(r"^tt\d+$")


def validate_media_id(media_id: str, field_name: str = "id") -> str:
    """Strip and validate a media ID, returning the stripped value.

    Accepts the identifier types Trakt resolves in a path or ``ids.trakt``:
    - Trakt numeric ID (e.g. ``"12345"``)
    - Trakt slug (e.g. ``"tron-legacy-2010"``)
    - IMDB ID (format ``tt\\d+``, e.g. ``"tt1104001"``)

    Any all-digit value is treated as a Trakt ID, never as a TMDB or TVDB ID.

    Args:
        media_id: Trakt ID, slug, or IMDB ID
        field_name: Name of the field for error messages

    Returns:
        Stripped media_id

    Raises:
        ValueError: If media_id is empty or has an invalid IMDB format
    """
    media_id = media_id.strip()
    if not media_id:
        msg = f"{field_name} cannot be empty"
        raise ValueError(msg)

    if media_id.startswith("tt") and not _IMDB_PATTERN.match(media_id):
        msg = (
            f"Invalid IMDB ID format for {field_name}: '{media_id}'."
            " Expected format: tt followed by digits (e.g. tt1104001)"
        )
        raise ValueError(msg)

    return media_id
