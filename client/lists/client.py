"""Personal lists functionality for Trakt."""

from client.auth import AuthClient
from client.endpoints import build_endpoint
from client.validation import validate_media_id
from config.api import MAX_API_PAGE_SIZE
from config.endpoints import TRAKT_ENDPOINTS, EndpointKey
from models.lists import (
    TraktCreateListRequest,
    TraktListItem,
    TraktListItemsRequest,
    TraktListItemsSummary,
    TraktUserList,
)
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors


class ListsClient(AuthClient):
    """Client for the authenticated user's personal lists."""

    @handle_api_errors
    async def get_user_lists(self) -> list[TraktUserList]:
        """Fetch every personal list of the authenticated user.

        Follows all pages; stops with an error at the auto-pagination safety cap.

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="fetch your lists")

        return await self.auto_paginate(
            TRAKT_ENDPOINTS["user_lists"],
            response_type=TraktUserList,
            params={"limit": MAX_API_PAGE_SIZE},
        )

    @handle_api_errors
    async def create_user_list(self, request: TraktCreateListRequest) -> TraktUserList:
        """Create a personal list.

        Args:
            request: Name plus optional description and privacy

        Returns:
            The created list

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="create a list")

        data = request.model_dump(mode="json", exclude_none=True)
        response = await self._post_request(TRAKT_ENDPOINTS["user_lists"], data)
        return TraktUserList.model_validate(response)

    @handle_api_errors
    async def get_user_list_items(self, list_id: str) -> list[TraktListItem]:
        """Fetch every item on one of the authenticated user's lists.

        Follows all pages; stops with an error at the auto-pagination safety cap.

        Args:
            list_id: Trakt list ID or slug

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="fetch your list items")

        return await self.auto_paginate(
            self._items_endpoint("user_list_items", list_id),
            response_type=TraktListItem,
            params={"limit": MAX_API_PAGE_SIZE},
        )

    @handle_api_errors
    async def add_user_list_items(
        self, list_id: str, request: TraktListItemsRequest
    ) -> TraktListItemsSummary:
        """Add movies or shows to a personal list.

        Args:
            list_id: Trakt list ID or slug
            request: Items to add

        Returns:
            Trakt's added, existing and not_found summary

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="add items to your list")

        return await self._post_items("user_list_items", list_id, request)

    @handle_api_errors
    async def remove_user_list_items(
        self, list_id: str, request: TraktListItemsRequest
    ) -> TraktListItemsSummary:
        """Remove movies or shows from a personal list.

        Args:
            list_id: Trakt list ID or slug
            request: Items to remove

        Returns:
            Trakt's deleted and not_found summary

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="remove items from your list")

        return await self._post_items("user_list_items_remove", list_id, request)

    @staticmethod
    def _items_endpoint(key: EndpointKey, list_id: str) -> str:
        return build_endpoint(key, list_id=validate_media_id(list_id, "list_id"))

    async def _post_items(
        self, key: EndpointKey, list_id: str, request: TraktListItemsRequest
    ) -> TraktListItemsSummary:
        data = request.model_dump(mode="json", exclude_none=True)
        response = await self._post_request(self._items_endpoint(key, list_id), data)
        return TraktListItemsSummary.model_validate(response)
