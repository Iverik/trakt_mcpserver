"""MCP tools for the authenticated Trakt calendars."""

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Annotated, Final

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

from client.calendars import CalendarsClient
from client.pool import get_client
from config.api.calendars import CALENDAR_DEFAULT_DAYS, CALENDAR_MAX_DAYS
from config.mcp.annotations import READ_ONLY
from config.mcp.descriptions import (
    CALENDAR_DAYS_DESCRIPTION,
    CALENDAR_START_DATE_DESCRIPTION,
    CALENDAR_TYPE_DESCRIPTION,
)
from models.calendars.calendar import CalendarKind
from models.formatters.calendars import CalendarFormatters
from server.base import ToolErrors
from utils.api.errors import handle_api_errors_func

logger = logging.getLogger("trakt_mcp")

# Type alias for tool handlers
ToolHandler = Callable[..., Awaitable[str]]

_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}")


class CalendarParams(BaseModel):
    """Parameters for fetching the user's calendar."""

    calendar_type: CalendarKind
    start_date: str | None = None
    days: int = Field(CALENDAR_DEFAULT_DAYS, ge=1)

    @field_validator("start_date")
    @classmethod
    def _validate_start_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not _DATE_PATTERN.fullmatch(text):
            raise ValueError("start_date must be formatted as YYYY-MM-DD")
        date.fromisoformat(text)
        return text


@handle_api_errors_func
async def fetch_my_calendar(
    calendar_type: CalendarKind,
    start_date: str | None = None,
    days: int = CALENDAR_DEFAULT_DAYS,
) -> str:
    """Fetch the authenticated user's calendar from Trakt.

    Args:
        calendar_type: shows, new_shows, premieres, finales or movies.
        start_date: First day as YYYY-MM-DD (UTC). Defaults to today (UTC).
        days: Days to cover. Values above the API maximum are reduced to it.

    Returns:
        Formatted markdown grouped by date.

    Raises:
        AuthenticationRequiredError: If user is not authenticated.
    """
    logger.debug("fetch_my_calendar called with calendar_type=%s", calendar_type)
    params = CalendarParams(
        calendar_type=calendar_type, start_date=start_date, days=days
    )
    first_day = (
        date.fromisoformat(params.start_date)
        if params.start_date
        else datetime.now(UTC).date()
    )
    effective_days = min(params.days, CALENDAR_MAX_DAYS)
    clamped_from = params.days if params.days > CALENDAR_MAX_DAYS else None

    client = get_client(CalendarsClient)
    if params.calendar_type == "movies":
        movies = await client.get_my_movie_calendar(
            first_day.isoformat(), effective_days
        )
        if isinstance(movies, str):
            raise ToolErrors.handle_api_string_error(
                resource_type="calendar",
                resource_id="my_movies",
                error_message=movies,
                operation="fetch_my_calendar",
            )
        return CalendarFormatters.format_movie_calendar(
            movies, first_day, effective_days, clamped_from
        )

    shows = await client.get_my_show_calendar(
        params.calendar_type, first_day.isoformat(), effective_days
    )
    if isinstance(shows, str):
        raise ToolErrors.handle_api_string_error(
            resource_type="calendar",
            resource_id=f"my_{params.calendar_type}",
            error_message=shows,
            operation="fetch_my_calendar",
        )
    return CalendarFormatters.format_show_calendar(
        params.calendar_type, shows, first_day, effective_days, clamped_from
    )


def register_calendar_tools(mcp: FastMCP) -> tuple[ToolHandler]:
    """Register calendar tools with the MCP server.

    Returns:
        Tuple of tool handlers for type checker visibility.
    """

    @mcp.tool(
        name="fetch_my_calendar",
        annotations=READ_ONLY,
        description=(
            "Fetch your personal Trakt calendar: upcoming episodes or movie "
            "releases for items you watched, collected or watchlisted. Choose "
            "calendar_type 'shows', 'new_shows', 'premieres', 'finales' or "
            "'movies'. Covers start_date (default today) for days (default 7, "
            f"max {CALENDAR_MAX_DAYS}). Dates and times are UTC. Requires OAuth "
            "authentication. Example: calendar_type='premieres', "
            "start_date='2026-11-22', days=14."
        ),
    )
    async def fetch_my_calendar_tool(
        calendar_type: Annotated[
            CalendarKind, Field(description=CALENDAR_TYPE_DESCRIPTION)
        ],
        start_date: Annotated[
            str | None, Field(description=CALENDAR_START_DATE_DESCRIPTION)
        ] = None,
        days: Annotated[
            int, Field(ge=1, description=CALENDAR_DAYS_DESCRIPTION)
        ] = CALENDAR_DEFAULT_DAYS,
    ) -> str:
        """MCP tool: fetch the authenticated user's calendar."""
        return await fetch_my_calendar(calendar_type, start_date, days)

    return (fetch_my_calendar_tool,)
