"""Pick the unwatched movies from a collection, then filter and sort them."""

import random
from collections.abc import Callable

from models.sync.collection import CollectionItem
from models.sync.unwatched import UnwatchedQuery, UnwatchedSelection
from models.sync.watched import WatchedMovieItem


def _passes_filters(item: CollectionItem, query: UnwatchedQuery) -> bool:
    """Whether a movie meets every filter; a missing value fails its filter."""
    movie = item.movie
    if movie is None:
        return False
    if query.min_runtime is not None and (
        movie.runtime is None or movie.runtime < query.min_runtime
    ):
        return False
    if query.max_runtime is not None and (
        movie.runtime is None or movie.runtime > query.max_runtime
    ):
        return False
    if query.min_trakt_rating is not None and (
        movie.rating is None or movie.rating < query.min_trakt_rating
    ):
        return False
    genres = {genre.lower() for genre in movie.genres}
    if query.genres_include and genres.isdisjoint(query.genres_include):
        return False
    return genres.isdisjoint(query.genres_exclude)


def _sorted_items(
    items: list[CollectionItem], query: UnwatchedQuery, rng: random.Random
) -> list[CollectionItem]:
    """Sort with the direction that suits each key; unknown values go last."""
    if query.sort == "random":
        shuffled = list(items)
        rng.shuffle(shuffled)
        return shuffled

    def keyed(
        key: Callable[[CollectionItem], float | str | None], *, descending: bool
    ) -> list[CollectionItem]:
        known = [item for item in items if key(item) is not None]
        unknown = [item for item in items if key(item) is None]
        known.sort(key=lambda item: key(item) or 0, reverse=descending)
        return known + unknown

    match query.sort:
        case "rating":
            return keyed(lambda i: i.movie.rating if i.movie else None, descending=True)
        case "runtime":
            return keyed(
                lambda i: i.movie.runtime if i.movie else None, descending=False
            )
        case "released":
            return keyed(
                lambda i: i.movie.released if i.movie else None, descending=True
            )
        case _:
            return keyed(
                lambda i: i.collected_at.timestamp() if i.collected_at else None,
                descending=True,
            )


def select_unwatched(
    collection: list[CollectionItem],
    watched: list[WatchedMovieItem],
    query: UnwatchedQuery,
    rng: random.Random,
) -> UnwatchedSelection:
    """Collected movies that are not in the watched set, filtered and sorted.

    Movies match on Trakt id. A collected movie with no Trakt id cannot be
    matched against the watched set, so it counts as unwatched.
    """
    watched_ids = {
        item.movie.ids.trakt for item in watched if item.movie.ids.trakt is not None
    }
    unwatched = [
        item
        for item in collection
        if item.movie is not None
        and (item.movie.ids.trakt is None or item.movie.ids.trakt not in watched_ids)
    ]
    matching = [item for item in unwatched if _passes_filters(item, query)]
    ordered = _sorted_items(matching, query, rng)
    return UnwatchedSelection(
        collected=len(collection),
        watched=len(watched),
        matching=len(matching),
        items=ordered[: query.limit],
    )
