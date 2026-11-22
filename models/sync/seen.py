"""Models for the have-I-seen-it lookup."""

from datetime import datetime

from pydantic import BaseModel, Field


class SeenEntry(BaseModel):
    """What the user's watched and rated data says about one Trakt movie id."""

    trakt_id: int = Field(ge=1)
    title: str | None = Field(default=None, description="Known from watched/rated data")
    year: int | None = None
    watched: bool = False
    plays: int = Field(default=0, ge=0)
    last_watched_at: datetime | None = None
    rating: int | None = Field(default=None, ge=1, le=10)
