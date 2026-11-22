"""Every registered tool must say whether it reads, writes or destroys."""

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from config.mcp.annotations import DESTRUCTIVE, READ_ONLY, WRITE
from server.main import create_server

# Tools whose names do not follow a prefix rule must be classified here, so a
# new tool without a classification fails test_every_tool_is_classified.
EXPLICIT: dict[str, ToolAnnotations] = {
    "unwatched_in_collection": READ_ONLY,
    "have_i_seen": READ_ONLY,
    "start_device_auth": WRITE,
    "check_auth_status": WRITE,
    "create_user_list": WRITE,
    "add_user_list_items": WRITE,
    "add_user_ratings": WRITE,
    "add_user_watchlist": WRITE,
    "add_to_history": WRITE,
    "hide_movie_recommendation": WRITE,
    "hide_show_recommendation": WRITE,
    "unhide_movie_recommendation": WRITE,
    "unhide_show_recommendation": WRITE,
    "checkin_to_show": WRITE,
    "checkin_to_movie": WRITE,
}
PREFIX_RULES: tuple[tuple[tuple[str, ...], ToolAnnotations], ...] = (
    (("remove_", "clear_", "cancel_"), DESTRUCTIVE),
    (("fetch_", "search_"), READ_ONLY),
)


def expected_for(name: str) -> ToolAnnotations | None:
    for prefixes, preset in PREFIX_RULES:
        if name.startswith(prefixes):
            return preset
    return EXPLICIT.get(name)


@pytest.fixture(scope="module")
def server() -> FastMCP:
    return create_server()


@pytest.mark.asyncio
async def test_every_tool_has_explicit_annotations(server: FastMCP) -> None:
    tools = await server.list_tools()
    assert tools
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is not None, tool.name
        assert tool.annotations.openWorldHint is True, tool.name
        if tool.annotations.readOnlyHint is False:
            assert tool.annotations.destructiveHint is not None, tool.name


@pytest.mark.asyncio
async def test_every_tool_is_classified(server: FastMCP) -> None:
    unclassified = [
        tool.name
        for tool in await server.list_tools()
        if expected_for(tool.name) is None
    ]
    assert not unclassified, f"add these tools to EXPLICIT: {unclassified}"


@pytest.mark.asyncio
async def test_annotations_match_classification(server: FastMCP) -> None:
    for tool in await server.list_tools():
        assert tool.annotations == expected_for(tool.name), tool.name


@pytest.mark.asyncio
async def test_explicit_mapping_has_no_stale_names(server: FastMCP) -> None:
    names = {tool.name for tool in await server.list_tools()}
    assert set(EXPLICIT) <= names


@pytest.mark.asyncio
async def test_removal_prefixes_are_destructive(server: FastMCP) -> None:
    for tool in await server.list_tools():
        if tool.name.startswith(("remove_", "clear_", "cancel_")):
            assert tool.annotations is not None
            assert tool.annotations.destructiveHint is True, tool.name
            assert tool.annotations.readOnlyHint is False, tool.name
