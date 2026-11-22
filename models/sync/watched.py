"""Sync watched models for the Trakt MCP server."""

from datetime import datetime

from pydantic import BaseModel, Field

from models.movies.movie import TraktMovie


class WatchedMovieItem(BaseModel):
    """One movie from ``GET /sync/watched/movies``."""

    plays: int = Field(default=0, ge=0, description="Number of times watched")
    last_watched_at: datetime | None = None
    last_updated_at: datetime | None = None
    movie: TraktMovie
