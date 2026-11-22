"""Tests that the personal list tools register with the MCP server."""

import pytest
from mcp.server.fastmcp import FastMCP

from config.mcp.tools import LISTS_TOOLS
from server.lists import register_lists_tools


@pytest.mark.asyncio
async def test_registers_every_list_tool_with_described_parameters() -> None:
    mcp = FastMCP(name="test")
    register_lists_tools(mcp)

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert set(tools) == LISTS_TOOLS
    for name in ("add_user_list_items", "remove_user_list_items"):
        props = tools[name].inputSchema["properties"]
        schema = tools[name].inputSchema
        assert schema["$defs"]["ListItemType"]["enum"] == ["movies", "shows"]
        assert props["list_id"]["description"]
        assert props["items"]["description"]
    create = tools["create_user_list"].inputSchema
    assert create["$defs"]["ListPrivacy"]["enum"] == [
        "private",
        "link",
        "friends",
        "public",
    ]
    assert create["required"] == ["name"]
