"""Client for the authenticated show calendars."""

from typing import Final

from client.auth import AuthClient
from config.endpoints import TRAKT_ENDPOINTS
from config.endpoints.keys import EndpointKey
from models.calendars.calendar import CalendarKind, CalendarShowEntry
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors

SHOW_CALENDAR_ENDPOINT_KEYS: Final[dict[CalendarKind, EndpointKey]] = {
    "shows": "calendar_my_shows",
    "new_shows": "calendar_my_new_shows",
    "premieres": "calendar_my_premieres",
    "finales": "calendar_my_finales",
}


class ShowCalendarClient(AuthClient):
    """Client for fetching the user's show calendars from Trakt."""

    @handle_api_errors
    async def get_my_show_calendar(
        self, kind: CalendarKind, start_date: str, days: int
    ) -> list[CalendarShowEntry]:
        """Fetch the user's show calendar.

        Args:
            kind: One of shows, new_shows, premieres or finales.
            start_date: First day, YYYY-MM-DD (UTC).
            days: Number of days to cover (already within the API maximum).

        Returns:
            Calendar entries, one per episode.

        Raises:
            AuthenticationRequiredError: If the client is not authenticated.
            ValueError: If kind is not a show calendar.
        """
        if kind not in SHOW_CALENDAR_ENDPOINT_KEYS:
            raise ValueError(f"Not a show calendar: {kind}")
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError("get show calendar")

        endpoint = (
            TRAKT_ENDPOINTS[SHOW_CALENDAR_ENDPOINT_KEYS[kind]]
            .replace(":start_date", start_date)
            .replace(":days", str(days))
        )
        # The network name is only returned with extended=full.
        return await self._make_typed_list_request(
            endpoint=endpoint,
            params={"extended": "full"},
            response_type=CalendarShowEntry,
        )
