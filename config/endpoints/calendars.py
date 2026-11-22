"""Trakt API endpoints for calendars."""

from collections.abc import Mapping
from typing import Final

from .keys import EndpointKey

CALENDARS_ENDPOINTS: Final[Mapping[EndpointKey, str]] = {
    "calendar_my_shows": "/calendars/my/shows/:start_date/:days",
    "calendar_my_new_shows": "/calendars/my/shows/new/:start_date/:days",
    "calendar_my_premieres": "/calendars/my/shows/premieres/:start_date/:days",
    "calendar_my_finales": "/calendars/my/shows/finales/:start_date/:days",
    "calendar_my_movies": "/calendars/my/movies/:start_date/:days",
}
