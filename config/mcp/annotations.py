"""MCP tool annotation presets shared by every registered tool."""

from typing import Final

from mcp.types import ToolAnnotations

# Every tool calls the Trakt API, so every preset is open-world.

# Reads only: no Trakt or local state changes.
READ_ONLY: Final[ToolAnnotations] = ToolAnnotations(
    readOnlyHint=True,
    openWorldHint=True,
)

# Writes that only add or change state (history, ratings, lists, check-ins,
# hidden recommendations, device-auth sign-in). Nothing is removed.
WRITE: Final[ToolAnnotations] = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    openWorldHint=True,
)

# Removals and other state-destroying calls. Repeating one changes nothing more.
DESTRUCTIVE: Final[ToolAnnotations] = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=True,
)

__all__ = ["DESTRUCTIVE", "READ_ONLY", "WRITE"]
