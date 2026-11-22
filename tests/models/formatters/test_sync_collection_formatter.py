"""Tests for sync collection formatters."""

from datetime import datetime

from models.formatters.sync_collection import SyncCollectionFormatters
from models.movies.movie import TraktMovie
from models.shows.show import TraktShow
from models.sync.collection import (
    CollectionEpisode,
    CollectionFetchResult,
    CollectionItem,
    CollectionMetadata,
    CollectionSeason,
)
from models.types.ids import TraktIds

IDS = TraktIds(trakt=1, slug="x")


def _movie_item(
    title: str, metadata: CollectionMetadata | None = None
) -> CollectionItem:
    return CollectionItem(
        movie=TraktMovie(title=title, year=2010, ids=IDS),
        collected_at=datetime.fromisoformat("2024-01-15T10:30:00+00:00"),
        metadata=metadata,
    )


class TestSyncCollectionFormatters:
    """Test cases for SyncCollectionFormatters."""

    def test_movies_with_and_without_metadata(self) -> None:
        """Movie lines show date, and resolution, hdr, audio when present."""
        result = CollectionFetchResult(
            items=[
                _movie_item(
                    "Inception",
                    CollectionMetadata(
                        resolution="uhd_4k", hdr="dolby_vision", audio="dolby_atmos"
                    ),
                ),
                _movie_item("Heat", CollectionMetadata(resolution="hd_1080p")),
                _movie_item("Alien"),
            ],
            pages_fetched=1,
        )

        lines = SyncCollectionFormatters.format_user_collection(
            result, "movies"
        ).splitlines()

        assert "Total: 3 movies" in lines
        assert (
            "- Inception (2010), collected 2024-01-15 "
            "(uhd_4k, dolby_vision, dolby_atmos)"
        ) in lines
        assert "- Heat (2010), collected 2024-01-15 (hd_1080p)" in lines
        assert "- Alien (2010), collected 2024-01-15" in lines

    def test_shows_list_collected_episode_counts(self) -> None:
        """Show lines give the number of collected episodes."""
        show = CollectionItem(
            show=TraktShow(title="Breaking Bad", year=2008, ids=IDS),
            seasons=[
                CollectionSeason(
                    number=1,
                    episodes=[CollectionEpisode(number=1), CollectionEpisode(number=2)],
                ),
                CollectionSeason(number=2, episodes=[CollectionEpisode(number=1)]),
            ],
        )
        single = CollectionItem(
            show=TraktShow(title="Short", year=None, ids=IDS),
            seasons=[
                CollectionSeason(number=1, episodes=[CollectionEpisode(number=1)])
            ],
        )

        output = SyncCollectionFormatters.format_user_collection(
            CollectionFetchResult(items=[show, single], pages_fetched=1), "shows"
        )

        assert "Total: 2 shows" in output
        assert "- Breaking Bad (2008), 3 episodes" in output
        assert "- Short, 1 episode" in output

    def test_empty_collection(self) -> None:
        """An empty collection still starts with a total line."""
        output = SyncCollectionFormatters.format_user_collection(
            CollectionFetchResult(items=[], pages_fetched=1), "movies"
        )

        assert "Total: 0 movies" in output

    def test_truncated_result_is_announced(self) -> None:
        """A page-guard truncation is stated in the output."""
        output = SyncCollectionFormatters.format_user_collection(
            CollectionFetchResult(
                items=[_movie_item("Alien")], pages_fetched=200, truncated=True
            ),
            "movies",
        )

        assert "WARNING: stopped after 200 pages" in output
