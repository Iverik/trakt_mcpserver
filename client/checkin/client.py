"""Check-in functionality for Trakt."""

import json
from typing import Any, cast

from client.validation import validate_media_id
from config.endpoints import TRAKT_ENDPOINTS
from models.checkin import TraktCheckin
from models.types import CheckinResponse
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import InvalidRequestError, handle_api_errors
from utils.api.id_helpers import build_trakt_id_object

from ..auth import AuthClient


class CheckinClient(AuthClient):
    """Client for check-in operations."""

    @handle_api_errors
    async def checkin_to_show(
        self,
        episode_season: int,
        episode_number: int,
        show_id: str | None = None,
        show_title: str | None = None,
        show_year: int | None = None,
        message: str = "",
        share_twitter: bool = False,
        share_mastodon: bool = False,
        share_tumblr: bool = False,
    ) -> CheckinResponse:
        """Check in to a show episode the user is currently watching.

        Args:
            episode_season: Season number of the episode
            episode_number: Episode number within the season
            show_id: Trakt show ID (optional if show_title provided)
            show_title: Show title (optional if show_id provided)
            show_year: Show year (optional)
            message: Optional message for the check-in
            share_twitter: Whether to share on Twitter
            share_mastodon: Whether to share on Mastodon
            share_tumblr: Whether to share on Tumblr

        Returns:
            Check-in response data

        Raises:
            AuthenticationRequiredError: If not authenticated
            ValueError: If missing required parameters
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="check in to a show")

        if not show_id and not show_title:
            raise ValueError("Either show_id or show_title must be provided")

        # Prepare show data
        show_data: dict[str, Any] = (
            {"ids": {}} if not show_title else {"title": show_title}
        )

        # Add show ID if provided
        if show_id:
            if "ids" not in show_data:
                show_data["ids"] = {}
            show_data["ids"]["trakt"] = show_id

        # Add year if provided
        if show_year:
            show_data["year"] = show_year

        # Prepare episode data
        episode_data: dict[str, int] = {
            "season": episode_season,
            "number": episode_number,
        }

        # Prepare checkin data
        data: dict[str, Any] = {"episode": episode_data, "show": show_data}
        data.update(
            self._message_and_sharing(
                message, share_twitter, share_mastodon, share_tumblr
            )
        )

        return await self._post_checkin(data)

    @handle_api_errors
    async def checkin_to_movie(
        self,
        movie_id: str | None = None,
        movie_title: str | None = None,
        movie_year: int | None = None,
        message: str = "",
        share_twitter: bool = False,
        share_mastodon: bool = False,
        share_tumblr: bool = False,
    ) -> CheckinResponse:
        """Check in to a movie the user is currently watching.

        Args:
            movie_id: Trakt ID, Trakt slug, or IMDB ID (optional if movie_title
                provided)
            movie_title: Movie title (optional if movie_id provided)
            movie_year: Movie year (optional)
            message: Optional message for the check-in
            share_twitter: Whether to share on Twitter
            share_mastodon: Whether to share on Mastodon
            share_tumblr: Whether to share on Tumblr

        Returns:
            Check-in response data

        Raises:
            AuthenticationRequiredError: If not authenticated
            ValueError: If missing required parameters or the ID is malformed
            InvalidRequestError: If a check-in is already in progress (409)
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="check in to a movie")

        if not movie_id and not movie_title:
            raise ValueError("Either movie_id or movie_title must be provided")

        movie_data: dict[str, Any] = {}
        if movie_id:
            movie_ref = build_trakt_id_object(
                validate_media_id(movie_id, "movie_id"), "movies"
            )
            movie_data.update(movie_ref["movies"][0])
        if movie_title:
            movie_data["title"] = movie_title
        if movie_year:
            movie_data["year"] = movie_year

        data: dict[str, Any] = {"movie": movie_data}
        data.update(
            self._message_and_sharing(
                message, share_twitter, share_mastodon, share_tumblr
            )
        )

        return await self._post_checkin(data)

    @handle_api_errors
    async def cancel_checkin(self) -> None:
        """Cancel any active check-in (movie or episode).

        Trakt needs no item for this and answers 204 No Content. Elapsed
        progress is kept as paused playback.

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="cancel your check-in")

        await self._delete_request(TRAKT_ENDPOINTS["checkin"])

    @staticmethod
    def _message_and_sharing(
        message: str,
        share_twitter: bool,
        share_mastodon: bool,
        share_tumblr: bool,
    ) -> dict[str, Any]:
        """Build the optional message and sharing fields of a check-in body."""
        fields: dict[str, Any] = {}
        if message:
            fields["message"] = message
        if share_twitter or share_mastodon or share_tumblr:
            fields["sharing"] = {
                "twitter": share_twitter,
                "mastodon": share_mastodon,
                "tumblr": share_tumblr,
            }
        return fields

    async def _post_checkin(self, data: dict[str, Any]) -> CheckinResponse:
        """POST a check-in, turning Trakt's 409 into an actionable error."""
        try:
            response = await self._post_request(TRAKT_ENDPOINTS["checkin"], data)
        except InvalidRequestError as error:
            if error.data and error.data.get("http_status") == 409:
                raise self._already_checked_in(error) from error
            raise
        return cast(
            "CheckinResponse", TraktCheckin.from_api_response(response).model_dump()
        )

    @staticmethod
    def _already_checked_in(conflict: InvalidRequestError) -> InvalidRequestError:
        """Describe a 409, using the expires_at Trakt returns when present."""
        data = dict(conflict.data or {})
        expires_at: object = None
        try:
            body = json.loads(str(data.get("details")))
            if isinstance(body, dict):
                expires_at = cast("dict[str, Any]", body).get("expires_at")
        except ValueError:
            pass

        message = "You are already checked in to something on Trakt."
        if isinstance(expires_at, str) and expires_at:
            data["expires_at"] = expires_at
            message += f" You can check in again at {expires_at}."
        message += " Use cancel_checkin to end the current check-in first."
        return InvalidRequestError(message, data=data)
