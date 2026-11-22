"""Tests for the movie check-in and cancel tools."""

from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from config.mcp.tools import CHECKIN_TOOLS
from models.types.api_responses import CheckinResponse
from server.checkin import register_checkin_tools
from server.checkin.tools import cancel_checkin, checkin_to_movie, checkin_to_show
from utils.api.error_types import (
    AuthenticationRequiredError,
    InvalidParamsError,
    InvalidRequestError,
)


@pytest.fixture
def movie_response() -> CheckinResponse:
    return {
        "id": 99,
        "watched_at": "2026-11-22T20:00:00.000Z",
        "sharing": {"twitter": False, "mastodon": True, "tumblr": False},
        "movie": {
            "title": "The Dark Knight",
            "year": 2008,
            "ids": {"trakt": 120, "slug": "the-dark-knight-2008"},
        },
    }


@pytest.mark.asyncio
async def test_checkin_to_movie_by_id(movie_response: CheckinResponse) -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock(return_value=movie_response)

        result = await checkin_to_movie(
            movie_id="120", message="Hi", share_mastodon=True
        )

        assert "# Successfully Checked In" in result
        assert "**The Dark Knight** (2008)" in result
        assert "Shared on: Mastodon" in result
        assert "Checkin ID: 99" in result
        client.checkin_to_movie.assert_called_once_with(
            movie_id="120",
            movie_title=None,
            movie_year=None,
            message="Hi",
            share_twitter=False,
            share_mastodon=True,
            share_tumblr=False,
        )


@pytest.mark.asyncio
async def test_checkin_to_movie_by_title(movie_response: CheckinResponse) -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock(return_value=movie_response)

        await checkin_to_movie(movie_title="The Dark Knight", movie_year=2008)

        kwargs = client.checkin_to_movie.call_args.kwargs
        assert kwargs["movie_id"] is None
        assert kwargs["movie_title"] == "The Dark Knight"
        assert kwargs["movie_year"] == 2008


@pytest.mark.asyncio
async def test_checkin_to_movie_title_without_year_is_rejected() -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock()

        with pytest.raises(InvalidParamsError) as excinfo:
            await checkin_to_movie(movie_title="Heat")

        assert "movie_year" in str(excinfo.value)
        client.checkin_to_movie.assert_not_called()


@pytest.mark.asyncio
async def test_checkin_to_movie_drops_the_watched_cache(
    movie_response: CheckinResponse,
) -> None:
    with (
        patch("server.checkin.tools.CheckinClient") as client_class,
        patch("server.checkin.tools.invalidate_watched_cache") as invalidate,
    ):
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock(return_value=movie_response)

        await checkin_to_movie(movie_id="120")

    invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_failed_checkin_keeps_the_watched_cache() -> None:
    with (
        patch("server.checkin.tools.CheckinClient") as client_class,
        patch("server.checkin.tools.invalidate_watched_cache") as invalidate,
    ):
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock(return_value="API error")

        with pytest.raises(Exception):  # noqa: B017
            await checkin_to_movie(movie_id="120")

    invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_checkin_to_movie_requires_id_or_title() -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)

        with pytest.raises(InvalidParamsError) as excinfo:
            await checkin_to_movie()

        assert excinfo.value.code == -32602
        client.checkin_to_movie.assert_not_called()


@pytest.mark.asyncio
async def test_checkin_to_movie_not_authenticated() -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=False)

        with pytest.raises(AuthenticationRequiredError) as excinfo:
            await checkin_to_movie(movie_id="120")

        assert excinfo.value.data is not None
        assert excinfo.value.data["error_type"] == "auth_required"
        client.checkin_to_movie.assert_not_called()


@pytest.mark.asyncio
async def test_checkin_to_movie_malformed_id_is_invalid_params() -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock(side_effect=ValueError("bad IMDB id"))

        with pytest.raises(InvalidParamsError, match="bad IMDB id"):
            await checkin_to_movie(movie_id="ttabc")


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["movie", "show"])
async def test_already_checked_in_error_reaches_the_caller(tool: str) -> None:
    conflict = InvalidRequestError(
        "You are already checked in to something on Trakt.",
        data={"http_status": 409, "expires_at": "2026-11-22T22:30:00.000Z"},
    )
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock(side_effect=conflict)
        client.checkin_to_show = AsyncMock(side_effect=conflict)

        with pytest.raises(InvalidRequestError) as excinfo:
            if tool == "movie":
                await checkin_to_movie(movie_id="120")
            else:
                await checkin_to_show(season=1, episode=1, show_id="1")

        assert excinfo.value is conflict


@pytest.mark.asyncio
async def test_checkin_to_movie_api_error_string() -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.checkin_to_movie = AsyncMock(return_value="boom")

        with pytest.raises(Exception, match="checkin"):
            await checkin_to_movie(movie_id="120")


@pytest.mark.asyncio
async def test_cancel_checkin() -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=True)
        client.cancel_checkin = AsyncMock(return_value=None)

        result = await cancel_checkin()

        assert "# Check-in Cancelled" in result
        assert "paused playback" in result
        client.cancel_checkin.assert_called_once_with()


@pytest.mark.asyncio
async def test_cancel_checkin_not_authenticated() -> None:
    with patch("server.checkin.tools.CheckinClient") as client_class:
        client = client_class.return_value
        client.ensure_authenticated = AsyncMock(return_value=False)

        with pytest.raises(AuthenticationRequiredError):
            await cancel_checkin()

        client.cancel_checkin.assert_not_called()


@pytest.mark.asyncio
async def test_registered_checkin_tools() -> None:
    mcp = FastMCP(name="test")
    register_checkin_tools(mcp)

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert set(tools) == CHECKIN_TOOLS
    movie_schema = tools["checkin_to_movie"].inputSchema
    assert movie_schema.get("required", []) == []
    for name in ("movie_id", "movie_title", "movie_year", "message"):
        assert movie_schema["properties"][name]["description"]
    assert tools["cancel_checkin"].inputSchema["properties"] == {}
