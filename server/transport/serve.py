"""Run the HTTP transport app under uvicorn."""

import logging

import uvicorn
from starlette.applications import Starlette

from .settings import TransportSettings

logger = logging.getLogger("trakt_mcp")

_GRACEFUL_SHUTDOWN_SECONDS = 10


def serve(app: Starlette, settings: TransportSettings) -> None:
    """Serve ``app`` until the process is stopped."""
    logger.info(
        "Serving Streamable HTTP on http://%s:%d/mcp"
        + " (legacy SSE on /sse is deprecated)",
        settings.host,
        settings.port,
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
        # Open SSE streams would otherwise hold shutdown open indefinitely.
        timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_SECONDS,
    )
