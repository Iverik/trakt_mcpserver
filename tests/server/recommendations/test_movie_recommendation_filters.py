"""Tests for client-side movie recommendation filters."""

import pytest

from models.recommendations.recommendation import TraktRecommendedMovie
from server.recommendations.filters import (
    describe_filtering,
    filter_movies,
    normalize_genre_slugs,
)


def _movie(
    trakt: int, runtime: int | None, genres: list[str] | None
) -> TraktRecommendedMovie:
    return TraktRecommendedMovie.model_validate(
        {
            "title": f"Movie {trakt}",
            "ids": {"trakt": trakt, "slug": f"movie-{trakt}"},
            "runtime": runtime,
            "genres": genres,
        }
    )


MOVIES = [
    _movie(1, 90, ["comedy"]),
    _movie(2, 150, ["drama", "science-fiction"]),
    _movie(3, 100, ["science-fiction", "thriller"]),
    _movie(4, None, ["comedy"]),
    _movie(5, 80, None),
]


def test_normalize_lowercases_strips_and_dedupes() -> None:
    assert normalize_genre_slugs([" Comedy ", "SCIENCE-FICTION", "comedy"]) == [
        "comedy",
        "science-fiction",
    ]


@pytest.mark.parametrize("bad", ["", "sci fi", "comedy!", "-x", "a--b"])
def test_normalize_rejects_non_slugs(bad: str) -> None:
    with pytest.raises(ValueError, match="Invalid genre slug"):
        normalize_genre_slugs([bad])


def test_max_runtime_only() -> None:
    result = filter_movies(MOVIES, max_runtime=100, genres_include=None)
    assert [m.ids.trakt for m in result.kept] == [1, 3, 5]
    # Movie 2 is too long, movie 4 has no runtime.
    assert result.removed_by_runtime == 2
    assert result.removed_by_genre == 0
    assert result.fetched == 5


def test_genres_match_any() -> None:
    result = filter_movies(
        MOVIES, max_runtime=None, genres_include=["thriller", "comedy"]
    )
    assert [m.ids.trakt for m in result.kept] == [1, 3, 4]
    assert result.removed_by_genre == 2


def test_genre_match_is_case_insensitive_on_response_values() -> None:
    movies = [_movie(9, 90, ["Science-Fiction"])]
    result = filter_movies(movies, max_runtime=None, genres_include=["science-fiction"])
    assert len(result.kept) == 1


def test_combination_requires_both() -> None:
    result = filter_movies(MOVIES, max_runtime=100, genres_include=["science-fiction"])
    assert [m.ids.trakt for m in result.kept] == [3]
    assert result.removed_by_runtime == 2
    assert result.removed_by_genre == 2


def test_describe_filtering_reports_counts() -> None:
    result = filter_movies(MOVIES, max_runtime=100, genres_include=["science-fiction"])
    note = describe_filtering(
        result, shown=1, max_runtime=100, genres_include=["science-fiction"]
    )
    assert "runtime <= 100 min" in note
    assert "genre in [science-fiction]" in note
    assert "fetching 5 recommendations" in note
    assert "4 filtered out (2 by runtime, 2 by genre)" in note
    assert "1 matched, showing 1" in note


def _rec(trakt: int) -> TraktRecommendedMovie:
    return _movie(trakt, None, None)


def test_collected_ids_are_removed_and_counted() -> None:
    result = filter_movies(
        [_rec(1), _rec(2), _rec(3)],
        max_runtime=None,
        genres_include=None,
        collected_ids=frozenset({2, 99}),
    )
    assert [m.ids.trakt for m in result.kept] == [1, 3]
    assert result.removed_as_collected == 1


def test_no_collected_ids_removes_nothing() -> None:
    result = filter_movies([_rec(1)], max_runtime=None, genres_include=None)
    assert result.removed_as_collected == 0
    assert len(result.kept) == 1
