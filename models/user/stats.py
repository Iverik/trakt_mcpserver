"""User stats models for the Trakt MCP server."""

from pydantic import BaseModel


class UserStatsPlayed(BaseModel):
    """Movie or episode counters from the user stats response."""

    ratings: int | None = None
    comments: int | None = None
    watched: int | None = None
    collected: int | None = None
    plays: int | None = None
    minutes: int | None = None


class UserStatsShows(BaseModel):
    """Show counters from the user stats response."""

    ratings: int | None = None
    comments: int | None = None
    watched: int | None = None
    collected: int | None = None


class UserStatsSeasons(BaseModel):
    """Season counters from the user stats response."""

    ratings: int | None = None
    comments: int | None = None


class UserStatsNetwork(BaseModel):
    """Social counters from the user stats response."""

    friends: int | None = None
    followers: int | None = None
    following: int | None = None


class UserStatsRatings(BaseModel):
    """Rating totals and the 1 to 10 distribution."""

    total: int | None = None
    distribution: dict[str, float] | None = None


class UserStatsProgress(BaseModel):
    """Show progress counters (null for some accounts)."""

    started: int | None = None
    finished: int | None = None
    dropped: int | None = None


class UserStats(BaseModel):
    """Response of GET /users/{id}/stats."""

    movies: UserStatsPlayed | None = None
    shows: UserStatsShows | None = None
    seasons: UserStatsSeasons | None = None
    episodes: UserStatsPlayed | None = None
    network: UserStatsNetwork | None = None
    ratings: UserStatsRatings | None = None
    progress: UserStatsProgress | None = None
    lists: int | None = None
    list_comments: int | None = None
    total_minutes: int | None = None
    total_plays: int | None = None
