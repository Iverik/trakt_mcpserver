"""Tests for personal list tools."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.lists import TraktListItem, TraktListItemsSummary, TraktUserList
from server.lists.tools import (
    UserListItem,
    add_user_list_items,
    create_user_list,
    fetch_user_list_items,
    fetch_user_lists,
    remove_user_list_items,
)

USER_LIST = TraktUserList.model_validate(
    {
        "name": "Weekend Watch",
        "privacy": "private",
        "item_count": 1,
        "ids": {"trakt": 2234573, "slug": "weekend-watch"},
    }
)
SUMMARY = TraktListItemsSummary.model_validate(
    {
        "added": {"movies": 1},
        "existing": {"movies": 0},
        "deleted": {"movies": 1},
        "not_found": {},
    }
)


@pytest.fixture
def client() -> Generator[MagicMock, None, None]:
    with patch("server.lists.tools.get_client") as get_client:
        mock = MagicMock()
        get_client.return_value = mock
        yield mock


@pytest.mark.asyncio
async def test_fetch_user_lists(client: MagicMock) -> None:
    client.get_user_lists = AsyncMock(return_value=[USER_LIST])
    output = await fetch_user_lists()
    assert "Weekend Watch" in output


@pytest.mark.asyncio
async def test_fetch_user_lists_error_string(client: MagicMock) -> None:
    client.get_user_lists = AsyncMock(return_value="boom")
    output = await fetch_user_lists()
    assert output.startswith("# Error")
    assert "user_lists" in output


@pytest.mark.asyncio
async def test_create_user_list_passes_validated_request(client: MagicMock) -> None:
    client.create_user_list = AsyncMock(return_value=USER_LIST)

    output = await create_user_list(" Weekend Watch ", "Cozy", "friends")

    assert "# List Created" in output
    request = client.create_user_list.call_args.args[0]
    assert request.model_dump(exclude_none=True) == {
        "name": "Weekend Watch",
        "description": "Cozy",
        "privacy": "friends",
    }


@pytest.mark.asyncio
async def test_create_user_list_rejects_bad_privacy(client: MagicMock) -> None:
    client.create_user_list = AsyncMock()
    bad: Any = "secret"
    output = await create_user_list("x", None, bad)
    assert output.startswith("# Error")
    assert "privacy" in output
    client.create_user_list.assert_not_called()


@pytest.mark.asyncio
async def test_create_user_list_rejects_blank_name(client: MagicMock) -> None:
    client.create_user_list = AsyncMock()
    output = await create_user_list("   ")
    assert output.startswith("# Error")
    assert "name" in output
    client.create_user_list.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_user_list_items(client: MagicMock) -> None:
    item = TraktListItem.model_validate(
        {
            "rank": 1,
            "type": "movie",
            "movie": {"title": "Tron", "year": 2010, "ids": {"trakt": 2}},
        }
    )
    client.get_user_list_items = AsyncMock(return_value=[item])

    output = await fetch_user_list_items(" weekend-watch ")

    assert "Movie: Tron (2010)" in output
    client.get_user_list_items.assert_called_once_with("weekend-watch")


@pytest.mark.asyncio
async def test_fetch_user_list_items_rejects_empty_id(client: MagicMock) -> None:
    client.get_user_list_items = AsyncMock()
    output = await fetch_user_list_items("")
    assert output.startswith("# Error")
    assert "list_id" in output
    client.get_user_list_items.assert_not_called()


@pytest.mark.asyncio
async def test_add_user_list_items_builds_request_for_every_id_type(
    client: MagicMock,
) -> None:
    client.add_user_list_items = AsyncMock(return_value=SUMMARY)
    items = [
        UserListItem(trakt_id="120"),
        UserListItem(slug="tron-legacy-2010"),
        UserListItem(imdb_id="tt0468569"),
        UserListItem(tmdb_id="155"),
        UserListItem(title="Heat", year=1995),
    ]

    output = await add_user_list_items("weekend-watch", "movies", items)

    assert "Added: 1 movies" in output
    list_id, request = client.add_user_list_items.call_args.args
    assert list_id == "weekend-watch"
    assert request.model_dump(mode="json", exclude_none=True) == {
        "movies": [
            {"ids": {"trakt": 120}},
            {"ids": {"slug": "tron-legacy-2010"}},
            {"ids": {"imdb": "tt0468569"}},
            {"ids": {"tmdb": 155}},
            {"title": "Heat", "year": 1995},
        ]
    }


@pytest.mark.asyncio
async def test_add_user_list_items_for_shows(client: MagicMock) -> None:
    client.add_user_list_items = AsyncMock(return_value=SUMMARY)
    await add_user_list_items("1", "shows", [UserListItem(tvdb_id="81189")])
    request = client.add_user_list_items.call_args.args[1]
    assert request.model_dump(mode="json", exclude_none=True) == {
        "shows": [{"ids": {"tvdb": 81189}}]
    }


@pytest.mark.asyncio
async def test_add_user_list_items_rejects_empty_items(client: MagicMock) -> None:
    client.add_user_list_items = AsyncMock()
    output = await add_user_list_items("weekend-watch", "movies", [])
    assert output.startswith("# Error")
    client.add_user_list_items.assert_not_called()


@pytest.mark.asyncio
async def test_remove_user_list_items(client: MagicMock) -> None:
    client.remove_user_list_items = AsyncMock(return_value=SUMMARY)

    output = await remove_user_list_items(
        "weekend-watch", "movies", [UserListItem(trakt_id="120")]
    )

    assert "Removed: 1 movies" in output
    list_id, request = client.remove_user_list_items.call_args.args
    assert list_id == "weekend-watch"
    assert request.model_dump(mode="json", exclude_none=True) == {
        "movies": [{"ids": {"trakt": 120}}]
    }


@pytest.mark.asyncio
async def test_remove_user_list_items_rejects_bad_list_id(client: MagicMock) -> None:
    client.remove_user_list_items = AsyncMock()
    output = await remove_user_list_items("  ", "movies", [UserListItem(trakt_id="1")])
    assert output.startswith("# Error")
    assert "list_id" in output
    client.remove_user_list_items.assert_not_called()


@pytest.mark.asyncio
async def test_remove_user_list_items_requires_an_id(client: MagicMock) -> None:
    client.remove_user_list_items = AsyncMock()

    output = await remove_user_list_items(
        "weekend-watch", "movies", [UserListItem(title="Heat", year=1995)]
    )

    assert output.startswith("# Error")
    assert "at least one ID" in output
    client.remove_user_list_items.assert_not_called()


def test_user_list_item_requires_identifier() -> None:
    with pytest.raises(ValueError, match="List item must include"):
        UserListItem()
