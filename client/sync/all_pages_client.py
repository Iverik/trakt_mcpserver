"""Shared fetch-every-page helper for sync reads."""

from dataclasses import dataclass, field
from typing import Any

from config.api import MAX_COLLECTION_PAGES, MAX_SYNC_PAGE_SIZE

from ..auth import AuthClient


@dataclass(frozen=True)
class AllPages[T]:
    """Every item read across pages, and whether the page guard cut it short."""

    items: list[T] = field(default_factory=lambda: list[T]())
    pages_fetched: int = 0
    truncated: bool = False


class SyncAllPagesClient(AuthClient):
    """Base for sync clients that must read a whole list, not a capped sample."""

    async def _fetch_all_pages[T](
        self,
        endpoint: str,
        *,
        response_type: type[T],
        params: dict[str, Any] | None = None,
    ) -> AllPages[T]:
        """Follow every page of ``endpoint``, with no item cap.

        Only a page-count guard (MAX_COLLECTION_PAGES) stops a runaway loop,
        and it is reported on the result. A response without pagination
        headers counts as one complete page.
        """
        items: list[T] = []
        page = 1
        pages_fetched = 0

        while pages_fetched < MAX_COLLECTION_PAGES:
            page_params = {**(params or {}), "page": page, "limit": MAX_SYNC_PAGE_SIZE}
            response = await self._make_paginated_request(
                endpoint, response_type=response_type, params=page_params
            )
            pages_fetched += 1
            items.extend(response.data)

            next_page = response.pagination.next_page()
            if next_page is None:
                return AllPages(items=items, pages_fetched=pages_fetched)
            page = next_page

        return AllPages(items=items, pages_fetched=pages_fetched, truncated=True)
