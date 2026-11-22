"""Unified calendars client."""

from client.calendars.movies import MovieCalendarClient
from client.calendars.shows import ShowCalendarClient


class CalendarsClient(ShowCalendarClient, MovieCalendarClient):
    """Unified client for the authenticated calendar operations.

    Combines functionality from:
    - ShowCalendarClient: get_my_show_calendar()
    - MovieCalendarClient: get_my_movie_calendar()

    Note: Calendar endpoints under /calendars/my require user authentication.
    """

    pass
