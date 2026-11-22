"""Unified sync client that combines all sync functionality."""

from .collection_client import SyncCollectionClient
from .history_client import SyncHistoryClient
from .ratings_client import SyncRatingsClient
from .watched_client import SyncWatchedClient
from .watchlist_client import SyncWatchlistClient


class SyncClient(
    SyncRatingsClient,
    SyncWatchlistClient,
    SyncHistoryClient,
    SyncCollectionClient,
    SyncWatchedClient,
):
    """Unified client for all sync-related operations.

    Combines functionality from:
    - SyncRatingsClient: get_sync_ratings(), add_sync_ratings(), remove_sync_ratings()
    - SyncWatchlistClient: get_sync_watchlist(), add_sync_watchlist(),
      remove_sync_watchlist()
    - SyncHistoryClient: get_history(), add_to_history(), remove_from_history()
    - SyncCollectionClient: get_collection()
    - SyncWatchedClient: get_watched_movies()

    Note: Inherits OAuth authentication handling from AuthClient through parent clients.
    All sync operations require user authentication to access personal data.
    """

    pass
