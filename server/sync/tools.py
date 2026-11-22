"""Sync tools for the Trakt MCP server."""

import logging
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, ClassVar, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator, model_validator

from client.pool import get_client
from client.shows.seasons import ShowSeasonsClient
from client.sync.client import SyncClient
from config.api import DEFAULT_LIMIT, UNWATCHED_DEFAULT_LIMIT, UNWATCHED_MAX_LIMIT
from config.api.sync import RATING_MAX, RATING_MIN, RATINGS_SUMMARY_RECENT_COUNT
from config.mcp.descriptions import (
    COLLECTION_INCLUDE_METADATA_DESCRIPTION,
    COLLECTION_TYPE_DESCRIPTION,
    HISTORY_END_AT_DESCRIPTION,
    HISTORY_ITEM_ID_DESCRIPTION,
    HISTORY_ITEMS_DESCRIPTION,
    HISTORY_QUERY_TYPE_DESCRIPTION,
    HISTORY_REMOVE_ITEMS_DESCRIPTION,
    HISTORY_START_AT_DESCRIPTION,
    HISTORY_TYPE_DESCRIPTION,
    MAX_RATING_DESCRIPTION,
    MIN_RATING_DESCRIPTION,
    PAGE_DESCRIPTION,
    RATED_AFTER_DESCRIPTION,
    RATING_FILTER_DESCRIPTION,
    RATING_ITEMS_DESCRIPTION,
    RATING_REMOVE_ITEMS_DESCRIPTION,
    RATING_TYPE_DESCRIPTION,
    RATINGS_LIMIT_DESCRIPTION,
    RATINGS_SUMMARY_DESCRIPTION,
    SORT_DIRECTION_DESCRIPTION,
    UNWATCHED_GENRES_EXCLUDE_DESCRIPTION,
    UNWATCHED_GENRES_INCLUDE_DESCRIPTION,
    UNWATCHED_LIMIT_DESCRIPTION,
    UNWATCHED_MAX_RUNTIME_DESCRIPTION,
    UNWATCHED_MIN_RATING_DESCRIPTION,
    UNWATCHED_MIN_RUNTIME_DESCRIPTION,
    UNWATCHED_SORT_DESCRIPTION,
    UNWATCHED_TYPE_DESCRIPTION,
    WATCHLIST_ITEMS_DESCRIPTION,
    WATCHLIST_REMOVE_ITEMS_DESCRIPTION,
    WATCHLIST_SORT_BY_DESCRIPTION,
    WATCHLIST_TYPE_DESCRIPTION,
    WATCHLIST_TYPE_REQUIRED_DESCRIPTION,
)
from models.formatters.sync_collection import SyncCollectionFormatters
from models.formatters.sync_history import SyncHistoryFormatters
from models.formatters.sync_ratings import SyncRatingsFormatters
from models.formatters.sync_unwatched import SyncUnwatchedFormatters
from models.formatters.sync_watchlist import SyncWatchlistFormatters
from models.sync.collection import CollectionFetchResult
from models.sync.history import (
    HistoryQueryParams,
    HistorySummary,
    HistorySummaryCount,
    TraktHistoryItem,
    TraktHistoryRequest,
)
from models.sync.ratings import (
    TraktSyncRating,
    TraktSyncRatingItem,
    TraktSyncRatingsRequest,
)
from models.sync.unwatched import UnwatchedQuery, UnwatchedSort
from models.sync.watched import WatchedMovieItem
from models.sync.watchlist import (
    TraktSyncWatchlistItem,
    TraktSyncWatchlistRequest,
)
from models.types.ids import TraktIds
from models.types.pagination import (
    PaginatedResponse,
    PaginationMetadata,
    PaginationParams,
)
from models.types.timestamps import WatchedAtValue
from server.base import IdentifierValidatorMixin, ToolErrors
from server.sync.cache import (
    COLLECTED_MOVIES_CACHE,
    WATCHED_MOVIES_CACHE,
    invalidate_watched_cache,
)
from server.sync.unwatched_selection import select_unwatched
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import InvalidParamsError, MCPError, handle_api_errors_func

logger = logging.getLogger("trakt_mcp")


def _unwrap_or_raise[T](
    result: T | str,
    *,
    resource_type: str,
    resource_id: str,
    operation: str,
) -> T:
    """Return ``result`` as ``T``, or raise a structured error if it is a string.

    Trakt API clients still surface some failures as error strings instead of
    raising. This helper folds the recurring guard-and-raise shape into a
    single call, preserving pyright narrowing on the success path.
    """
    if isinstance(result, str):
        raise ToolErrors.handle_api_string_error(
            resource_type=resource_type,
            resource_id=resource_id,
            error_message=result,
            operation=operation,
        )
    return result


def _aggregate_summary(
    target: HistorySummary, source: HistorySummary, operation: str
) -> None:
    """Aggregate counts from source into target summary in-place.

    Args:
        target: Summary to accumulate into
        source: Summary with new counts to add
        operation: "added" or "deleted" — which count field to aggregate
    """
    src_counts = getattr(source, operation, None)
    if src_counts is None:
        return

    tgt_counts = getattr(target, operation, None)
    if tgt_counts is None:
        tgt_counts = HistorySummaryCount()
        setattr(target, operation, tgt_counts)

    for field in ("movies", "shows", "seasons", "episodes"):
        new_val = getattr(tgt_counts, field) + getattr(src_counts, field)
        setattr(tgt_counts, field, new_val)

    # Aggregate not_found lists
    if source.not_found:
        for field in ("movies", "shows", "seasons", "episodes"):
            getattr(target.not_found, field).extend(getattr(source.not_found, field))


async def _get_show_season_ids(show_id: str) -> list[int]:
    """Fetch Trakt season IDs for a show, excluding specials (season 0).

    Args:
        show_id: Trakt show ID or slug

    Returns:
        List of Trakt season IDs
    """
    seasons_client = get_client(ShowSeasonsClient)
    seasons = await seasons_client.get_seasons(show_id)
    if isinstance(seasons, str):
        return []
    return [s["ids"]["trakt"] for s in seasons if s["number"] > 0]


def _resolve_show_id(item: TraktHistoryItem) -> str | None:
    """Return the item's Trakt ID, falling back to its slug, else None."""
    if not item.ids:
        return None
    if item.ids.trakt:
        return str(item.ids.trakt)
    return item.ids.slug


async def _send_show_as_single(
    item: TraktHistoryItem,
    client_method: Callable[[TraktHistoryRequest], Awaitable[HistorySummary | str]],
    show_id: str | None,
    operation: str,
    combined: HistorySummary,
    *,
    suppress_cause: bool = False,
) -> None:
    """Send a single show item as its own history request and aggregate the result.

    Raises an MCPError if the API returns a string error. ``suppress_cause``
    raises with ``from None`` so an in-flight ``except`` doesn't chain its
    caught exception onto the user-facing error.
    """
    request = TraktHistoryRequest(shows=[item])
    result = await client_method(request)
    if isinstance(result, str):
        error = ToolErrors.handle_api_string_error(
            resource_type="sync_history_show",
            resource_id=show_id or "unknown",
            error_message=result,
            operation=operation,
        )
        if suppress_cause:
            raise error from None
        raise error
    _aggregate_summary(combined, result, operation)


async def _batch_show_history_op(
    client_method: Callable[[TraktHistoryRequest], Awaitable[HistorySummary | str]],
    show_items: list[TraktHistoryItem],
    operation: str,
) -> HistorySummary:
    """Execute a history add/remove for shows by batching per-season.

    Large shows (100+ episodes) cause Trakt API 504 gateway timeouts.
    This sends one request per season to keep each call small.

    Args:
        client_method: The client add_to_history or remove_from_history method
        show_items: List of show items to process
        operation: "added" or "deleted" — for aggregating the correct counts

    Returns:
        Aggregated HistorySummary across all season batches
    """
    combined = HistorySummary()

    for item in show_items:
        show_id = _resolve_show_id(item)

        if show_id is None:
            await _send_show_as_single(
                item, client_method, show_id, operation, combined
            )
            continue

        try:
            season_ids = await _get_show_season_ids(show_id)
        except Exception:
            logger.warning(
                "Failed to fetch seasons for show %s, sending as single request",
                show_id,
            )
            await _send_show_as_single(
                item,
                client_method,
                show_id,
                operation,
                combined,
                suppress_cause=True,
            )
            continue

        if not season_ids:
            logger.warning(
                "No seasons found for show %s, sending as single request",
                show_id,
            )
            await _send_show_as_single(
                item, client_method, show_id, operation, combined
            )
            continue

        # Process seasons sequentially to avoid Trakt API rate-limit pressure
        failed_seasons: list[int] = []
        for season_id in season_ids:
            request = TraktHistoryRequest(
                seasons=[
                    TraktHistoryItem(
                        ids=TraktIds(trakt=season_id),
                        watched_at=item.watched_at,
                    )
                ]
            )
            try:
                result = await client_method(request)
                if isinstance(result, str):
                    raise ToolErrors.handle_api_string_error(
                        resource_type="sync_history_season",
                        resource_id=str(season_id),
                        error_message=result,
                        operation=operation,
                    )
                _aggregate_summary(combined, result, operation)
            except MCPError:
                raise
            except Exception:
                logger.warning(
                    "Failed to process season %s for show %s",
                    season_id,
                    show_id,
                )
                failed_seasons.append(season_id)

        if failed_seasons:
            logger.warning(
                "Show %s: %d of %d seasons failed",
                show_id,
                len(failed_seasons),
                len(season_ids),
            )

    return combined


WatchlistSortField = Literal[
    "rank",
    "added",
    "title",
    "released",
    "runtime",
    "popularity",
    "percentage",
    "votes",
]

# Type alias for tool handlers
ToolHandler = Callable[..., Awaitable[str]]


# Pydantic models for parameter validation
class UserRatingsParams(BaseModel):
    """Parameters for fetching user ratings."""

    rating_type: Literal["movies", "shows", "seasons", "episodes"] = "movies"
    rating: int | None = Field(
        default=None,
        ge=RATING_MIN,
        le=RATING_MAX,
        description="Optional specific rating to filter by",
    )
    page: int | None = Field(
        default=None, ge=1, description="Optional page number for pagination (1-based)"
    )
    min_rating: int | None = Field(
        default=None, ge=RATING_MIN, le=RATING_MAX, description="Minimum rating"
    )
    max_rating: int | None = Field(
        default=None, ge=RATING_MIN, le=RATING_MAX, description="Maximum rating"
    )
    rated_after: datetime | None = Field(
        default=None, description="Only ratings made on or after this instant (UTC)"
    )
    limit: int | None = Field(default=None, ge=1, description="Maximum ratings")
    summary: bool = False

    @field_validator(
        "rating", "page", "min_rating", "max_rating", "limit", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    @field_validator("rated_after", mode="before")
    @classmethod
    def _parse_rated_after(cls, v: object) -> object:
        """Accept an ISO 8601 date or datetime; a missing zone means UTC."""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                parsed = datetime.fromisoformat(v)
            except ValueError as e:
                raise ValueError(
                    f"rated_after must be an ISO 8601 date or datetime, got {v!r}"
                ) from e
        elif isinstance(v, datetime):
            parsed = v
        else:
            raise ValueError("rated_after must be an ISO 8601 date or datetime string")
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

    @model_validator(mode="after")
    def _validate_combinations(self) -> "UserRatingsParams":
        if (
            self.min_rating is not None
            and self.max_rating is not None
            and self.min_rating > self.max_rating
        ):
            raise ValueError(
                f"min_rating ({self.min_rating}) must not exceed "
                + f"max_rating ({self.max_rating})"
            )
        if self.rating is not None and (
            self.min_rating is not None or self.max_rating is not None
        ):
            raise ValueError("rating cannot be combined with min_rating or max_rating")
        if self.page is not None and self.uses_client_side_view:
            raise ValueError(
                "page cannot be combined with min_rating, max_rating, "
                + "rated_after, limit or summary"
            )
        return self

    @property
    def uses_client_side_view(self) -> bool:
        """True when any filter, limit or summary asks for the full-set view."""
        return (
            self.min_rating is not None
            or self.max_rating is not None
            or self.rated_after is not None
            or self.limit is not None
            or self.summary
        )

    @property
    def exact_rating(self) -> int | None:
        """The single rating value to filter by, if the inputs pin one."""
        if self.rating is not None:
            return self.rating
        if self.min_rating is not None and self.min_rating == self.max_rating:
            return self.min_rating
        return None


class UserRatingRequestItem(IdentifierValidatorMixin):
    """Single rating item for add/remove operations."""

    _identifier_error_prefix: ClassVar[str] = "Rating item"

    rating: int = Field(ge=1, le=10, description="Rating from 1 to 10")


class UserRatingIdentifier(IdentifierValidatorMixin):
    """Rating item identifier for removal operations (no rating required)."""

    _identifier_error_prefix: ClassVar[str] = "Rating item"


class UserRatingRequest(BaseModel):
    """Parameters for adding/removing user ratings."""

    rating_type: Literal["movies", "shows", "seasons", "episodes"]
    items: list[UserRatingRequestItem] = Field(
        min_length=1, description="List of items to rate"
    )


class UserWatchlistParams(BaseModel):
    """Parameters for fetching user watchlist."""

    watchlist_type: Literal["all", "movies", "shows", "seasons", "episodes"] = "all"
    sort_by: WatchlistSortField = "rank"
    sort_how: Literal["asc", "desc"] = "asc"
    page: int | None = Field(
        default=None, ge=1, description="Optional page number for pagination (1-based)"
    )

    @field_validator("page", mode="before")
    @classmethod
    def _validate_page(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v


class UserWatchlistRequestItem(IdentifierValidatorMixin):
    """Single watchlist item for add operations (with optional notes)."""

    _identifier_error_prefix: ClassVar[str] = "Watchlist item"

    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Optional notes (VIP only, 500 char max)",
    )

    @field_validator("notes", mode="before")
    @classmethod
    def _strip_notes(cls, v: object) -> object:
        """Strip whitespace from notes field."""
        return v.strip() if isinstance(v, str) else v


class UserWatchlistIdentifier(IdentifierValidatorMixin):
    """Watchlist item identifier for removal operations (no notes)."""

    _identifier_error_prefix: ClassVar[str] = "Watchlist item"


class UserWatchlistRequest(BaseModel):
    """Parameters for adding/removing user watchlist items."""

    watchlist_type: Literal["movies", "shows", "seasons", "episodes"]
    items: list[UserWatchlistRequestItem] = Field(
        min_length=1, description="List of items to add to watchlist"
    )


def _select_ratings(
    ratings: list[TraktSyncRating], params: UserRatingsParams
) -> list[TraktSyncRating]:
    """Apply rating-range and date filters, newest rated first."""
    low = params.min_rating if params.min_rating is not None else RATING_MIN
    high = params.max_rating if params.max_rating is not None else RATING_MAX
    selected = [
        r
        for r in ratings
        if low <= r.rating <= high
        and (params.rated_after is None or r.rated_at >= params.rated_after)
    ]
    selected.sort(key=lambda r: r.rated_at, reverse=True)
    return selected


@handle_api_errors_func
async def fetch_user_ratings(
    rating_type: Literal["movies", "shows", "seasons", "episodes"] = "movies",
    rating: int | None = None,
    page: int | None = None,
    min_rating: int | None = None,
    max_rating: int | None = None,
    rated_after: str | None = None,
    limit: int | None = None,
    summary: bool = False,
) -> str:
    """Fetch authenticated user's personal ratings from Trakt.

    Args:
        rating_type: Type of ratings to fetch (movies, shows, seasons, episodes)
        rating: Optional specific rating to filter by (1-10)
        page: Optional page number for pagination (1-based)
        min_rating: Only ratings of at least this value (1-10)
        max_rating: Only ratings of at most this value (1-10)
        rated_after: Only ratings made on or after this ISO 8601 date or datetime
        limit: Maximum number of ratings to return, most recently rated first
        summary: Return counts per rating value and the most recent ratings

    Returns:
        User's personal ratings formatted as markdown. When 'page' is None,
        only the first page is retrieved (see pagination info in the output).
        With any of min_rating, max_rating, rated_after, limit or summary, every
        page is fetched and the filters, limit and counts apply to the full set.

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("fetch_user_ratings called with rating_type=%s", rating_type)
    # Validate parameters with Pydantic
    params = UserRatingsParams(
        rating_type=rating_type,
        rating=rating,
        page=page,
        min_rating=min_rating,
        max_rating=max_rating,
        rated_after=rated_after,  # pyright: ignore[reportArgumentType]
        limit=limit,
        summary=summary,
    )
    rating_type, rating, page = params.rating_type, params.rating, params.page

    try:
        client = get_client(SyncClient)

        if params.uses_client_side_view:
            return await _fetch_ratings_view(client, params)

        # If 'page' is provided, request that page; otherwise use default page=1.
        pagination_params = (
            PaginationParams(page=page, limit=DEFAULT_LIMIT)
            if page is not None
            else None
        )
        paginated_result = await client.get_sync_ratings(
            rating_type, rating, pagination=pagination_params
        )

        paginated_result = _unwrap_or_raise(
            paginated_result,
            resource_type=f"user_{rating_type}_ratings",
            resource_id=f"user_ratings_{rating_type}",
            operation="fetch_user_ratings",
        )

        return SyncRatingsFormatters.format_user_ratings(
            paginated_result, rating_type, rating
        )
    except MCPError:
        raise


async def _fetch_ratings_view(client: SyncClient, params: UserRatingsParams) -> str:
    """Fetch every rating, then filter, truncate or summarize over the full set."""
    rating_type = params.rating_type
    all_ratings = _unwrap_or_raise(
        # Use the API's single-rating path filter when the inputs pin one value;
        # any range is filtered client-side below.
        await client.get_all_sync_ratings(rating_type, params.exact_rating),
        resource_type=f"user_{rating_type}_ratings",
        resource_id=f"user_ratings_{rating_type}",
        operation="fetch_user_ratings",
    )
    selected = _select_ratings(all_ratings, params)

    if params.summary:
        counts = dict.fromkeys(range(RATING_MAX, RATING_MIN - 1, -1), 0)
        for item in selected:
            counts[item.rating] += 1
        recent_count = min(
            params.limit or RATINGS_SUMMARY_RECENT_COUNT, RATINGS_SUMMARY_RECENT_COUNT
        )
        return SyncRatingsFormatters.format_ratings_overview(
            counts, selected[:recent_count], rating_type
        )

    shown = selected[: params.limit] if params.limit else selected
    if not shown:
        return SyncRatingsFormatters.format_ratings_overview({}, [], rating_type)
    return SyncRatingsFormatters.format_user_ratings(
        PaginatedResponse[TraktSyncRating](
            data=shown,
            pagination=PaginationMetadata(
                current_page=1,
                items_per_page=len(shown),
                total_pages=1,
                total_items=len(shown),
            ),
        ),
        rating_type,
        params.exact_rating,
    )


@handle_api_errors_func
async def add_user_ratings(
    rating_type: Literal["movies", "shows", "seasons", "episodes"],
    items: list[UserRatingRequestItem],
) -> str:
    """Add new ratings for the authenticated user.

    Args:
        rating_type: Type of content to rate (movies, shows, seasons, episodes)
        items: List of items to rate with rating and identification info

    Returns:
        Summary of added ratings with counts

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("add_user_ratings called with rating_type=%s", rating_type)

    try:
        client = get_client(SyncClient)

        # Convert to sync request format
        sync_items: list[TraktSyncRatingItem] = []
        for item in items:
            # Create sync rating item
            sync_item_data: dict[str, Any] = {
                "rating": item.rating,
                "ids": item.build_ids_dict(),
            }

            # Add title and year if provided
            if item.title:
                sync_item_data["title"] = item.title
            if item.year:
                sync_item_data["year"] = item.year

            sync_items.append(TraktSyncRatingItem(**sync_item_data))

        # Create request with the appropriate type
        request_data: dict[str, Any] = {rating_type: sync_items}
        request = TraktSyncRatingsRequest(**request_data)

        summary = await client.add_sync_ratings(request)

        summary = _unwrap_or_raise(
            summary,
            resource_type=f"add_user_{rating_type}_ratings",
            resource_id=f"add_ratings_{rating_type}",
            operation="add_user_ratings",
        )

        return SyncRatingsFormatters.format_user_ratings_summary(
            summary, "added", rating_type
        )
    except MCPError:
        raise


@handle_api_errors_func
async def remove_user_ratings(
    rating_type: Literal["movies", "shows", "seasons", "episodes"],
    items: list[UserRatingIdentifier],
) -> str:
    """Remove ratings for the authenticated user.

    Args:
        rating_type: Type of content to unrate (movies, shows, seasons, episodes)
        items: List of items to remove ratings from (no rating values needed,
            just identification)

    Returns:
        Summary of removed ratings with counts

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("remove_user_ratings called with rating_type=%s", rating_type)

    try:
        client = get_client(SyncClient)

        # Convert to sync request format (no ratings needed for removal)
        sync_items: list[TraktSyncRatingItem] = []
        for item in items:
            # Create sync rating item (no rating for removal)
            sync_item_data: dict[str, Any] = {"ids": item.build_ids_dict()}

            # Add title and year if provided
            if item.title:
                sync_item_data["title"] = item.title
            if item.year:
                sync_item_data["year"] = item.year

            sync_items.append(TraktSyncRatingItem(**sync_item_data))

        # Create request with the appropriate type
        request_data: dict[str, Any] = {rating_type: sync_items}
        request = TraktSyncRatingsRequest(**request_data)

        summary = await client.remove_sync_ratings(request)

        summary = _unwrap_or_raise(
            summary,
            resource_type=f"remove_user_{rating_type}_ratings",
            resource_id=f"remove_ratings_{rating_type}",
            operation="remove_user_ratings",
        )

        return SyncRatingsFormatters.format_user_ratings_summary(
            summary, "removed", rating_type
        )
    except MCPError:
        raise


@handle_api_errors_func
async def fetch_user_collection(
    collection_type: Literal["movies", "shows"],
    include_metadata: bool = False,
) -> str:
    """Fetch the authenticated user's entire collection from Trakt.

    Args:
        collection_type: Collection to fetch (movies or shows)
        include_metadata: Include resolution, HDR, audio and related fields

    Returns:
        Every collected item as compact markdown, one line per item. All pages
        are fetched; there is no item cap.

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("fetch_user_collection called with type=%s", collection_type)
    try:
        client = get_client(SyncClient)
        result = await client.get_collection(collection_type, include_metadata)
        result = _unwrap_or_raise(
            result,
            resource_type=f"user_{collection_type}_collection",
            resource_id=f"user_collection_{collection_type}",
            operation="fetch_user_collection",
        )
        return SyncCollectionFormatters.format_user_collection(result, collection_type)
    except MCPError:
        raise


async def _require_auth(client: SyncClient, action: str) -> None:
    """Fail before any cached snapshot is served to a logged-out session."""
    if not await client.ensure_authenticated():
        raise AuthenticationRequiredError(action=action)


async def _load_collected_movies() -> CollectionFetchResult:
    """Fetch the whole movie collection with runtime, genres, rating, metadata."""
    result = await get_client(SyncClient).get_collection(
        "movies", include_metadata=True, include_details=True
    )
    return _unwrap_or_raise(
        result,
        resource_type="user_movies_collection",
        resource_id="user_collection_movies",
        operation="unwatched_in_collection",
    )


async def _load_watched_movies() -> list[WatchedMovieItem]:
    """Fetch every watched movie, across all pages."""
    result = await get_client(SyncClient).get_watched_movies()
    return _unwrap_or_raise(
        result,
        resource_type="user_watched_movies",
        resource_id="user_watched_movies",
        operation="unwatched_in_collection",
    )


@handle_api_errors_func
async def unwatched_in_collection(
    collection_type: Literal["movies"] = "movies",
    min_runtime: int | None = None,
    max_runtime: int | None = None,
    genres_include: list[str] | None = None,
    genres_exclude: list[str] | None = None,
    min_trakt_rating: float | None = None,
    sort: UnwatchedSort = "rating",
    limit: int = UNWATCHED_DEFAULT_LIMIT,
    rng: random.Random | None = None,
) -> str:
    """List collected movies the user has not watched, filtered and sorted.

    The collection and the watched set are cached for 15 minutes, and the
    watched set is dropped whenever history is added or removed.

    Args:
        collection_type: Collection to check (movies only for now)
        min_runtime: Minimum runtime in minutes
        max_runtime: Maximum runtime in minutes
        genres_include: Keep films with at least one of these genre slugs
        genres_exclude: Drop films with any of these genre slugs
        min_trakt_rating: Minimum community rating, 0-10
        sort: rating, runtime, collected_at, released or random
        limit: Maximum films to list
        rng: Random source for sort="random"; defaults to a fresh one

    Returns:
        Counts, then one line per film

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        ValidationError: If parameters are invalid
    """
    query = UnwatchedQuery(
        collection_type=collection_type,
        min_runtime=min_runtime,
        max_runtime=max_runtime,
        genres_include=genres_include or [],
        genres_exclude=genres_exclude or [],
        min_trakt_rating=min_trakt_rating,
        sort=sort,
        limit=limit,
    )
    logger.debug("unwatched_in_collection called with sort=%s", query.sort)
    await _require_auth(get_client(SyncClient), "check your collection")
    collected = await COLLECTED_MOVIES_CACHE.get_or_load(_load_collected_movies)
    watched = await WATCHED_MOVIES_CACHE.get_or_load(_load_watched_movies)
    selection = select_unwatched(
        collected.items,
        watched,
        query,
        rng or random.Random(),  # noqa: S311  # shuffle, not security
    )
    output = SyncUnwatchedFormatters.format_unwatched(selection)
    if collected.truncated:
        output += (
            f"\n\nWARNING: collection read stopped after {collected.pages_fetched} "
            + "pages; this list is incomplete."
        )
    return output


@handle_api_errors_func
async def fetch_user_watchlist(
    watchlist_type: Literal["all", "movies", "shows", "seasons", "episodes"] = "all",
    sort_by: WatchlistSortField = "rank",
    sort_how: Literal["asc", "desc"] = "asc",
    page: int | None = None,
) -> str:
    """Fetch authenticated user's watchlist from Trakt.

    Args:
        watchlist_type: Type of watchlist items to fetch
            (all, movies, shows, seasons, episodes)
        sort_by: Field to sort by (rank, added, title, released, runtime, etc.)
        sort_how: Sort direction (asc, desc)
        page: Optional page number for pagination (1-based)

    Returns:
        User's watchlist formatted as markdown. When 'page' is None,
        only the first page is retrieved (see pagination info in the output).

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("fetch_user_watchlist called with watchlist_type=%s", watchlist_type)
    # Validate parameters with Pydantic
    params = UserWatchlistParams(
        watchlist_type=watchlist_type, sort_by=sort_by, sort_how=sort_how, page=page
    )
    watchlist_type, sort_by, sort_how, page = (
        params.watchlist_type,
        params.sort_by,
        params.sort_how,
        params.page,
    )

    try:
        client = get_client(SyncClient)

        # If 'page' is provided, request that page; otherwise use default page=1.
        pagination_params = (
            PaginationParams(page=page, limit=DEFAULT_LIMIT)
            if page is not None
            else None
        )
        paginated_result = await client.get_sync_watchlist(
            watchlist_type, sort_by, sort_how, pagination=pagination_params
        )

        paginated_result = _unwrap_or_raise(
            paginated_result,
            resource_type=f"user_{watchlist_type}_watchlist",
            resource_id=f"user_watchlist_{watchlist_type}",
            operation="fetch_user_watchlist",
        )

        return SyncWatchlistFormatters.format_user_watchlist(
            paginated_result, watchlist_type, sort_by, sort_how
        )
    except MCPError:
        raise


@handle_api_errors_func
async def add_user_watchlist(
    watchlist_type: Literal["movies", "shows", "seasons", "episodes"],
    items: list[UserWatchlistRequestItem],
) -> str:
    """Add items to the authenticated user's watchlist.

    Args:
        watchlist_type: Type of content to add (movies, shows, seasons, episodes)
        items: List of items to add with identification info and optional notes
            (VIP only)

    Returns:
        Summary of added watchlist items with counts

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("add_user_watchlist called with watchlist_type=%s", watchlist_type)

    try:
        client = get_client(SyncClient)

        # Convert to sync request format
        sync_items: list[TraktSyncWatchlistItem] = []
        for item in items:
            # Create sync watchlist item
            sync_item_data: dict[str, Any] = {"ids": item.build_ids_dict()}

            # Add title and year if provided
            if item.title:
                sync_item_data["title"] = item.title
            if item.year:
                sync_item_data["year"] = item.year
            # Add notes if provided (VIP only)
            if item.notes:
                sync_item_data["notes"] = item.notes

            sync_items.append(TraktSyncWatchlistItem(**sync_item_data))

        # Create request with the appropriate type
        request_data: dict[str, Any] = {watchlist_type: sync_items}
        request = TraktSyncWatchlistRequest(**request_data)

        summary = await client.add_sync_watchlist(request)

        summary = _unwrap_or_raise(
            summary,
            resource_type=f"add_user_{watchlist_type}_watchlist",
            resource_id=f"add_watchlist_{watchlist_type}",
            operation="add_user_watchlist",
        )

        return SyncWatchlistFormatters.format_user_watchlist_summary(
            summary, "added", watchlist_type
        )
    except MCPError:
        raise


@handle_api_errors_func
async def remove_user_watchlist(
    watchlist_type: Literal["movies", "shows", "seasons", "episodes"],
    items: list[UserWatchlistIdentifier],
) -> str:
    """Remove items from the authenticated user's watchlist.

    Args:
        watchlist_type: Type of content to remove (movies, shows, seasons, episodes)
        items: List of items to remove from watchlist (no notes needed,
            just identification)

    Returns:
        Summary of removed watchlist items with counts

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("remove_user_watchlist called with watchlist_type=%s", watchlist_type)

    try:
        client = get_client(SyncClient)

        # Convert to sync request format (no notes for removal)
        sync_items: list[TraktSyncWatchlistItem] = []
        for item in items:
            # Create sync watchlist item (no notes for removal)
            sync_item_data: dict[str, Any] = {"ids": item.build_ids_dict()}

            # Add title and year if provided
            if item.title:
                sync_item_data["title"] = item.title
            if item.year:
                sync_item_data["year"] = item.year

            sync_items.append(TraktSyncWatchlistItem(**sync_item_data))

        # Create request with the appropriate type
        request_data: dict[str, Any] = {watchlist_type: sync_items}
        request = TraktSyncWatchlistRequest(**request_data)

        summary = await client.remove_sync_watchlist(request)

        summary = _unwrap_or_raise(
            summary,
            resource_type=f"remove_user_{watchlist_type}_watchlist",
            resource_id=f"remove_watchlist_{watchlist_type}",
            operation="remove_user_watchlist",
        )

        return SyncWatchlistFormatters.format_user_watchlist_summary(
            summary, "removed", watchlist_type
        )
    except MCPError:
        raise


class HistoryItemBase(IdentifierValidatorMixin):
    """Base class for history item operations."""

    _identifier_error_prefix: ClassVar[str] = "History item"


class HistoryRequestItem(HistoryItemBase):
    """Single history item for add operations."""

    watched_at: WatchedAtValue | None = Field(
        default=None,
        description=(
            "ISO 8601 UTC timestamp, 'released' (initial release date + "
            "runtime; shows/seasons/episodes only), or 'unknown' (no date)"
        ),
        json_schema_extra={
            "examples": ["2024-01-15T20:30:00.000Z", "released", "unknown"]
        },
    )


class HistoryRemoveItem(HistoryItemBase):
    """History item identifier for removal operations."""

    pass


def _reject_released_sentinel_for_movies(
    history_type: Literal["movies", "shows", "seasons", "episodes"],
    items: list[HistoryRequestItem],
) -> None:
    """Reject watched_at='released', which Trakt supports for episodes only.

    Shows and seasons expand to episodes server-side, so the sentinel is
    meaningful for every type except movies.
    """
    if history_type != "movies":
        return
    if any(item.watched_at == "released" for item in items):
        message = (
            "watched_at='released' is only supported for shows, seasons and "
            "episodes. Use an ISO 8601 timestamp or 'unknown' for movies."
        )
        raise InvalidParamsError(message)


@handle_api_errors_func
async def fetch_history(
    history_type: Literal["movies", "shows", "seasons", "episodes"] | None = None,
    item_id: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    page: int | None = None,
) -> str:
    """Fetch watch history, optionally filtered by type and/or specific item.

    Args:
        history_type: Type of content to filter (movies, shows, seasons, episodes)
        item_id: Trakt ID for a specific item (requires history_type)
        start_at: Filter watches after this date (ISO 8601)
        end_at: Filter watches before this date (ISO 8601)
        page: Page number for paginated results (1-based)

    Returns:
        Watch history formatted as markdown with pagination info

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        ValidationError: If parameters are invalid
    """
    # Validate parameters with Pydantic
    params = HistoryQueryParams(
        history_type=history_type,
        item_id=item_id,
        start_at=start_at,
        end_at=end_at,
        page=page,
    )

    logger.debug(
        "fetch_history called with type=%s, item_id=%s",
        params.history_type,
        params.item_id,
    )

    client = get_client(SyncClient)

    # Create pagination params if page is specified
    pagination_params = (
        PaginationParams(page=params.page, limit=DEFAULT_LIMIT)
        if params.page is not None
        else None
    )

    result = await client.get_history(
        history_type=params.history_type,
        item_id=params.item_id,
        start_at=params.start_at,
        end_at=params.end_at,
        pagination=pagination_params,
    )

    result = _unwrap_or_raise(
        result,
        resource_type="history",
        resource_id=params.item_id or "all",
        operation="fetch_history",
    )

    return SyncHistoryFormatters.format_watch_history(
        result, params.history_type, params.item_id
    )


@handle_api_errors_func
async def add_to_history(
    history_type: Literal["movies", "shows", "seasons", "episodes"],
    items: list[HistoryRequestItem],
) -> str:
    """Add items to watch history.

    Args:
        history_type: Type of content to add (movies, shows, seasons, episodes)
        items: List of items to add with identification info and optional
            watched_at (ISO 8601 timestamp, 'released', or 'unknown')

    Returns:
        Summary of added history items with counts

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InvalidParamsError: If watched_at='released' is used with movies
    """
    logger.debug("add_to_history called with type=%s", history_type)

    _reject_released_sentinel_for_movies(history_type, items)

    client = get_client(SyncClient)

    history_items: list[TraktHistoryItem] = []
    for item in items:
        ids_dict = dict(item.build_ids_dict())
        history_items.append(
            TraktHistoryItem(
                ids=TraktIds.model_validate(ids_dict) if ids_dict else None,
                title=item.title,
                year=item.year,
                watched_at=item.watched_at,
            )
        )

    # A write that times out may still have been applied by Trakt, so the
    # cached watched set is dropped whether or not the call succeeded.
    try:
        # For shows, batch per-season to avoid Trakt API gateway timeouts
        if history_type == "shows":
            summary = await _batch_show_history_op(
                client.add_to_history, history_items, "added"
            )
        else:
            request = TraktHistoryRequest(**{history_type: history_items})
            summary = await client.add_to_history(request)
    finally:
        invalidate_watched_cache()

    summary = _unwrap_or_raise(
        summary,
        resource_type=f"add_history_{history_type}",
        resource_id=f"add_history_{history_type}",
        operation="add_to_history",
    )

    return SyncHistoryFormatters.format_history_summary(summary, "added", history_type)


@handle_api_errors_func
async def remove_from_history(
    history_type: Literal["movies", "shows", "seasons", "episodes"],
    items: list[HistoryRemoveItem],
) -> str:
    """Remove items from watch history.

    Args:
        history_type: Type of content to remove (movies, shows, seasons, episodes)
        items: List of items to remove with identification info

    Returns:
        Summary of removed history items with counts

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    logger.debug("remove_from_history called with type=%s", history_type)

    client = get_client(SyncClient)

    history_items: list[TraktHistoryItem] = []
    for item in items:
        ids_dict = dict(item.build_ids_dict())
        history_items.append(
            TraktHistoryItem(
                ids=TraktIds.model_validate(ids_dict) if ids_dict else None,
                title=item.title,
                year=item.year,
            )
        )

    # A write that times out may still have been applied by Trakt, so the
    # cached watched set is dropped whether or not the call succeeded.
    try:
        # For shows, batch per-season to avoid Trakt API gateway timeouts
        if history_type == "shows":
            summary = await _batch_show_history_op(
                client.remove_from_history, history_items, "deleted"
            )
        else:
            request = TraktHistoryRequest(**{history_type: history_items})
            summary = await client.remove_from_history(request)
    finally:
        invalidate_watched_cache()

    summary = _unwrap_or_raise(
        summary,
        resource_type=f"remove_history_{history_type}",
        resource_id=f"remove_history_{history_type}",
        operation="remove_from_history",
    )

    return SyncHistoryFormatters.format_history_summary(
        summary, "removed", history_type
    )


def register_sync_tools(
    mcp: FastMCP,
) -> tuple[
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
    ToolHandler,
]:
    """Register sync tools (ratings, watchlist, collection, history).

    Returns:
        Tuple of tool handlers for type checker visibility
    """

    @mcp.tool(
        name="fetch_user_ratings",
        description=(
            "Fetch the authenticated user's personal ratings from Trakt. "
            "Supports optional pagination with 'page' parameter, and "
            "'min_rating', 'max_rating', 'rated_after' and 'limit' filters. "
            "Set 'summary' for counts per rating plus the most recent ratings. "
            "Requires OAuth authentication."
        ),
    )
    async def fetch_user_ratings_tool(
        rating_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"],
            Field(description=RATING_TYPE_DESCRIPTION),
        ] = "movies",
        rating: Annotated[
            int | None,
            Field(ge=1, le=10, description=RATING_FILTER_DESCRIPTION),
        ] = None,
        page: Annotated[
            int | None,
            Field(ge=1, description=PAGE_DESCRIPTION),
        ] = None,
        min_rating: Annotated[
            int | None,
            Field(ge=RATING_MIN, le=RATING_MAX, description=MIN_RATING_DESCRIPTION),
        ] = None,
        max_rating: Annotated[
            int | None,
            Field(ge=RATING_MIN, le=RATING_MAX, description=MAX_RATING_DESCRIPTION),
        ] = None,
        rated_after: Annotated[
            str | None,
            Field(description=RATED_AFTER_DESCRIPTION),
        ] = None,
        limit: Annotated[
            int | None,
            Field(ge=1, description=RATINGS_LIMIT_DESCRIPTION),
        ] = None,
        summary: Annotated[
            bool,
            Field(description=RATINGS_SUMMARY_DESCRIPTION),
        ] = False,
    ) -> str:
        return await fetch_user_ratings(
            rating_type,
            rating,
            page,
            min_rating,
            max_rating,
            rated_after,
            limit,
            summary,
        )

    @mcp.tool(
        name="add_user_ratings",
        description=(
            "Add new ratings for the authenticated user. Requires OAuth authentication."
        ),
    )
    async def add_user_ratings_tool(
        rating_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"],
            Field(description=RATING_TYPE_DESCRIPTION),
        ],
        items: Annotated[
            list[UserRatingRequestItem],
            Field(
                min_length=1,
                description=RATING_ITEMS_DESCRIPTION,
            ),
        ],
    ) -> str:
        return await add_user_ratings(rating_type, items)

    @mcp.tool(
        name="remove_user_ratings",
        description=(
            "Remove ratings for the authenticated user. Requires OAuth authentication."
        ),
    )
    async def remove_user_ratings_tool(
        rating_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"],
            Field(description=RATING_TYPE_DESCRIPTION),
        ],
        items: Annotated[
            list[UserRatingIdentifier],
            Field(
                min_length=1,
                description=RATING_REMOVE_ITEMS_DESCRIPTION,
            ),
        ],
    ) -> str:
        return await remove_user_ratings(rating_type, items)

    @mcp.tool(
        name="fetch_user_collection",
        description=(
            "Fetch the authenticated user's entire movie or show collection "
            "from Trakt (all pages, no item cap). Shows list the number of "
            "collected episodes. Optionally include media metadata. "
            "Requires OAuth authentication."
        ),
    )
    async def fetch_user_collection_tool(
        collection_type: Annotated[
            Literal["movies", "shows"],
            Field(description=COLLECTION_TYPE_DESCRIPTION),
        ],
        include_metadata: Annotated[
            bool,
            Field(description=COLLECTION_INCLUDE_METADATA_DESCRIPTION),
        ] = False,
    ) -> str:
        return await fetch_user_collection(collection_type, include_metadata)

    @mcp.tool(
        name="unwatched_in_collection",
        description=(
            "List movies in the user's Trakt collection that they have not "
            "watched, in one call. Compares the whole collection with the "
            "whole watched set, so do not page through either by hand. "
            "Filter by runtime, genre and Trakt community rating, sort, and "
            "limit the result. Each line shows title, runtime, genres, rating "
            "and resolution. Requires OAuth authentication."
        ),
    )
    async def unwatched_in_collection_tool(
        collection_type: Annotated[
            Literal["movies"],
            Field(description=UNWATCHED_TYPE_DESCRIPTION),
        ] = "movies",
        min_runtime: Annotated[
            int | None,
            Field(ge=0, description=UNWATCHED_MIN_RUNTIME_DESCRIPTION),
        ] = None,
        max_runtime: Annotated[
            int | None,
            Field(ge=0, description=UNWATCHED_MAX_RUNTIME_DESCRIPTION),
        ] = None,
        genres_include: Annotated[
            list[str] | None,
            Field(description=UNWATCHED_GENRES_INCLUDE_DESCRIPTION),
        ] = None,
        genres_exclude: Annotated[
            list[str] | None,
            Field(description=UNWATCHED_GENRES_EXCLUDE_DESCRIPTION),
        ] = None,
        min_trakt_rating: Annotated[
            float | None,
            Field(ge=0, le=10, description=UNWATCHED_MIN_RATING_DESCRIPTION),
        ] = None,
        sort: Annotated[
            UnwatchedSort,
            Field(description=UNWATCHED_SORT_DESCRIPTION),
        ] = "rating",
        limit: Annotated[
            int,
            Field(
                ge=1, le=UNWATCHED_MAX_LIMIT, description=UNWATCHED_LIMIT_DESCRIPTION
            ),
        ] = UNWATCHED_DEFAULT_LIMIT,
    ) -> str:
        return await unwatched_in_collection(
            collection_type,
            min_runtime,
            max_runtime,
            genres_include,
            genres_exclude,
            min_trakt_rating,
            sort,
            limit,
        )

    @mcp.tool(
        name="fetch_user_watchlist",
        description=(
            "Fetch the authenticated user's watchlist from Trakt. "
            "Supports optional pagination with 'page' parameter and sorting options. "
            "Requires OAuth authentication."
        ),
    )
    async def fetch_user_watchlist_tool(
        watchlist_type: Annotated[
            Literal["all", "movies", "shows", "seasons", "episodes"],
            Field(description=WATCHLIST_TYPE_DESCRIPTION),
        ] = "all",
        sort_by: Annotated[
            WatchlistSortField,
            Field(description=WATCHLIST_SORT_BY_DESCRIPTION),
        ] = "rank",
        sort_how: Annotated[
            Literal["asc", "desc"],
            Field(description=SORT_DIRECTION_DESCRIPTION),
        ] = "asc",
        page: Annotated[
            int | None,
            Field(ge=1, description=PAGE_DESCRIPTION),
        ] = None,
    ) -> str:
        # Validate parameters with Pydantic
        params = UserWatchlistParams(
            watchlist_type=watchlist_type, sort_by=sort_by, sort_how=sort_how, page=page
        )
        return await fetch_user_watchlist(
            params.watchlist_type, params.sort_by, params.sort_how, params.page
        )

    @mcp.tool(
        name="add_user_watchlist",
        description=(
            "Add items to the authenticated user's watchlist. "
            "Supports optional notes (VIP only, 500 character limit). "
            "Requires OAuth authentication."
        ),
    )
    async def add_user_watchlist_tool(
        watchlist_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"],
            Field(description=WATCHLIST_TYPE_REQUIRED_DESCRIPTION),
        ],
        items: Annotated[
            list[UserWatchlistRequestItem],
            Field(
                min_length=1,
                description=WATCHLIST_ITEMS_DESCRIPTION,
            ),
        ],
    ) -> str:
        return await add_user_watchlist(watchlist_type, items)

    @mcp.tool(
        name="remove_user_watchlist",
        description=(
            "Remove items from the authenticated user's watchlist. "
            "Requires OAuth authentication."
        ),
    )
    async def remove_user_watchlist_tool(
        watchlist_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"],
            Field(description=WATCHLIST_TYPE_REQUIRED_DESCRIPTION),
        ],
        items: Annotated[
            list[UserWatchlistIdentifier],
            Field(
                min_length=1,
                description=WATCHLIST_REMOVE_ITEMS_DESCRIPTION,
            ),
        ],
    ) -> str:
        return await remove_user_watchlist(watchlist_type, items)

    @mcp.tool(
        name="fetch_history",
        description=(
            "Check if a movie or show has been watched, or browse watch history. "
            "For 'Have I seen [movie]?': provide history_type='movies' and item_id. "
            "Returns watch dates and count. Empty result means not watched. "
            "Supports optional pagination with 'page' parameter. "
            "Requires OAuth authentication."
        ),
    )
    async def fetch_history_tool(
        history_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"] | None,
            Field(description=HISTORY_QUERY_TYPE_DESCRIPTION),
        ] = None,
        item_id: Annotated[
            str | None,
            Field(description=HISTORY_ITEM_ID_DESCRIPTION),
        ] = None,
        start_at: Annotated[
            str | None,
            Field(description=HISTORY_START_AT_DESCRIPTION),
        ] = None,
        end_at: Annotated[
            str | None,
            Field(description=HISTORY_END_AT_DESCRIPTION),
        ] = None,
        page: Annotated[
            int | None,
            Field(ge=1, description=PAGE_DESCRIPTION),
        ] = None,
    ) -> str:
        return await fetch_history(history_type, item_id, start_at, end_at, page)

    @mcp.tool(
        name="add_to_history",
        description=(
            "Add items to watch history. Marks movies, shows, seasons, or episodes "
            "as watched. Optionally specify when they were watched via "
            "'watched_at', which also accepts 'released' or 'unknown'. "
            "Requires OAuth authentication."
        ),
    )
    async def add_to_history_tool(
        history_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"],
            Field(description=HISTORY_TYPE_DESCRIPTION),
        ],
        items: Annotated[
            list[HistoryRequestItem],
            Field(min_length=1, description=HISTORY_ITEMS_DESCRIPTION),
        ],
    ) -> str:
        return await add_to_history(history_type, items)

    @mcp.tool(
        name="remove_from_history",
        description=(
            "Remove items from watch history. Removes movies, shows, seasons, "
            "or episodes from your watched history. "
            "Requires OAuth authentication."
        ),
    )
    async def remove_from_history_tool(
        history_type: Annotated[
            Literal["movies", "shows", "seasons", "episodes"],
            Field(description=HISTORY_TYPE_DESCRIPTION),
        ],
        items: Annotated[
            list[HistoryRemoveItem],
            Field(min_length=1, description=HISTORY_REMOVE_ITEMS_DESCRIPTION),
        ],
    ) -> str:
        return await remove_from_history(history_type, items)

    # Return handlers for type checker visibility
    return (
        fetch_user_ratings_tool,
        add_user_ratings_tool,
        remove_user_ratings_tool,
        fetch_user_collection_tool,
        unwatched_in_collection_tool,
        fetch_user_watchlist_tool,
        add_user_watchlist_tool,
        remove_user_watchlist_tool,
        fetch_history_tool,
        add_to_history_tool,
        remove_from_history_tool,
    )
