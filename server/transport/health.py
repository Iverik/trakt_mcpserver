"""Liveness endpoint: no MCP session, no auth, no Trakt call."""

import asyncio
import logging
import time
from typing import Final

from starlette.requests import Request
from starlette.responses import JSONResponse

from client.auth.client import AUTH_TOKEN_FILE
from client.auth.token_store import describe_load_error, get_token_store
from models.auth import TraktAuthToken

logger = logging.getLogger("trakt_mcp")

STATE_PRESENT: Final[str] = "present"
STATE_ABSENT: Final[str] = "absent"
STATE_EXPIRED: Final[str] = "expired"
STATE_UNREADABLE: Final[str] = "unreadable"


def _token_state(token: TraktAuthToken | None) -> str:
    if token is None:
        return STATE_ABSENT
    if token.created_at + token.expires_in <= time.time():
        return STATE_EXPIRED
    return STATE_PRESENT


def _probe_store() -> str:
    """Read the token state through the process-wide store (blocking I/O)."""
    return _token_state(get_token_store(AUTH_TOKEN_FILE).probe())


async def healthz(_request: Request) -> JSONResponse:
    """Report process and token-store health without exposing token data.

    Returns 200 with ``{"status": "ok", "token": "present|absent|expired"}``, or
    503 with ``{"status": "error", "token": "unreadable"}`` when the store
    cannot be read. An absent or expired token is still healthy: login is a
    tool call, not a precondition for serving.
    """
    try:
        token = await asyncio.to_thread(_probe_store)
    except Exception as error:
        # No traceback or message: a validation error would echo token values.
        logger.warning(
            "Health check could not read the token store: %s",
            describe_load_error(error),
        )
        return JSONResponse(
            {"status": "error", "token": STATE_UNREADABLE}, status_code=503
        )
    return JSONResponse({"status": "ok", "token": token})
