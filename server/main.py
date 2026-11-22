"""Main server module for the Trakt MCP server."""

import logging
import sys
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Final

from mcp.server.fastmcp import FastMCP

from client.pool import shutdown_clients
from config.transport import TRANSPORT_HTTP
from utils.version import package_version

# Import all module registration functions
from .auth import register_auth_resources, register_auth_tools
from .calendars import register_calendar_tools
from .checkin import register_checkin_tools
from .comments import register_comment_tools
from .episodes import register_episode_tools
from .lists import register_lists_tools
from .movies import register_movie_resources, register_movie_tools
from .people import register_people_tools
from .progress import register_progress_tools
from .prompts.basic import register_basic_prompts
from .recommendations import register_recommendation_tools
from .search import register_search_tools
from .seasons import register_season_tools
from .shows import register_show_resources, register_show_tools
from .sync import register_sync_tools
from .transport.app import build_app
from .transport.serve import serve
from .transport.settings import load_settings
from .user import register_user_resources, register_user_tools

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("trakt_mcp")

REGISTRATIONS: Final[tuple[Callable[[FastMCP], object], ...]] = (
    register_auth_resources,
    register_auth_tools,
    register_show_resources,
    register_show_tools,
    register_movie_resources,
    register_movie_tools,
    register_comment_tools,
    register_user_resources,
    register_user_tools,
    register_search_tools,
    register_calendar_tools,
    register_checkin_tools,
    register_sync_tools,
    register_progress_tools,
    register_recommendation_tools,
    register_season_tools,
    register_episode_tools,
    register_lists_tools,
    register_people_tools,
    register_basic_prompts,
)


@asynccontextmanager
async def _lifespan(_mcp: FastMCP) -> AsyncGenerator[None]:
    """Close pooled HTTP clients when the server stops."""
    try:
        yield
    finally:
        await shutdown_clients()


@asynccontextmanager
async def idle_lifespan(_mcp: FastMCP) -> AsyncGenerator[None]:
    """Do nothing: over HTTP the lifespan runs per session, not per process."""
    yield


def create_server(
    lifespan: Callable[[FastMCP], AbstractAsyncContextManager[None]] = _lifespan,
) -> FastMCP:
    """Create and configure the Trakt MCP server with all modules.

    Args:
        lifespan: Context manager run around each server run. The default
            closes the shared HTTP clients on exit, which is only right when a
            run is the whole process (stdio).

    Returns:
        Configured FastMCP server instance
    """
    logger.info("Starting trakt-mcp v%s", package_version())
    mcp = FastMCP(name="trakt-mcp", lifespan=lifespan)
    for register in REGISTRATIONS:
        register(mcp)
    logger.info("All Trakt MCP modules registered successfully")
    return mcp


# Create the server instance
mcp = create_server()


def run(argv: Sequence[str] | None = None) -> None:
    """Console-script entry point (used by `[project.scripts]` and uvx).

    Serves over stdio unless ``--transport http`` or TRAKT_MCP_TRANSPORT=http.
    """
    settings = load_settings(argv)
    if settings.transport == TRANSPORT_HTTP:
        http_server = create_server(lifespan=idle_lifespan)
        serve(build_app(http_server, settings), settings)
        return
    # Print to stderr to avoid polluting stdout (required for stdio transport)
    print("Starting Trakt MCP server...", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    run()
