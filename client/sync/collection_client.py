"""Sync collection functionality for Trakt."""

from typing import Literal

from config.api import MAX_API_PAGE_SIZE, MAX_COLLECTION_PAGES
from config.endpoints.sync import SYNC_ENDPOINTS
from models.sync.collection import CollectionFetchResult, CollectionItem
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors

from ..auth import AuthClient


class SyncCollectionClient(AuthClient):
    """Client for reading the user's collection."""

    @handle_api_errors
    async def get_collection(
        self,
        collection_type: Literal["movies", "shows"],
        include_metadata: bool = False,
    ) -> CollectionFetchResult:
        """Fetch the user's entire collection of one type, following every page.

        Unlike the list tools, this applies no item cap: a truncated collection
        gives wrong answers. Only a page-count guard (MAX_COLLECTION_PAGES)
        stops a runaway loop, and it is reported on the result. A response
        without pagination headers counts as one complete page.

        Args:
            collection_type: Collection to fetch (movies or shows)
            include_metadata: Send ``extended=metadata`` to include media type,
                resolution, HDR, audio, audio channels and 3D

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
        items: list[CollectionItem] = []
        page = 1
        pages_fetched = 0

        while pages_fetched < MAX_COLLECTION_PAGES:
            params: dict[str, str | int] = {"page": page, "limit": MAX_API_PAGE_SIZE}
            if include_metadata:
                params["extended"] = "metadata"
            response = await self._make_paginated_request(
                endpoint, response_type=CollectionItem, params=params
            )
            pages_fetched += 1
            items.extend(response.data)

            next_page = response.pagination.next_page()
            if next_page is None:
                return CollectionFetchResult(items=items, pages_fetched=pages_fetched)
            page = next_page

        return CollectionFetchResult(
            items=items, pages_fetched=pages_fetched, truncated=True
        )
