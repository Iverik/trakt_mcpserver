"""Build the single ASGI app serving Streamable HTTP, legacy SSE and /healthz."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import BaseRoute, Route

from client.pool import shutdown_clients
from config.transport import (
    HEALTH_PATH,
    LOOPBACK_ALLOWED_HOSTS,
    LOOPBACK_HOSTS,
)

from .deprecation import SseDeprecationMiddleware
from .health import healthz
from .origin import OriginGuardMiddleware
from .settings import TransportSettings

logger = logging.getLogger("trakt_mcp")


def _security(settings: TransportSettings) -> TransportSecuritySettings:
    """Host header (DNS rebinding) checks, on when hosts are known.

    Bound to loopback with nothing configured, only loopback names are
    accepted. Bound elsewhere with nothing configured the Host check is off,
    because the right value depends on the proxy in front; the Origin check
    stays on either way.
    """
    hosts = list(settings.allowed_hosts)
    if not hosts and settings.host in LOOPBACK_HOSTS:
        hosts = list(LOOPBACK_ALLOWED_HOSTS)
    if not hosts:
        logger.info("No TRAKT_MCP_ALLOWED_HOSTS set: the Host header is not checked")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(hosts),
        allowed_hosts=hosts,
        allowed_origins=list(settings.allowed_origins),
    )


def build_app(mcp: FastMCP, settings: TransportSettings) -> Starlette:
    """Combine the SDK's Streamable HTTP and SSE apps with a health route.

    Args:
        mcp: Server built with a lifespan that does not close the shared HTTP
            clients; this app closes them once, when the process stops
        settings: Resolved transport settings

    Returns:
        One Starlette app owning the session manager lifespan
    """
    mcp.settings.host = settings.host
    mcp.settings.port = settings.port
    mcp.settings.stateless_http = settings.stateless
    mcp.settings.transport_security = _security(settings)

    streamable = mcp.streamable_http_app()
    sse = mcp.sse_app()
    routes: list[BaseRoute] = [
        Route(HEALTH_PATH, healthz, methods=["GET"]),
        *streamable.routes,
        *sse.routes,
    ]

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            await shutdown_clients()

    return Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(
                OriginGuardMiddleware,
                allowed_origins=settings.allowed_origins,
                guarded_prefixes=(
                    mcp.settings.streamable_http_path,
                    mcp.settings.sse_path,
                    mcp.settings.message_path.rstrip("/"),
                ),
            ),
            Middleware(
                SseDeprecationMiddleware,
                sse_path=mcp.settings.sse_path,
                streamable_path=mcp.settings.streamable_http_path,
            ),
        ],
    )
