"""Deprecation notice for the legacy HTTP+SSE transport."""

import logging

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("trakt_mcp")

SSE_DEPRECATION_MESSAGE = (
    "Client connected over the deprecated HTTP+SSE transport at %s; "
    "use Streamable HTTP at %s. The SSE endpoint will be removed in a future release."
)


class SseDeprecationMiddleware:
    """Log a warning whenever a client opens the legacy SSE stream."""

    def __init__(self, app: ASGIApp, sse_path: str, streamable_path: str) -> None:
        """Wrap ``app``; warn on GET ``sse_path``."""
        self.app = app
        self.sse_path = sse_path
        self.streamable_path = streamable_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Log the notice for SSE stream requests, then pass the request on."""
        if (
            scope["type"] == "http"
            and scope["method"] == "GET"
            and scope["path"] == self.sse_path
        ):
            logger.warning(SSE_DEPRECATION_MESSAGE, self.sse_path, self.streamable_path)
        await self.app(scope, receive, send)
