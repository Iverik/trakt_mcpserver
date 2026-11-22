"""Process-wide caches for the user's synced Trakt data."""

from typing import Final

from config.api import SYNC_CACHE_TTL_SECONDS
from models.sync.base import TraktSyncRating
from models.sync.collection import CollectionFetchResult
from models.sync.watched import WatchedMovieItem
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
