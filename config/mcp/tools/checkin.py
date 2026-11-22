"""Check-in specific MCP tool name definitions."""

from typing import Final

CHECKIN_TOOLS: Final[frozenset[str]] = frozenset(
    {"checkin_to_show", "checkin_to_movie", "cancel_checkin"}
)
