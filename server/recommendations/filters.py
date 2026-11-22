"""Client-side filters for movie recommendations.

The recommendations endpoint returns full metadata with ``extended=full``, so
runtime and genre filters are applied after the fetch.
"""

import re
from dataclasses import dataclass
from typing import Final

from models.recommendations.recommendation import TraktRecommendedMovie

_GENRE_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def normalize_genre_slugs(genres: list[str]) -> list[str]:
    """Lowercase and strip genre slugs, dropping duplicates.

    Args:
        genres: Genre slugs as given by the caller, any case.

    Returns:
        Normalized slugs in first-seen order.

    Raises:
        ValueError: If a value is not shaped like a Trakt genre slug.
    """
    normalized: list[str] = []
    for genre in genres:
        slug = genre.strip().lower()
        if not _GENRE_SLUG_PATTERN.match(slug):
            msg = (
                f"Invalid genre slug {genre!r}: use Trakt genre slugs such as "
                "'science-fiction' (see the Trakt genres list for movies)"
            )
            raise ValueError(msg)
        if slug not in normalized:
            normalized.append(slug)
    return normalized


@dataclass(frozen=True)
class MovieFilterResult:
    """Outcome of filtering movie recommendations."""

    kept: list[TraktRecommendedMovie]
    fetched: int
    removed_by_runtime: int
    removed_by_genre: int


def filter_movies(
    movies: list[TraktRecommendedMovie],
    *,
    max_runtime: int | None,
    genres_include: list[str] | None,
) -> MovieFilterResult:
    """Apply runtime and genre filters to movie recommendations.

    A movie with no runtime is removed when ``max_runtime`` is set, since it
    cannot be shown to fit. Genres match any (case-insensitive).

    Args:
        movies: Recommendations fetched with ``extended=full``.
        max_runtime: Keep movies up to this many minutes, or None.
        genres_include: Keep movies with any of these genre slugs, or None.

    Returns:
        The kept movies plus how many each filter removed.
    """
    wanted = set(genres_include or [])
    kept: list[TraktRecommendedMovie] = []
    removed_by_runtime = 0
    removed_by_genre = 0

    for movie in movies:
        if max_runtime is not None and (
            movie.runtime is None or movie.runtime > max_runtime
        ):
            removed_by_runtime += 1
            continue
        if wanted and not wanted.intersection(g.lower() for g in movie.genres or []):
            removed_by_genre += 1
            continue
        kept.append(movie)

    return MovieFilterResult(
        kept=kept,
        fetched=len(movies),
        removed_by_runtime=removed_by_runtime,
        removed_by_genre=removed_by_genre,
    )


def describe_filtering(
    result: MovieFilterResult,
    *,
    shown: int,
    max_runtime: int | None,
    genres_include: list[str] | None,
) -> str:
    """Describe what the filters did, for the top of the tool output.

    Args:
        result: Outcome from ``filter_movies``.
        shown: How many movies will be listed after trimming to the limit.
        max_runtime: The runtime filter that was applied, or None.
        genres_include: The genre filter that was applied, or None.

    Returns:
        One markdown line naming the filters and the counts.
    """
    applied: list[str] = []
    if max_runtime is not None:
        applied.append(f"runtime <= {max_runtime} min")
    if genres_include:
        applied.append(f"genre in [{', '.join(genres_include)}]")

    removed = result.removed_by_runtime + result.removed_by_genre
    detail = (
        f"{result.removed_by_runtime} by runtime, {result.removed_by_genre} by genre"
    )
    return (
        f"_Filters ({'; '.join(applied)}) applied after fetching "
        f"{result.fetched} recommendations: {removed} filtered out ({detail}), "
        f"{len(result.kept)} matched, showing {shown}._"
    )
