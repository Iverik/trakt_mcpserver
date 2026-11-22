"""Sync collection functionality for Trakt."""

from typing import Literal

from config.endpoints.sync import SYNC_ENDPOINTS
from models.sync.collection import CollectionFetchResult, CollectionItem
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors

from .all_pages_client import SyncAllPagesClient


class SyncCollectionClient(SyncAllPagesClient):
    """Client for reading the user's collection."""

    @handle_api_errors
    async def get_collection(
        self,
        collection_type: Literal["movies", "shows"],
        include_metadata: bool = False,
        include_details: bool = False,
    ) -> CollectionFetchResult:
        """Fetch the user's entire collection of one type, following every page.

        Unlike the list tools, this applies no item cap: a truncated collection
        gives wrong answers. Only a page-count guard stops a runaway loop, and
        it is reported on the result.

        Args:
            collection_type: Collection to fetch (movies or shows)
            include_metadata: Send ``extended=metadata`` to include media type,
                resolution, HDR, audio, audio channels and 3D
            include_details: Send ``extended=full`` so movies carry runtime,
                genres, community rating and release date. Combined with
                include_metadata as ``extended=full,metadata``

        Returns:
            Every collected item, the number of pages read, and whether the
            page-count guard cut the fetch short

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="access your collection")

        endpoint = SYNC_ENDPOINTS["sync_collection_get"].replace(
            ":type", collection_type
        )
        params: dict[str, str] = {}
        extended = [
            name
            for name, wanted in (
                ("full", include_details),
                ("metadata", include_metadata),
            )
            if wanted
        ]
        if extended:
            params["extended"] = ",".join(extended)

        result = await self._fetch_all_pages(
            endpoint, response_type=CollectionItem, params=params
        )
        return CollectionFetchResult(
            items=result.items,
            pages_fetched=result.pages_fetched,
            truncated=result.truncated,
        )
