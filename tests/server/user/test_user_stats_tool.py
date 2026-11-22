"""Tests for the fetch_user_stats tool."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from models.user.stats import UserStats
from server.user.tools import fetch_user_stats, register_user_tools
from utils.api.error_types import AuthenticationRequiredError


@pytest.mark.asyncio
async def test_fetch_user_stats_full(user_stats_full: dict[str, Any]) -> None:
    with patch("server.user.tools.UserClient") as mock_class:
        client = mock_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.get_user_stats = AsyncMock(
            return_value=UserStats.model_validate(user_stats_full)
        )

        result = await fetch_user_stats()

    assert "# Your Trakt Stats" in result
    assert "549 watched" in result
    assert "## Ratings (803 total)" in result


@pytest.mark.asyncio
async def test_fetch_user_stats_partial(user_stats_partial: dict[str, Any]) -> None:
    with patch("server.user.tools.UserClient") as mock_class:
        client = mock_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.get_user_stats = AsyncMock(
            return_value=UserStats.model_validate(user_stats_partial)
        )

        result = await fetch_user_stats()

    assert "10 watched" in result


@pytest.mark.asyncio
async def test_fetch_user_stats_204_is_a_result_not_an_error() -> None:
    with patch("server.user.tools.UserClient") as mock_class:
        client = mock_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.get_user_stats = AsyncMock(return_value=None)

        result = await fetch_user_stats()

    assert "Trakt returned no stats for this account (204 No Content)" in result


@pytest.mark.asyncio
async def test_fetch_user_stats_requires_auth() -> None:
    with patch("server.user.tools.UserClient") as mock_class:
        client = mock_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=False)

        with pytest.raises(AuthenticationRequiredError):
            await fetch_user_stats()


@pytest.mark.asyncio
async def test_fetch_user_stats_tool_registered_without_parameters() -> None:
    mcp = FastMCP(name="test")
    register_user_tools(mcp)

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert "fetch_user_stats" in tools
    assert tools["fetch_user_stats"].inputSchema.get("properties", {}) == {}
