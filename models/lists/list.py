"""Personal list models for the Trakt MCP server."""

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from models.movies.movie import TraktMovie
from models.shows.episode import TraktEpisode
from models.shows.show import TraktShow
from models.types.ids import TraktIds

type ListPrivacy = Literal["private", "link", "friends", "public"]
type ListItemType = Literal["movies", "shows"]


class TraktCreateListRequest(BaseModel):
    """Request body for creating a personal list."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Name of the list")
    description: str | None = Field(default=None, description="List description")
    privacy: ListPrivacy | None = Field(
        default=None, description="Visibility; Trakt defaults to private"
    )


class TraktListItemRef(BaseModel):
    """A movie or show reference inside an add/remove request."""

    title: str | None = None
    year: int | None = Field(default=None, gt=1800)
    ids: TraktIds | None = None


class TraktListItemsRequest(BaseModel):
    """Request body for adding items to, or removing them from, a list.

    Exactly one of movies or shows must be provided and non-empty.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    movies: list[TraktListItemRef] | None = Field(default=None, min_length=1)
    shows: list[TraktListItemRef] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_exactly_one_collection(self) -> "TraktListItemsRequest":
        """Require exactly one non-empty collection."""
        present = [name for name in ("movies", "shows") if getattr(self, name)]
        if not present:
            raise PydanticCustomError(
                "lists.collection_missing",
                "Either movies or shows must be provided",
            )
        if len(present) > 1:
            raise PydanticCustomError(
                "lists.multiple_collections",
                "Only one of movies or shows is allowed per request",
            )
        return self


class TraktUserList(BaseModel):
    """A personal list as returned by Trakt."""

    name: str
    description: str | None = None
    privacy: str = "private"
    share_link: str | None = None
    type: str | None = None
    display_numbers: bool | None = None
    allow_comments: bool | None = None
    sort_by: str | None = None
    sort_how: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    item_count: int = 0
    comment_count: int = 0
    likes: int = 0
    ids: TraktIds


class TraktListSeason(BaseModel):
    """A season entry inside a list item."""

    number: int
    ids: TraktIds | None = None


class TraktListItem(BaseModel):
    """One entry on a personal list."""

    rank: int | None = None
    id: int | None = None
    listed_at: str | None = None
    notes: str | None = None
    type: Literal["movie", "show", "season", "episode"]
    movie: TraktMovie | None = None
    show: TraktShow | None = None
    season: TraktListSeason | None = None
    episode: TraktEpisode | None = None


class TraktListSummaryCount(BaseModel):
    """Per-type counts in an add/remove response."""

    movies: int = Field(default=0, ge=0)
    shows: int = Field(default=0, ge=0)
    seasons: int = Field(default=0, ge=0)
    episodes: int = Field(default=0, ge=0)


class TraktListNotFound(BaseModel):
    """Items Trakt could not match, by type."""

    movies: Annotated[list[TraktListItemRef], Field(default_factory=list)]
    shows: Annotated[list[TraktListItemRef], Field(default_factory=list)]
    seasons: Annotated[list[TraktListItemRef], Field(default_factory=list)]
    episodes: Annotated[list[TraktListItemRef], Field(default_factory=list)]


class TraktListState(BaseModel):
    """The list's state after an add/remove."""

    updated_at: str | None = None
    item_count: int | None = None


class TraktListItemsSummary(BaseModel):
    """Response to adding items to, or removing them from, a list.

    Adds report ``added`` and ``existing``; removals report ``deleted``.
    """

    added: TraktListSummaryCount | None = None
    existing: TraktListSummaryCount | None = None
    deleted: TraktListSummaryCount | None = None
    not_found: TraktListNotFound = Field(
        default_factory=lambda: TraktListNotFound(
            movies=[], shows=[], seasons=[], episodes=[]
        )
    )
    list: TraktListState | None = None
