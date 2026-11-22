"""Tests for the server.sync.unwatched_selection module."""

import random
from datetime import datetime

import pytest

from models.sync.collection import CollectionItem, CollectionMovie
from models.sync.unwatched import UnwatchedQuery
from models.sync.watched import WatchedMovieItem
from models.types.ids import TraktIds
from server.sync.unwatched_selection import select_unwatched


def _item(
    trakt: int,
    *,
    runtime: int | None = 100,
    genres: list[str] | None = None,
    rating: float | None = 7.0,
    released: str | None = "2010-01-01",
    collected: str = "2024-01-01T00:00:00+00:00",
) -> CollectionItem:
    return CollectionItem(
        movie=CollectionMovie(
            title=f"Movie {trakt}",
            year=2010,
            ids=TraktIds(trakt=trakt),
            runtime=runtime,
            genres=genres or [],
            rating=rating,
            released=released,
        ),
        collected_at=datetime.fromisoformat(collected),
    )


def _watched(trakt: int) -> WatchedMovieItem:
    return WatchedMovieItem(
        plays=1,
        movie=CollectionMovie(title=f"Movie {trakt}", ids=TraktIds(trakt=trakt)),
    )


def _ids(items: list[CollectionItem]) -> list[int | None]:
    return [item.movie.ids.trakt for item in items if item.movie]


def _select(
    collection: list[CollectionItem],
    watched: list[WatchedMovieItem] | None = None,
    **query: object,
) -> list[int | None]:
    result = select_unwatched(
        collection,
        watched or [],
        UnwatchedQuery.model_validate(query),
        random.Random(1),  # noqa: S311
    )
    return _ids(result.items)


class TestSetDifference:
    def test_watched_movies_are_removed_and_counts_reported(self) -> None:
        collection = [_item(1), _item(2), _item(3)]
        watched = [_watched(2), _watched(99)]

        result = select_unwatched(
            collection,
            watched,
            UnwatchedQuery(sort="runtime"),
            random.Random(1),  # noqa: S311
        )

        assert sorted(_ids(result.items), key=lambda i: i or 0) == [1, 3]
        assert (result.collected, result.watched, result.matching) == (3, 2, 2)

    def test_movie_without_trakt_id_counts_as_unwatched(self) -> None:
        nameless = CollectionItem(movie=CollectionMovie(title="X", ids=TraktIds()))

        assert len(_select([nameless], [_watched(1)])) == 1


class TestFilters:
    def test_min_and_max_runtime_are_inclusive(self) -> None:
        collection = [_item(1, runtime=89), _item(2, runtime=90), _item(3, runtime=120)]
        collection += [_item(4, runtime=121), _item(5, runtime=None)]

        assert sorted(
            _select(collection, min_runtime=90, max_runtime=120),
            key=lambda i: i or 0,
        ) == [2, 3]

    def test_genres_include_matches_any_case_insensitively(self) -> None:
        collection = [
            _item(1, genres=["drama"]),
            _item(2, genres=["comedy"]),
            _item(3, genres=["thriller", "drama"]),
            _item(4),
        ]

        picked = _select(collection, genres_include=["DRAMA", "horror"])

        assert sorted(picked, key=lambda i: i or 0) == [1, 3]

    def test_genres_exclude_drops_any_match(self) -> None:
        collection = [
            _item(1, genres=["drama"]),
            _item(2, genres=["horror", "drama"]),
            _item(3),
        ]

        picked = _select(collection, genres_exclude=["Horror"])

        assert sorted(picked, key=lambda i: i or 0) == [1, 3]

    def test_min_trakt_rating_drops_lower_and_unrated(self) -> None:
        collection = [
            _item(1, rating=7.4),
            _item(2, rating=7.5),
            _item(3, rating=None),
        ]

        assert _select(collection, min_trakt_rating=7.5) == [2]

    def test_runtime_range_must_be_ordered(self) -> None:
        with pytest.raises(ValueError, match="min_runtime"):
            UnwatchedQuery(min_runtime=120, max_runtime=90)


class TestSort:
    def test_rating_descending_with_unrated_last(self) -> None:
        collection = [_item(1, rating=6.0), _item(2, rating=None), _item(3, rating=8.0)]

        assert _select(collection, sort="rating") == [3, 1, 2]

    def test_runtime_ascending_with_unknown_last(self) -> None:
        collection = [
            _item(1, runtime=150),
            _item(2, runtime=None),
            _item(3, runtime=90),
        ]

        assert _select(collection, sort="runtime") == [3, 1, 2]

    def test_collected_at_newest_first(self) -> None:
        collection = [
            _item(1, collected="2023-01-01T00:00:00+00:00"),
            _item(2, collected="2025-01-01T00:00:00+00:00"),
            _item(3, collected="2024-01-01T00:00:00+00:00"),
        ]

        assert _select(collection, sort="collected_at") == [2, 3, 1]

    def test_released_newest_first(self) -> None:
        collection = [
            _item(1, released="1999-05-01"),
            _item(2, released=None),
            _item(3, released="2021-02-03"),
        ]

        assert _select(collection, sort="released") == [3, 1, 2]

    def test_random_is_repeatable_with_a_seeded_source(self) -> None:
        collection = [_item(i) for i in range(1, 11)]
        query = UnwatchedQuery(sort="random")

        first = select_unwatched(collection, [], query, random.Random(42))  # noqa: S311
        second = select_unwatched(collection, [], query, random.Random(42))  # noqa: S311

        assert _ids(first.items) == _ids(second.items)
        assert sorted(_ids(first.items), key=lambda i: i or 0) == list(range(1, 11))
        assert _ids(first.items) != list(range(1, 11))


class TestLimit:
    def test_limit_caps_items_but_not_the_matching_count(self) -> None:
        collection = [_item(i, rating=float(i % 10)) for i in range(1, 31)]

        result = select_unwatched(
            collection,
            [],
            UnwatchedQuery(limit=5),
            random.Random(1),  # noqa: S311
        )

        assert len(result.items) == 5
        assert result.matching == 30

    def test_limit_is_bounded(self) -> None:
        with pytest.raises(ValueError, match="limit"):
            UnwatchedQuery(limit=0)
        with pytest.raises(ValueError, match="limit"):
            UnwatchedQuery(limit=101)
