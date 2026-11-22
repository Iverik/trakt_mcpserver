"""Transport constants for the Trakt MCP server."""

from typing import Final

TRANSPORT_STDIO: Final[str] = "stdio"
TRANSPORT_HTTP: Final[str] = "http"

# Environment variables read when the matching command-line flag is absent.
ENV_TRANSPORT: Final[str] = "TRAKT_MCP_TRANSPORT"
ENV_HOST: Final[str] = "TRAKT_MCP_HOST"
ENV_PORT: Final[str] = "TRAKT_MCP_PORT"
ENV_ALLOWED_ORIGINS: Final[str] = "TRAKT_MCP_ALLOWED_ORIGINS"
ENV_ALLOWED_HOSTS: Final[str] = "TRAKT_MCP_ALLOWED_HOSTS"
ENV_STATELESS: Final[str] = "TRAKT_MCP_STATELESS"
ENV_LEGACY_SSE: Final[str] = "TRAKT_MCP_LEGACY_SSE"

# Loopback by default: exposing the server beyond the machine is opt-in.
DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8080
LOOPBACK_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost", "::1"})

# Host header patterns accepted when bound to loopback and none are configured.
LOOPBACK_ALLOWED_HOSTS: Final[tuple[str, ...]] = (
    "127.0.0.1:*",
    "localhost:*",
    "[::1]:*",
)

HEALTH_PATH: Final[str] = "/healthz"
