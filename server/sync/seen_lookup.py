"""Look up watched state and rating for a list of Trakt movie ids."""

from models.sync.base import TraktSyncRating
from models.sync.seen import SeenEntry
from models.sync.watched import WatchedMovieItem


def lookup_seen(
    trakt_ids: list[int],
    watched: list[WatchedMovieItem],
    ratings: list[TraktSyncRating],
) -> list[SeenEntry]:
    """One entry per distinct id, in the order given.

    The title comes from the watched data, else from the ratings data. An id
    in neither carries no title, watched state or rating.
    """
    watched_by_id = {
        item.movie.ids.trakt: item for item in watched if item.movie.ids.trakt
    }
    rated_by_id: dict[int, TraktSyncRating] = {}
    for rating in ratings:
        if rating.type == "movie" and rating.movie and rating.movie.ids.trakt:
            rated_by_id[rating.movie.ids.trakt] = rating

    entries: list[SeenEntry] = []
    for trakt_id in dict.fromkeys(trakt_ids):
        watched_item = watched_by_id.get(trakt_id)
        rated = rated_by_id.get(trakt_id)
        movie = watched_item.movie if watched_item else (rated.movie if rated else None)
        entries.append(
            SeenEntry(
                trakt_id=trakt_id,
                title=movie.title if movie else None,
                year=movie.year if movie else None,
                watched=watched_item is not None,
                plays=watched_item.plays if watched_item else 0,
                last_watched_at=watched_item.last_watched_at if watched_item else None,
                rating=rated.rating if rated else None,
            )
        )
    return entries
