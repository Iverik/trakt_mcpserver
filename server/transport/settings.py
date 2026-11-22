"""Resolve transport settings from command-line flags and the environment."""

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from config.transport import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ENV_ALLOWED_HOSTS,
    ENV_ALLOWED_ORIGINS,
    ENV_HOST,
    ENV_LEGACY_SSE,
    ENV_PORT,
    ENV_STATELESS,
    ENV_TRANSPORT,
    TRANSPORT_HTTP,
    TRANSPORT_STDIO,
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no"})
_STRICT_TRUE_VALUES = frozenset({"1", "true", "yes"})
_MAX_PORT = 65535


@dataclass(frozen=True, slots=True)
class TransportSettings:
    """How the server is exposed. ``stdio`` ignores every other field."""

    transport: str = TRANSPORT_STDIO
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allowed_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    stateless: bool = False
    legacy_sse: bool = True


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid port: {value!r}") from None
    if not 1 <= port <= _MAX_PORT:
        raise argparse.ArgumentTypeError(f"port out of range: {port}")
    return port


def _flag(value: str) -> bool:
    """Parse true/false, 1/0 or yes/no, case-insensitively."""
    word = value.strip().lower()
    if word in _STRICT_TRUE_VALUES:
        return True
    if word in _FALSE_VALUES:
        return False
    raise argparse.ArgumentTypeError(f"expected true or false, got {value!r}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trakt-mcp",
        description="Trakt MCP server. Runs over stdio unless --transport http.",
    )
    parser.add_argument(
        "--transport",
        choices=(TRANSPORT_STDIO, TRANSPORT_HTTP),
        help=f"default: stdio (env {ENV_TRANSPORT})",
    )
    parser.add_argument("--host", help=f"HTTP bind host (env {ENV_HOST})")
    parser.add_argument("--port", type=_port, help=f"HTTP port (env {ENV_PORT})")
    parser.add_argument(
        "--no-legacy-sse",
        action="store_true",
        help=f"do not serve the deprecated /sse transport (env {ENV_LEGACY_SSE}=false)",
    )
    return parser


def load_settings(
    argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None
) -> TransportSettings:
    """Build settings; a flag wins over its environment variable.

    Args:
        argv: Command-line arguments without the program name
        env: Environment to read; defaults to ``os.environ``

    Returns:
        The resolved settings. Exits with a usage error on an invalid value.
    """
    environment = os.environ if env is None else env
    parser = _build_parser()
    args = parser.parse_args(argv)

    transport: str = (
        args.transport or environment.get(ENV_TRANSPORT) or TRANSPORT_STDIO
    ).lower()
    if transport not in (TRANSPORT_STDIO, TRANSPORT_HTTP):
        parser.error(f"invalid {ENV_TRANSPORT}: {transport!r}")

    port: int = args.port or DEFAULT_PORT
    if args.port is None and environment.get(ENV_PORT):
        try:
            port = _port(environment[ENV_PORT])
        except argparse.ArgumentTypeError as error:
            parser.error(f"{ENV_PORT}: {error}")

    legacy_sse = True
    if args.no_legacy_sse:
        legacy_sse = False
    elif environment.get(ENV_LEGACY_SSE) is not None:
        try:
            legacy_sse = _flag(environment[ENV_LEGACY_SSE])
        except argparse.ArgumentTypeError as error:
            parser.error(f"{ENV_LEGACY_SSE}: {error}")

    return TransportSettings(
        transport=transport,
        host=args.host or environment.get(ENV_HOST) or DEFAULT_HOST,
        port=port,
        allowed_origins=_split_csv(environment.get(ENV_ALLOWED_ORIGINS, "")),
        allowed_hosts=_split_csv(environment.get(ENV_ALLOWED_HOSTS, "")),
        stateless=environment.get(ENV_STATELESS, "").strip().lower() in _TRUE_VALUES,
        legacy_sse=legacy_sse,
    )
