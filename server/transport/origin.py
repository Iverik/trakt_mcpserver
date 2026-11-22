"""Origin validation for the HTTP transports (MCP spec, Streamable HTTP)."""

import logging
from collections.abc import Collection

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("trakt_mcp")


class OriginGuardMiddleware:
    """Reject browser requests from origins that are not allowlisted.

    A request without an ``Origin`` header is let through: browsers always send
    one on cross-origin requests, so its absence marks a non-browser client
    (including a reverse proxy that forwards server-side). When the header is
    present it must exactly match an allowed origin, so an empty allowlist
    rejects every request that carries one. More than one Origin header is
    ambiguous and always rejected.
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_origins: Collection[str],
        guarded_prefixes: Collection[str],
    ) -> None:
        """Wrap ``app``, guarding paths that start with a guarded prefix."""
        self.app = app
        self.allowed_origins = frozenset(o.rstrip("/").lower() for o in allowed_origins)
        self.guarded_prefixes = tuple(guarded_prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer 403 for a disallowed Origin, otherwise pass the request on."""
        if scope["type"] == "http" and scope["path"].startswith(self.guarded_prefixes):
            origins = _origin_headers(scope)
            if len(origins) > 1 or any(
                origin.rstrip("/").lower() not in self.allowed_origins
                for origin in origins
            ):
                logger.warning("Rejected request with disallowed Origin %r", origins)
                response = PlainTextResponse("Invalid Origin header", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _origin_headers(scope: Scope) -> list[str]:
    return [
        value.decode("latin-1") for name, value in scope["headers"] if name == b"origin"
    ]
