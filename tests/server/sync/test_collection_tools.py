"""Tests for the fetch_user_collection tool in server.sync.tools."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from models.sync.collection import (
    CollectionFetchResult,
    CollectionItem,
    CollectionMovie,
)
from models.types.ids import TraktIds
from server.sync.tools import fetch_user_collection, register_sync_tools


@pytest.mark.asyncio
async def test_fetch_user_collection_formats_result() -> None:
    """The tool passes its arguments to the client and formats the result."""
    item = CollectionItem(
        movie=CollectionMovie(title="Inception", year=2010, ids=TraktIds(trakt=1)),
        collected_at=datetime.fromisoformat("2024-01-15T10:30:00+00:00"),
    )
    with patch("server.sync.tools.SyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.get_collection = AsyncMock(
            return_value=CollectionFetchResult(items=[item], pages_fetched=1)
        )

        output = await fetch_user_collection("movies", include_metadata=True)

    mock_client.get_collection.assert_awaited_once_with("movies", True)
    assert "Total: 1 movie" in output
    assert "- Inception (2010), collected 2024-01-15" in output


@pytest.mark.asyncio
async def test_fetch_user_collection_is_registered_read_only() -> None:
    """The tool is registered with the expected inputs and no write tools exist."""
    mcp = FastMCP("test")
    register_sync_tools(mcp)

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert "fetch_user_collection" in tools
    schema = json.loads(json.dumps(tools["fetch_user_collection"].inputSchema))
    assert set(schema["properties"]) == {"collection_type", "include_metadata"}
    assert schema["required"] == ["collection_type"]
    assert not [
        name
        for name in tools
        if "collection" in name and name.startswith(("add_", "remove_"))
    ]
