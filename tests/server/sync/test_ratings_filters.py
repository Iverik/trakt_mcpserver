"""Tests for fetch_user_ratings filters, limit and summary mode."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from config.api.sync import RATINGS_SUMMARY_RECENT_COUNT
from models.movies.movie import TraktMovie
from models.sync.ratings import TraktSyncRating
from models.types.ids import TraktIds
from models.types.pagination import PaginatedResponse, PaginationMetadata
from server.sync.tools import UserRatingsParams, fetch_user_ratings

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def make_rating(index: int, rating: int, days: int | None = None) -> TraktSyncRating:
    """Build a movie rating named 'Movie {index}' rated `days` after BASE."""
    return TraktSyncRating(
        rated_at=BASE + timedelta(days=index if days is None else days),
        rating=rating,
        type="movie",
        movie=TraktMovie(
            title=f"Movie {index}",
            year=2000,
            ids=TraktIds(trakt=index, slug=f"m{index}"),
        ),
    )


def _client_with(ratings: list[TraktSyncRating]) -> AsyncMock:
    client = AsyncMock()
    client.get_all_sync_ratings = AsyncMock(return_value=ratings)
    client.get_sync_ratings = AsyncMock(
        return_value=PaginatedResponse[TraktSyncRating](
            data=ratings,
            pagination=PaginationMetadata(
                current_page=1,
                items_per_page=len(ratings) or 1,
                total_pages=1,
                total_items=len(ratings),
            ),
        )
    )
    return client


class TestParamsValidation:
    def test_defaults_keep_current_behaviour(self) -> None:
        params = UserRatingsParams()
        assert params.summary is False
        assert params.uses_client_side_view is False

    def test_min_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not exceed"):
            UserRatingsParams(min_rating=8, max_rating=5)

    @pytest.mark.parametrize("value", [0, 11])
    def test_rating_bounds(self, value: int) -> None:
        with pytest.raises(ValidationError):
            UserRatingsParams(min_rating=value)
        with pytest.raises(ValidationError):
            UserRatingsParams(max_rating=value)

    def test_limit_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            UserRatingsParams(limit=0)

    def test_rated_after_date_is_midnight_utc(self) -> None:
        params = UserRatingsParams(rated_after="2024-03-05")  # pyright: ignore[reportArgumentType]
        assert params.rated_after == datetime(2024, 3, 5, tzinfo=UTC)

    def test_rated_after_datetime_with_zone(self) -> None:
        params = UserRatingsParams(rated_after="2024-03-05T10:00:00+02:00")  # pyright: ignore[reportArgumentType]
        assert params.rated_after == datetime(2024, 3, 5, 8, 0, tzinfo=UTC)

    def test_rated_after_invalid(self) -> None:
        with pytest.raises(ValidationError, match="ISO 8601"):
            UserRatingsParams(rated_after="last week")  # pyright: ignore[reportArgumentType]

    def test_rating_conflicts_with_range(self) -> None:
        with pytest.raises(ValidationError, match="cannot be combined"):
            UserRatingsParams(rating=5, min_rating=3)

    def test_page_conflicts_with_new_inputs(self) -> None:
        with pytest.raises(ValidationError, match="page cannot be combined"):
            UserRatingsParams(page=2, summary=True)

    def test_exact_rating(self) -> None:
        assert UserRatingsParams(min_rating=7, max_rating=7).exact_rating == 7
        assert UserRatingsParams(min_rating=7, max_rating=8).exact_rating is None
        assert UserRatingsParams(rating=4).exact_rating == 4


@pytest.mark.asyncio
async def test_default_path_unchanged() -> None:
    """With no new inputs the single-response path is used, summary is off."""
    ratings = [make_rating(1, 9)]
    client = _client_with(ratings)
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings()
    client.get_sync_ratings.assert_awaited_once_with("movies", None, pagination=None)
    client.get_all_sync_ratings.assert_not_called()
    assert "Found 1 rated movie on this page" in result
    assert "Summary" not in result


@pytest.mark.asyncio
async def test_range_filters_client_side_over_full_set() -> None:
    ratings = [make_rating(i, r) for i, r in enumerate([10, 9, 8, 7, 6, 5], start=1)]
    client = _client_with(ratings)
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(min_rating=7, max_rating=9)
    client.get_all_sync_ratings.assert_awaited_once_with("movies", None)
    assert "Movie 2" in result and "Movie 3" in result and "Movie 4" in result
    assert "Movie 1" not in result and "Movie 5" not in result


@pytest.mark.asyncio
async def test_equal_min_max_uses_path_filter() -> None:
    client = _client_with([make_rating(1, 8)])
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(min_rating=8, max_rating=8)
    client.get_all_sync_ratings.assert_awaited_once_with("movies", 8)
    assert "filtered to rating 8" in result


@pytest.mark.asyncio
async def test_rated_after_filters() -> None:
    ratings = [make_rating(i, 8, days=i) for i in range(1, 6)]  # Jan 2 .. Jan 6
    client = _client_with(ratings)
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(rated_after="2024-01-05")
    assert "Movie 4" in result and "Movie 5" in result
    assert "Movie 3" not in result


@pytest.mark.asyncio
async def test_limit_keeps_most_recent() -> None:
    ratings = [make_rating(i, 8) for i in range(1, 6)]
    client = _client_with(ratings)
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(limit=2)
    assert "Found 2 rated movies" in result
    assert "Movie 5" in result and "Movie 4" in result
    assert "Movie 3" not in result


@pytest.mark.asyncio
async def test_no_matches_message() -> None:
    client = _client_with([make_rating(1, 3)])
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(min_rating=9)
    assert "No movies ratings found" in result


@pytest.mark.asyncio
async def test_invalid_range_raises() -> None:
    with pytest.raises(Exception, match="must not exceed"):
        await fetch_user_ratings(min_rating=9, max_rating=2)


@pytest.mark.asyncio
async def test_summary_counts_cover_full_set_and_recent_is_capped() -> None:
    # 30 ratings: 12 tens, 10 nines, 8 sevens; Movie N rated N days after BASE
    values = [10] * 12 + [9] * 10 + [7] * 8
    ratings = [make_rating(i, r) for i, r in enumerate(values, start=1)]
    client = _client_with(ratings)
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(summary=True)

    client.get_all_sync_ratings.assert_awaited_once_with("movies", None)
    assert "Total rated: **30**" in result
    assert "- 10/10: 12" in result
    assert "- 9/10: 10" in result
    assert "- 8/10: 0" in result
    assert "- 7/10: 8" in result
    assert "- 1/10: 0" in result
    # Counts listed from 10 down to 1
    order = [result.index(f"- {n}/10:") for n in range(10, 0, -1)]
    assert order == sorted(order)

    assert f"Most recent ratings ({RATINGS_SUMMARY_RECENT_COUNT})" in result
    recent_section = result.split("## Most recent ratings")[1]
    # Newest first: Movie 30 down to Movie 11, and nothing older
    titles = [
        int(line.split("Movie ")[1].split(" ")[0])
        for line in recent_section.splitlines()
        if line.startswith("- **Movie")
    ]
    assert titles == list(range(30, 10, -1))
    assert len(titles) == RATINGS_SUMMARY_RECENT_COUNT


@pytest.mark.asyncio
async def test_summary_respects_filters() -> None:
    ratings = [make_rating(1, 10), make_rating(2, 9), make_rating(3, 5)]
    client = _client_with(ratings)
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(summary=True, min_rating=9)
    assert "Total rated: **2**" in result
    assert "- 5/10" not in result.replace("- 5/10: 0", "")


@pytest.mark.asyncio
async def test_summary_empty() -> None:
    client = _client_with([])
    with patch("server.sync.tools.get_client", return_value=client):
        result = await fetch_user_ratings(summary=True)
    assert "No movies ratings found" in result
