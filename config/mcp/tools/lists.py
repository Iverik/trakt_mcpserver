"""Personal list MCP tool name definitions (user data requiring OAuth)."""

from typing import Final

LISTS_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "fetch_user_lists",
        "create_user_list",
        "fetch_user_list_items",
        "add_user_list_items",
        "remove_user_list_items",
    }
)
