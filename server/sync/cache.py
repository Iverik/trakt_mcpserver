"""Process-wide caches for the user's synced Trakt data."""

from dataclasses import dataclass
from typing import Final

from client.pool import get_client
from client.sync import SyncClient
from config.api import SYNC_CACHE_TTL_SECONDS
from models.sync.base import TraktSyncRating
from models.sync.collection import CollectionFetchResult
from models.sync.watched import WatchedMovieItem
from server.base import ToolErrors
from utils.cache.ttl_cache import TTLCache

COLLECTED_MOVIES_CACHE: Final[TTLCache[CollectionFetchResult]] = TTLCache(
    SYNC_CACHE_TTL_SECONDS
)
WATCHED_MOVIES_CACHE: Final[TTLCache[list[WatchedMovieItem]]] = TTLCache(
    SYNC_CACHE_TTL_SECONDS
)
RATED_MOVIES_CACHE: Final[TTLCache[list[TraktSyncRating]]] = TTLCache(
    SYNC_CACHE_TTL_SECONDS
)


async def load_collected_movies() -> CollectionFetchResult:
    """Fetch the whole movie collection with runtime, genres, rating, metadata."""
    result = await get_client(SyncClient).get_collection(
        "movies", include_metadata=True, include_details=True
    )
    if isinstance(result, str):
        raise ToolErrors.handle_api_string_error(
            resource_type="user_movies_collection",
            resource_id="user_collection_movies",
            error_message=result,
            operation="load_collected_movies",
        )
    return result


@dataclass(frozen=True)
class CollectedMovieIds:
    """Trakt ids of the collected movies, and whether the read was cut short."""

    ids: frozenset[int]
    truncated: bool


async def collected_movie_ids() -> CollectedMovieIds:
    """Trakt ids of every collected movie, from the shared collection cache."""
    collected = await COLLECTED_MOVIES_CACHE.get_or_load(load_collected_movies)
    ids = frozenset(
        item.movie.ids.trakt
        for item in collected.items
        if item.movie is not None and item.movie.ids.trakt is not None
    )
    return CollectedMovieIds(ids=ids, truncated=collected.truncated)


def invalidate_watched_cache() -> None:
    """Drop the watched snapshot after the watch history changed."""
    WATCHED_MOVIES_CACHE.invalidate()


def invalidate_ratings_cache() -> None:
    """Drop the movie ratings snapshot after ratings changed."""
    RATED_MOVIES_CACHE.invalidate()


def invalidate_all_caches() -> None:
    """Drop every cached snapshot."""
    COLLECTED_MOVIES_CACHE.invalidate()
    WATCHED_MOVIES_CACHE.invalidate()
    RATED_MOVIES_CACHE.invalidate()
