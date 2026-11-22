"""Checkin tools for the Trakt MCP server."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from client.checkin.client import CheckinClient
from client.pool import get_client
from config.mcp.descriptions import (
    EPISODE_DESCRIPTION,
    MOVIE_ID_DESCRIPTION,
    SEASON_DESCRIPTION,
    SHOW_ID_DESCRIPTION,
)
from models.formatters.checkin import CheckinFormatters
from server.base import ToolErrors
from server.sync.cache import invalidate_watched_cache
from utils.api.errors import MCPError

logger = logging.getLogger("trakt_mcp")


async def checkin_to_show(
    season: int,
    episode: int,
    show_id: str | None = None,
    show_title: str | None = None,
    show_year: int | None = None,
    message: str = "",
    share_twitter: bool = False,
    share_mastodon: bool = False,
    share_tumblr: bool = False,
) -> str:
    """Check in to a show episode that the user is currently watching.

    This will mark the episode as watched on Trakt and can optionally share to
    connected social media. First use the search_shows tool to find the correct
    show_id before checking in, or provide the show title.

    Args:
        season: Season number
        episode: Episode number
        show_id: Trakt ID for the show (use search_shows to find this,
            optional if show_title is provided)
        show_title: Title of the show (optional if show_id is provided)
        show_year: Year the show was released (optional, can help with ambiguous titles)
        message: Optional message to include with the checkin
        share_twitter: Whether to share this checkin on Twitter
        share_mastodon: Whether to share this checkin on Mastodon
        share_tumblr: Whether to share this checkin on Tumblr

    Returns:
        Confirmation of the checkin

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InvalidParamsError: If required parameters are missing or invalid
        InternalError: If an unexpected error occurs
    """
    client = get_client(CheckinClient)

    # Check authentication (attempts token refresh if expired)
    if not await client.ensure_authenticated():
        raise ToolErrors.handle_authentication_required(
            action="check in to a show episode",
            show_id=show_id,
            show_title=show_title,
            season=season,
            episode=episode,
        )

    # Validate parameters
    ToolErrors.validate_either_or_params(
        param_sets=[("show_id",), ("show_title",)],
        show_id=show_id,
        show_title=show_title,
    )

    try:
        # Attempt to check in to the show
        response = await client.checkin_to_show(
            episode_season=season,
            episode_number=episode,
            show_id=show_id,
            show_title=show_title,
            show_year=show_year,
            message=message,
            share_twitter=share_twitter,
            share_mastodon=share_mastodon,
            share_tumblr=share_tumblr,
        )

        # Handle transitional case where API returns error strings
        if isinstance(response, str):
            raise ToolErrors.handle_api_string_error(
                resource_type="checkin",
                resource_id=show_id or show_title or "unknown",
                error_message=response,
                operation="checkin_to_show",
            )

        # Format the response
        return CheckinFormatters.format_checkin_response(response)
    except MCPError:
        raise
    except Exception as e:
        # Convert any unexpected errors to structured MCP errors
        raise ToolErrors.handle_unexpected_error(
            operation="check in to show episode",
            error=e,
            show_id=show_id,
            show_title=show_title,
            season=season,
            episode=episode,
            show_year=show_year,
        ) from e


async def checkin_to_movie(
    movie_id: str | None = None,
    movie_title: str | None = None,
    movie_year: int | None = None,
    message: str = "",
    share_twitter: bool = False,
    share_mastodon: bool = False,
    share_tumblr: bool = False,
) -> str:
    """Check in to a movie that the user is currently watching.

    This will show the movie as watching on Trakt and mark it watched when it
    finishes, optionally sharing to connected social media. First use the
    search_movies tool to find the correct movie_id before checking in, or
    provide the movie title.

    Args:
        movie_id: Trakt ID, Trakt slug, or IMDB ID for the movie (use
            search_movies to find this, optional if movie_title is provided)
        movie_title: Title of the movie (optional if movie_id is provided)
        movie_year: Year the movie was released (required when movie_id is
            not provided)
        message: Optional message to include with the checkin
        share_twitter: Whether to share this checkin on Twitter
        share_mastodon: Whether to share this checkin on Mastodon
        share_tumblr: Whether to share this checkin on Tumblr

    Returns:
        Confirmation of the checkin

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InvalidParamsError: If required parameters are missing or invalid
        InvalidRequestError: If the user is already checked in (HTTP 409)
        InternalError: If an unexpected error occurs
    """
    client = get_client(CheckinClient)

    if not await client.ensure_authenticated():
        raise ToolErrors.handle_authentication_required(
            action="check in to a movie",
            movie_id=movie_id,
            movie_title=movie_title,
        )

    ToolErrors.validate_either_or_params(
        param_sets=[("movie_id",), ("movie_title",)],
        movie_id=movie_id,
        movie_title=movie_title,
    )
    if not movie_id and movie_year is None:
        raise ToolErrors.handle_validation_error(
            "movie_year is required when checking in by title without a movie_id",
            operation="checkin_to_movie",
            movie_title=movie_title,
        )

    try:
        response = await client.checkin_to_movie(
            movie_id=movie_id,
            movie_title=movie_title,
            movie_year=movie_year,
            message=message,
            share_twitter=share_twitter,
            share_mastodon=share_mastodon,
            share_tumblr=share_tumblr,
        )

        if isinstance(response, str):
            raise ToolErrors.handle_api_string_error(
                resource_type="checkin",
                resource_id=movie_id or movie_title or "unknown",
                error_message=response,
                operation="checkin_to_movie",
            )

        # Trakt records the movie as watched, so the cached watched set is stale.
        invalidate_watched_cache()
        return CheckinFormatters.format_checkin_response(response)
    except MCPError:
        raise
    except ValueError as e:
        raise ToolErrors.handle_validation_error(
            str(e), operation="checkin_to_movie", movie_id=movie_id
        ) from e
    except Exception as e:
        raise ToolErrors.handle_unexpected_error(
            operation="check in to movie",
            error=e,
            movie_id=movie_id,
            movie_title=movie_title,
            movie_year=movie_year,
        ) from e


async def cancel_checkin() -> str:
    """Cancel the user's active check-in, whether a movie or an episode.

    Use this when the user stopped watching or checked in by mistake. Trakt
    keeps the elapsed progress as paused playback.

    Returns:
        Confirmation that the check-in was cancelled

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InternalError: If an unexpected error occurs
    """
    client = get_client(CheckinClient)

    if not await client.ensure_authenticated():
        raise ToolErrors.handle_authentication_required(action="cancel your check-in")

    try:
        result = await client.cancel_checkin()

        if isinstance(result, str):
            raise ToolErrors.handle_api_string_error(
                resource_type="checkin",
                resource_id="active_checkin",
                error_message=result,
                operation="cancel_checkin",
            )

        return CheckinFormatters.format_cancel_response()
    except MCPError:
        raise
    except Exception as e:
        raise ToolErrors.handle_unexpected_error(
            operation="cancel check-in", error=e
        ) from e


def register_checkin_tools(
    mcp: FastMCP,
) -> tuple[Callable[..., Awaitable[str]], ...]:
    """Register checkin tools with the MCP server.

    Returns:
        Tuple of tool handlers for type checker visibility
    """

    @mcp.tool(
        name="checkin_to_show",
        description="Check in to a TV show episode you're currently watching on Trakt",
    )
    async def checkin_to_show_tool(
        season: Annotated[int, Field(description=SEASON_DESCRIPTION)],
        episode: Annotated[int, Field(description=EPISODE_DESCRIPTION)],
        show_id: Annotated[
            str | None,
            Field(
                description=(
                    f"{SHOW_ID_DESCRIPTION}. Provide either show_id OR show_title."
                )
            ),
        ] = None,
        show_title: Annotated[
            str | None,
            Field(
                description=(
                    "Title of the show (e.g., 'Breaking Bad'). "
                    "Provide either show_title OR show_id."
                )
            ),
        ] = None,
        show_year: Annotated[
            int | None,
            Field(
                description=(
                    "Year the show first aired (e.g., 2008). "
                    "Helps disambiguate shows with the same title."
                )
            ),
        ] = None,
        message: Annotated[
            str,
            Field(
                description=(
                    "Optional message to share on connected social networks. "
                    "If not provided, uses the user's default watching message."
                )
            ),
        ] = "",
        share_twitter: Annotated[
            bool,
            Field(
                description=(
                    "Share this check-in on Twitter. "
                    "Overrides user's default sharing setting."
                )
            ),
        ] = False,
        share_mastodon: Annotated[
            bool,
            Field(
                description=(
                    "Share this check-in on Mastodon. "
                    "Overrides user's default sharing setting."
                )
            ),
        ] = False,
        share_tumblr: Annotated[
            bool,
            Field(
                description=(
                    "Share this check-in on Tumblr. "
                    "Overrides user's default sharing setting."
                )
            ),
        ] = False,
    ) -> str:
        return await checkin_to_show(
            season,
            episode,
            show_id,
            show_title,
            show_year,
            message,
            share_twitter,
            share_mastodon,
            share_tumblr,
        )

    @mcp.tool(
        name="checkin_to_movie",
        description="Check in to a movie you're currently watching on Trakt",
    )
    async def checkin_to_movie_tool(
        movie_id: Annotated[
            str | None,
            Field(
                description=(
                    f"{MOVIE_ID_DESCRIPTION}. Provide either movie_id OR movie_title."
                )
            ),
        ] = None,
        movie_title: Annotated[
            str | None,
            Field(
                description=(
                    "Title of the movie (e.g., 'The Dark Knight'). "
                    "Provide either movie_title OR movie_id."
                )
            ),
        ] = None,
        movie_year: Annotated[
            int | None,
            Field(
                description=(
                    "Year the movie was released (e.g., 2008). "
                    "Required when movie_id is not provided."
                )
            ),
        ] = None,
        message: Annotated[
            str,
            Field(
                description=(
                    "Optional message to share on connected social networks. "
                    "If not provided, uses the user's default watching message."
                )
            ),
        ] = "",
        share_twitter: Annotated[
            bool,
            Field(
                description=(
                    "Share this check-in on Twitter. "
                    "Overrides user's default sharing setting."
                )
            ),
        ] = False,
        share_mastodon: Annotated[
            bool,
            Field(
                description=(
                    "Share this check-in on Mastodon. "
                    "Overrides user's default sharing setting."
                )
            ),
        ] = False,
        share_tumblr: Annotated[
            bool,
            Field(
                description=(
                    "Share this check-in on Tumblr. "
                    "Overrides user's default sharing setting."
                )
            ),
        ] = False,
    ) -> str:
        return await checkin_to_movie(
            movie_id,
            movie_title,
            movie_year,
            message,
            share_twitter,
            share_mastodon,
            share_tumblr,
        )

    @mcp.tool(
        name="cancel_checkin",
        description=(
            "Cancel your active Trakt check-in, whether it is a movie or an "
            "episode. Use it when you stopped watching or checked in by mistake"
        ),
    )
    async def cancel_checkin_tool() -> str:
        return await cancel_checkin()

    # Return handlers for type checker visibility
    return checkin_to_show_tool, checkin_to_movie_tool, cancel_checkin_tool
