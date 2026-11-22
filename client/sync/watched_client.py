"""Sync watched functionality for Trakt."""

from config.endpoints.sync import SYNC_ENDPOINTS
from models.sync.watched import WatchedMovieItem
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors

from .all_pages_client import SyncAllPagesClient


class SyncWatchedClient(SyncAllPagesClient):
    """Client for reading what the user has watched."""

    @handle_api_errors
    async def get_watched_movies(self) -> list[WatchedMovieItem]:
        """Fetch every movie the user has watched, following every page.

        Raises:
            AuthenticationRequiredError: If not authenticated
            RuntimeError: If the page-count guard stopped the fetch, because a
                partial watched list would give wrong answers
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="access your watched movies")

        endpoint = SYNC_ENDPOINTS["sync_watched_get"].replace(":type", "movies")
        result = await self._fetch_all_pages(endpoint, response_type=WatchedMovieItem)
        if result.truncated:
            raise RuntimeError(
                f"Watched movies stopped after {result.pages_fetched} pages; "
                + "the list would be incomplete."
            )
        return result.items
