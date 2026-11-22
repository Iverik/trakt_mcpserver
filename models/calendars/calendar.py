"""Pydantic models for Trakt calendar responses."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from models.types.ids import TraktIds

CalendarKind = Literal["shows", "new_shows", "premieres", "finales", "movies"]


class CalendarShow(BaseModel):
    """Show summary inside a calendar entry."""

    title: str
    year: int | None = None
    network: str | None = None
    ids: TraktIds = Field(default_factory=TraktIds)


class CalendarEpisode(BaseModel):
    """Episode summary inside a calendar entry."""

    season: int
    number: int
    title: str | None = None


class CalendarShowEntry(BaseModel):
    """One episode airing in a show calendar."""

    first_aired: datetime = Field(description="UTC air time")
    episode: CalendarEpisode
    show: CalendarShow


class CalendarMovie(BaseModel):
    """Movie summary inside a calendar entry."""

    title: str
    year: int | None = None
    ids: TraktIds = Field(default_factory=TraktIds)


class CalendarMovieEntry(BaseModel):
    """One movie releasing in the movie calendar."""

    released: date = Field(description="Release date (UTC day)")
    movie: CalendarMovie
