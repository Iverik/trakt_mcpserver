"""User client for user-specific data."""

from config.endpoints import TRAKT_ENDPOINTS
from models.types import UserWatchedMovie, UserWatchedShow
from models.user.stats import UserStats
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors

from ..auth import AuthClient


class UserClient(AuthClient):
    """Client for handling user-specific operations that require authentication."""

    @handle_api_errors
    async def get_user_watched_shows(self) -> list[UserWatchedShow]:
        """Get shows watched by the authenticated user.

        Returns:
            list[UserWatchedShow]: Watched shows.

        Raises:
            AuthenticationRequiredError: If the client is not authenticated.
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError("get user watched shows")

        return await self._make_typed_list_request(
            TRAKT_ENDPOINTS["user_watched_shows"], response_type=UserWatchedShow
        )

    @handle_api_errors
    async def get_user_watched_movies(self) -> list[UserWatchedMovie]:
        """Get movies watched by the authenticated user.

        Returns:
            list[UserWatchedMovie]: Watched movies.

        Raises:
            AuthenticationRequiredError: If the client is not authenticated.
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError("get user watched movies")

        return await self._make_typed_list_request(
            TRAKT_ENDPOINTS["user_watched_movies"], response_type=UserWatchedMovie
        )

    @handle_api_errors
    async def get_user_stats(self) -> UserStats | None:
        """Get watch, collection and rating stats for the authenticated user.

        Returns:
            UserStats | None: Stats, or None when Trakt answers 204 No Content
                (no precomputed stats for the account).

        Raises:
            AuthenticationRequiredError: If the client is not authenticated.
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError("get user stats")

        result = await self._make_request(
            "GET", TRAKT_ENDPOINTS["user_stats"], allow_empty=True
        )
        if result is None:
            return None
        return UserStats.model_validate(result)
