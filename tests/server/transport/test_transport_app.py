"""Tests for the combined Streamable HTTP + SSE app: routes, Origin, Host."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from server.main import (
    create_server,
    idle_lifespan,
)
from server.transport.app import build_app
from server.transport.deprecation import SseDeprecationMiddleware
from server.transport.origin import OriginGuardMiddleware
from server.transport.settings import TransportSettings

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def make_app(**overrides: object) -> Starlette:
    settings = TransportSettings(transport="http", host="0.0.0.0", **overrides)  # type: ignore[arg-type]  # noqa: S104
    return build_app(create_server(lifespan=idle_lifespan), settings)


@asynccontextmanager
async def serving(app: Starlette) -> AsyncGenerator[httpx.AsyncClient]:
    """An HTTP client for ``app`` with its lifespan (session manager) running."""
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http,
    ):
        yield http


def test_route_table_has_mcp_sse_messages_and_health() -> None:
    app = make_app()
    paths = {route.path for route in app.routes if isinstance(route, Route | Mount)}

    assert {"/mcp", "/sse", "/messages", "/healthz"} <= paths


@pytest.mark.asyncio
async def test_streamable_http_initialize_without_origin_is_accepted() -> None:
    async with serving(make_app(stateless=True)) as client:
        response = await client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)

    assert response.status_code == 200
    assert "trakt-mcp" in response.text


@pytest.mark.asyncio
async def test_disallowed_origin_is_rejected_on_every_guarded_path() -> None:
    headers = {**MCP_HEADERS, "Origin": "https://evil.example"}

    async with serving(make_app(stateless=True)) as client:
        mcp = await client.post("/mcp", json=INITIALIZE, headers=headers)
        sse = await client.get("/sse", headers=headers)
        messages = await client.post(
            "/messages/?session_id=x", json={}, headers=headers
        )

    assert [r.status_code for r in (mcp, sse, messages)] == [403, 403, 403]


@pytest.mark.asyncio
async def test_empty_allowlist_rejects_any_present_origin() -> None:
    headers = {**MCP_HEADERS, "Origin": "https://claude.ai"}

    async with serving(make_app(stateless=True)) as client:
        response = await client.post("/mcp", json=INITIALIZE, headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_allowlisted_origin_is_accepted() -> None:
    app = make_app(allowed_origins=("https://claude.ai",), stateless=True)
    headers = {**MCP_HEADERS, "Origin": "https://claude.ai"}

    async with serving(app) as test_client:
        response = await test_client.post("/mcp", json=INITIALIZE, headers=headers)

    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origins",
    [
        ["https://claude.ai", "https://claude.ai"],
        ["https://claude.ai", "https://evil.example"],
        ["https://evil.example", "https://claude.ai"],
    ],
    ids=["duplicate", "allowed-then-evil", "evil-then-allowed"],
)
async def test_multiple_origin_headers_are_rejected(origins: list[str]) -> None:
    app = make_app(allowed_origins=("https://claude.ai",), stateless=True)
    headers = [*MCP_HEADERS.items(), *(("Origin", origin) for origin in origins)]

    async with serving(app) as test_client:
        response = await test_client.post("/mcp", json=INITIALIZE, headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_health_does_not_require_or_check_origin() -> None:
    async with serving(make_app(stateless=True)) as client:
        response = await client.get(
            "/healthz", headers={"Origin": "https://evil.example"}
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_host_check_is_off_by_default_when_bound_publicly() -> None:
    async with serving(make_app(stateless=True)) as client:
        response = await client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Host": "trakt:8080"}
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_configured_hosts_are_enforced() -> None:
    app = make_app(allowed_hosts=("trakt:8080",), stateless=True)

    async with serving(app) as test_client:
        allowed = await test_client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Host": "trakt:8080"}
        )
        denied = await test_client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Host": "evil.example"}
        )

    assert allowed.status_code == 200
    assert denied.status_code == 421


@pytest.mark.asyncio
async def test_loopback_bind_defaults_to_loopback_hosts_only() -> None:
    settings = TransportSettings(transport="http", stateless=True)
    app = build_app(create_server(lifespan=idle_lifespan), settings)

    async with serving(app) as test_client:
        local = await test_client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Host": "localhost:8080"}
        )
        remote = await test_client.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Host": "trakt:8080"}
        )

    assert local.status_code == 200
    assert remote.status_code == 421


@pytest.mark.asyncio
async def test_legacy_sse_off_unmounts_sse_routes() -> None:
    app = make_app(stateless=True, legacy_sse=False)
    paths = {route.path for route in app.routes if isinstance(route, Route | Mount)}

    assert {"/mcp", "/healthz"} <= paths
    assert not paths & {"/sse", "/messages"}

    async with serving(app) as client:
        sse = await client.get("/sse")
        messages = await client.post("/messages/?session_id=x", json={})
        mcp = await client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)
        health = await client.get("/healthz")

    assert [r.status_code for r in (sse, messages, mcp, health)] == [404, 404, 200, 200]


@pytest.mark.asyncio
async def test_legacy_sse_off_still_guards_origin_on_mcp() -> None:
    headers = {**MCP_HEADERS, "Origin": "https://evil.example"}

    async with serving(make_app(stateless=True, legacy_sse=False)) as client:
        response = await client.post("/mcp", json=INITIALIZE, headers=headers)

    assert response.status_code == 403


def test_legacy_sse_off_has_no_deprecation_middleware() -> None:
    off = make_app(legacy_sse=False)
    on = make_app(legacy_sse=True)

    assert [m.cls for m in off.user_middleware] == [OriginGuardMiddleware]
    assert [m.cls for m in on.user_middleware] == [
        OriginGuardMiddleware,
        SseDeprecationMiddleware,
    ]
