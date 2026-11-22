"""Models for the unwatched-in-collection query."""

from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from config.api import UNWATCHED_DEFAULT_LIMIT, UNWATCHED_MAX_LIMIT
from models.sync.collection import CollectionItem

UnwatchedSort = Literal["rating", "runtime", "collected_at", "released", "random"]


class UnwatchedQuery(BaseModel):
    """Filters, sort and size for the unwatched-in-collection list."""

    collection_type: Literal["movies"] = "movies"
    min_runtime: int | None = Field(default=None, ge=0)
    max_runtime: int | None = Field(default=None, ge=0)
    genres_include: list[str] = Field(default_factory=lambda: list[str]())
    genres_exclude: list[str] = Field(default_factory=lambda: list[str]())
    min_trakt_rating: float | None = Field(default=None, ge=0, le=10)
    sort: UnwatchedSort = "rating"
    limit: int = Field(default=UNWATCHED_DEFAULT_LIMIT, ge=1, le=UNWATCHED_MAX_LIMIT)

    @field_validator("genres_include", "genres_exclude")
    @classmethod
    def _lowercase_genres(cls, genres: list[str]) -> list[str]:
        return [genre.strip().lower() for genre in genres if genre.strip()]

    @model_validator(mode="after")
    def _runtime_range_is_ordered(self) -> Self:
        if (
            self.min_runtime is not None
            and self.max_runtime is not None
            and self.min_runtime > self.max_runtime
        ):
            raise ValueError("min_runtime must not exceed max_runtime")
        return self


class UnwatchedSelection(BaseModel):
    """Result of the set difference, with counts for the header."""

    collected: int = Field(ge=0, description="Movies in the collection")
    watched: int = Field(ge=0, description="Movies in the watched set")
    matching: int = Field(ge=0, description="Unwatched movies passing the filters")
    items: list[CollectionItem] = Field(description="The movies to show")
