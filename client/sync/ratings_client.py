"""Sync ratings functionality for Trakt."""

from typing import TYPE_CHECKING, Literal

from config.api import MAX_API_PAGE_SIZE
from config.endpoints.sync import SYNC_ENDPOINTS
from models.sync.ratings import (
    SyncRatingsSummary,
    TraktSyncRating,
    TraktSyncRatingsRequest,
)
from models.types.pagination import PaginatedResponse, PaginationParams
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import handle_api_errors

from ..auth import AuthClient

if TYPE_CHECKING:
    from models.types.common import JSONValue


class SyncRatingsClient(AuthClient):
    """Client for sync ratings operations."""

    @staticmethod
    def _ratings_endpoint(
        rating_type: Literal["movies", "shows", "seasons", "episodes"],
        rating: int | None,
    ) -> str:
        """Build the ratings endpoint, using the rating path filter if given."""
        if rating is not None:
            return (
                SYNC_ENDPOINTS["sync_ratings_get"]
                .replace(":type", rating_type)
                .replace(":rating", str(rating))
            )
        return SYNC_ENDPOINTS["sync_ratings_get_type"].replace(":type", rating_type)

    @handle_api_errors
    async def get_sync_ratings(
        self,
        rating_type: Literal["movies", "shows", "seasons", "episodes"],
        rating: int | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResponse[TraktSyncRating]:
        """Get user's personal ratings from sync API with pagination.

        Args:
            rating_type: Type of ratings to get (movies, shows, seasons, episodes)
            rating: Optional specific rating to filter by (1-10)
            pagination: Optional pagination parameters (page, limit)

        Returns:
            Paginated response with user's ratings and pagination metadata

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="access your personal ratings")

        endpoint = self._ratings_endpoint(rating_type, rating)

        # Build query parameters with pagination
        params: dict[str, int] = {}
        if pagination:
            params.update(pagination.to_query_params())

        return await self._make_paginated_request(
            endpoint, response_type=TraktSyncRating, params=params
        )

    @handle_api_errors
    async def get_all_sync_ratings(
        self,
        rating_type: Literal["movies", "shows", "seasons", "episodes"],
        rating: int | None = None,
    ) -> list[TraktSyncRating]:
        """Get every rating of a type, following pagination to the last page.

        Unlike get_sync_ratings, this is never truncated, so callers can
        filter and count over the full set.

        Args:
            rating_type: Type of ratings to get (movies, shows, seasons, episodes)
            rating: Optional specific rating to filter by (1-10)

        Returns:
            All of the user's ratings of that type

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="access your personal ratings")

        return await self.auto_paginate(
            self._ratings_endpoint(rating_type, rating),
            response_type=TraktSyncRating,
            params={"limit": MAX_API_PAGE_SIZE},
        )

    @handle_api_errors
    async def add_sync_ratings(
        self, request: TraktSyncRatingsRequest
    ) -> SyncRatingsSummary:
        """Add new ratings for the authenticated user.

        Args:
            request: Rating items to add with ratings data

        Returns:
            Summary of added ratings with counts and any not found items

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="add personal ratings")

        # Convert request to dict, excluding None values
        # Use mode='json' to serialize datetime fields to ISO 8601 strings
        data: dict[str, JSONValue] = request.model_dump(mode="json", exclude_none=True)

        return await self._post_typed_request(
            SYNC_ENDPOINTS["sync_ratings_add"], data, response_type=SyncRatingsSummary
        )

    @handle_api_errors
    async def remove_sync_ratings(
        self, request: TraktSyncRatingsRequest
    ) -> SyncRatingsSummary:
        """Remove ratings for the authenticated user.

        Args:
            request: Rating items to remove (should not include rating values,
                just item identification)

        Returns:
            Summary of removed ratings with counts and any not found items

        Raises:
            AuthenticationRequiredError: If not authenticated
        """
        if not await self.ensure_authenticated():
            raise AuthenticationRequiredError(action="remove personal ratings")

        # Convert request to dict, excluding None values
        # Use mode='json' to serialize datetime fields to ISO 8601 strings
        data: dict[str, JSONValue] = request.model_dump(mode="json", exclude_none=True)

        # Use POST method for sync ratings removal
        return await self._post_typed_request(
            SYNC_ENDPOINTS["sync_ratings_remove"],
            data,
            response_type=SyncRatingsSummary,
        )
