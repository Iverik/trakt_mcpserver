"""Client for the authenticated movie calendar."""

from client.auth import AuthClient
from config.endpoints import TRAKT_ENDPOINTS
from models.calendars.calendar import CalendarMovieEntry
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors


class MovieCalendarClient(AuthClient):
    """Client for fetching the user's movie calendar from Trakt."""

    @handle_api_errors
    async def get_my_movie_calendar(
        self, start_date: str, days: int
    ) -> list[CalendarMovieEntry]:
        """Fetch the user's movie calendar.

        Args:
            start_date: First day, YYYY-MM-DD (UTC).
            days: Number of days to cover (already within the API maximum).

        Returns:
            Calendar entries, one per movie release.

        Raises:
            AuthenticationRequiredError: If the client is not authenticated.
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError("get movie calendar")

        endpoint = (
            TRAKT_ENDPOINTS["calendar_my_movies"]
            .replace(":start_date", start_date)
            .replace(":days", str(days))
        )
        return await self._make_typed_list_request(
            endpoint=endpoint, response_type=CalendarMovieEntry
        )
