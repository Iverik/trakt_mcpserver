"""TRAKT_MCP_READ_ONLY leaves out every tool that is not annotated read-only."""

import logging
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

import server.main as main_module
from server.main import create_server
from server.read_only import ReadOnlyFastMCP


@pytest.mark.asyncio
async def test_off_keeps_every_tool() -> None:
    names = {tool.name for tool in await create_server().list_tools()}
    assert {"add_to_history", "remove_from_history", "clear_auth"} <= names


@pytest.mark.asyncio
async def test_on_registers_only_read_only_tools() -> None:
    tools = await create_server(read_only=True).list_tools()
    assert tools
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is True, tool.name


@pytest.mark.asyncio
async def test_on_is_exactly_the_read_only_subset_of_off() -> None:
    full = await create_server().list_tools()
    expected = {
        tool.name
        for tool in full
        if tool.annotations is not None and tool.annotations.readOnlyHint is True
    }
    limited = {tool.name for tool in await create_server(read_only=True).list_tools()}
    assert limited == expected
    assert len(limited) < len(full)


@pytest.mark.asyncio
async def test_on_logs_skipped_count(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("trakt_mcp")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="trakt_mcp"):
            full = await create_server().list_tools()
            caplog.clear()
            limited = await create_server(read_only=True).list_tools()
    finally:
        logger.removeHandler(caplog.handler)
    skipped = len(full) - len(limited)
    messages = [record.getMessage() for record in caplog.records]
    expected = (
        f"Read-only mode (TRAKT_MCP_READ_ONLY): skipped {skipped} "
        "tools that are not read-only"
    )
    assert [m for m in messages if "Read-only mode" in m] == [expected]


def test_run_over_http_builds_a_read_only_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[bool] = []
    real_create = main_module.create_server

    def spy(*args: Any, **kwargs: Any) -> FastMCP:
        built.append(kwargs.get("read_only", False))
        return real_create(*args, **kwargs)

    monkeypatch.setenv("TRAKT_MCP_READ_ONLY", "true")
    monkeypatch.setattr(main_module, "create_server", spy)

    def nothing(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(main_module, "build_app", nothing)
    monkeypatch.setattr(main_module, "serve", nothing)
    main_module.run(["--transport", "http"])
    assert built == [True]


def test_run_over_stdio_serves_a_read_only_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served: list[FastMCP] = []
    monkeypatch.setenv("TRAKT_MCP_READ_ONLY", "true")

    def record(self: FastMCP, *_args: Any, **_kwargs: Any) -> None:
        served.append(self)

    monkeypatch.setattr(FastMCP, "run", record)
    main_module.run([])
    assert len(served) == 1
    assert isinstance(served[0], ReadOnlyFastMCP)
