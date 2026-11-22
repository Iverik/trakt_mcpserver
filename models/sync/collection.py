"""Sync collection models for the Trakt MCP server."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.movies.movie import TraktMovie
from models.shows.show import TraktShow


class CollectionMetadata(BaseModel):
    """Media metadata Trakt returns with ``extended=metadata``."""

    model_config = ConfigDict(populate_by_name=True)

    media_type: str | None = Field(default=None, description="e.g. bluray, digital")
    resolution: str | None = Field(default=None, description="e.g. uhd_4k")
    hdr: str | None = Field(default=None, description="e.g. dolby_vision")
    audio: str | None = Field(default=None, description="e.g. dolby_atmos")
    audio_channels: str | None = Field(default=None, description="e.g. 7.1")
    three_d: bool | None = Field(default=None, alias="3d", description="3D release")


class CollectionEpisode(BaseModel):
    """A collected episode nested inside a collected show season."""

    number: int = Field(ge=0)
    collected_at: datetime | None = None
    metadata: CollectionMetadata | None = None


class CollectionSeason(BaseModel):
    """A collected season with its collected episodes."""

    number: int = Field(ge=0)  # Season 0 is typically specials
    episodes: list[CollectionEpisode] = Field(
        default_factory=lambda: list[CollectionEpisode]()
    )


class CollectionItem(BaseModel):
    """One item from the sync collection API (a movie or a show)."""

    type: Literal["movie", "show"] | None = None
    movie: TraktMovie | None = None
    show: TraktShow | None = None
    collected_at: datetime | None = Field(
        default=None, description="Movies: when it was collected"
    )
    updated_at: datetime | None = None
    metadata: CollectionMetadata | None = Field(
        default=None, description="Movies: present with extended=metadata"
    )
    last_collected_at: datetime | None = Field(
        default=None, description="Shows: most recent episode collection"
    )
    last_updated_at: datetime | None = None
    seasons: list[CollectionSeason] | None = Field(
        default=None, description="Shows: collected seasons and episodes"
    )

    @property
    def collected_episode_count(self) -> int:
        """Number of collected episodes across all seasons (shows)."""
        return sum(len(season.episodes) for season in self.seasons or [])


class CollectionFetchResult(BaseModel):
    """Every collection item fetched across all pages."""

    items: list[CollectionItem]
    pages_fetched: int = Field(ge=0)
    truncated: bool = Field(
        default=False,
        description="True when the page-count guard stopped the fetch early",
    )
