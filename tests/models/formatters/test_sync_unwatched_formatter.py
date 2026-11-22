"""Tests for the sync unwatched formatter."""

from models.formatters.sync_unwatched import SyncUnwatchedFormatters
from models.sync.collection import CollectionItem, CollectionMetadata, CollectionMovie
from models.sync.unwatched import UnwatchedSelection
from models.types.ids import TraktIds


def _item(resolution: str | None, **movie: object) -> CollectionItem:
    metadata = CollectionMetadata(resolution=resolution) if resolution else None
    return CollectionItem(
        movie=CollectionMovie.model_validate(
            {"title": "Heat", "year": 1995, "ids": TraktIds(trakt=1), **movie}
        ),
        metadata=metadata,
    )


def test_line_has_title_runtime_genres_rating_and_resolution() -> None:
    item = _item("hd_1080p", runtime=112, genres=["drama", "thriller"], rating=7.43)
    selection = UnwatchedSelection(collected=10, watched=4, matching=3, items=[item])

    output = SyncUnwatchedFormatters.format_unwatched(selection)

    assert "Collected: 10 | Watched: 4 | Unwatched matching filters: 3 | Shown: 1" in (
        output
    )
    assert "Heat (1995) | 1h 52m | drama, thriller | 7.4 | 1080p" in output


def test_resolution_is_omitted_when_unknown_and_raw_when_unmapped() -> None:
    plain = SyncUnwatchedFormatters.format_unwatched(
        UnwatchedSelection(
            collected=1,
            watched=0,
            matching=1,
            items=[_item(None, runtime=90, genres=["drama"], rating=8.0)],
        )
    )
    odd = SyncUnwatchedFormatters.format_unwatched(
        UnwatchedSelection(
            collected=1, watched=0, matching=1, items=[_item("hd_8k", runtime=90)]
        )
    )

    assert "Heat (1995) | 1h 30m | drama | 8.0" in plain
    assert plain.endswith("8.0")
    assert odd.endswith("| hd_8k")


def test_uhd_maps_to_4k_and_missing_values_show_a_dash() -> None:
    output = SyncUnwatchedFormatters.format_unwatched(
        UnwatchedSelection(collected=1, watched=0, matching=1, items=[_item("uhd_4k")])
    )

    assert "Heat (1995) | - | - | - | 4K" in output


def test_runtime_formats() -> None:
    assert SyncUnwatchedFormatters.format_runtime(45) == "45m"
    assert SyncUnwatchedFormatters.format_runtime(120) == "2h"
    assert SyncUnwatchedFormatters.format_runtime(61) == "1h 1m"
    assert SyncUnwatchedFormatters.format_runtime(None) == "-"


def test_empty_selection_has_header_only() -> None:
    output = SyncUnwatchedFormatters.format_unwatched(
        UnwatchedSelection(collected=3, watched=3, matching=0, items=[])
    )

    assert "Shown: 0" in output
    assert "|" in output and output.count("\n") <= 3
