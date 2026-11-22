"""Tests for personal list formatters."""

from models.formatters.lists import ListsFormatters
from models.lists import TraktListItem, TraktListItemsSummary, TraktUserList


def _list(**overrides: object) -> TraktUserList:
    data: dict[str, object] = {
        "name": "Weekend Watch",
        "description": "Cozy picks",
        "privacy": "link",
        "share_link": "https://trakt.tv/lists/2234573",
        "item_count": 3,
        "ids": {"trakt": 2234573, "slug": "weekend-watch"},
        **overrides,
    }
    return TraktUserList.model_validate(data)


def test_format_user_lists() -> None:
    output = ListsFormatters.format_user_lists([_list()])
    assert "# Your Lists" in output
    assert "**Weekend Watch** (ID: 2234573, slug: weekend-watch): 3 items, link" in (
        output
    )


def test_format_user_lists_empty() -> None:
    assert "no lists yet" in ListsFormatters.format_user_lists([])


def test_format_created_list() -> None:
    output = ListsFormatters.format_created_list(_list())
    assert "# List Created" in output
    assert "Cozy picks" in output
    assert "List ID: 2234573" in output
    assert "Slug: weekend-watch" in output
    assert "Share link: https://trakt.tv/lists/2234573" in output


def test_format_created_list_minimal() -> None:
    output = ListsFormatters.format_created_list(
        _list(description=None, share_link=None)
    )
    assert "Cozy picks" not in output
    assert "Share link" not in output


def test_format_list_items_all_types() -> None:
    show = {"title": "Severance", "year": 2022, "ids": {"trakt": 1}}
    items = [
        TraktListItem.model_validate(raw)
        for raw in (
            {
                "rank": 1,
                "type": "movie",
                "movie": {"title": "Tron", "year": 2010, "ids": {"trakt": 2}},
            },
            {"rank": 2, "type": "show", "show": show},
            {"rank": 3, "type": "season", "season": {"number": 2}, "show": show},
            {
                "rank": 4,
                "type": "episode",
                "episode": {"season": 1, "number": 3},
                "show": show,
            },
        )
    ]
    output = ListsFormatters.format_list_items(items, "weekend-watch")
    assert "Found 4 items on `weekend-watch`" in output
    assert "1. Movie: Tron (2010)" in output
    assert "2. Show: Severance (2022)" in output
    assert "3. Season 2 of Severance" in output
    assert "4. Episode: Severance S01E03" in output


def test_format_list_items_empty() -> None:
    assert "is empty" in ListsFormatters.format_list_items([], "weekend-watch")


def test_format_add_summary_reports_trakt_counts() -> None:
    summary = TraktListItemsSummary.model_validate(
        {
            "added": {"movies": 2, "shows": 0, "seasons": 0, "episodes": 0},
            "existing": {"movies": 1, "shows": 0, "seasons": 0, "episodes": 0},
            "not_found": {
                "movies": [{"ids": {"imdb": "tt0000001"}}],
                "shows": [{"title": "Ghost Show", "year": 1999}],
            },
            "list": {"item_count": 9},
        }
    )
    output = ListsFormatters.format_items_summary(summary, "added", "weekend-watch")
    assert "Added: 2 movies, 0 shows, 0 seasons, 0 episodes" in output
    assert "Already on the list: 1 movies" in output
    assert "- movie: imdb tt0000001" in output
    assert "- show: Ghost Show" in output
    assert "now has 9 items" in output


def test_format_remove_summary() -> None:
    summary = TraktListItemsSummary.model_validate(
        {"deleted": {"shows": 1}, "not_found": {}}
    )
    output = ListsFormatters.format_items_summary(summary, "removed", "x")
    assert "Removed: 0 movies, 1 shows" in output
    assert "Not found" not in output
