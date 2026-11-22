"""Tests for the personal lists client."""

import pytest

from client.lists import ListsClient
from models.auth import TraktAuthToken
from models.lists import TraktCreateListRequest, TraktListItemsRequest
from tests.conftest import MockTraktApi
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import MCPError

LIST = {
    "name": "Weekend Watch",
    "description": "Cozy picks",
    "privacy": "private",
    "share_link": "https://trakt.tv/lists/2234573",
    "type": "personal",
    "display_numbers": False,
    "allow_comments": True,
    "sort_by": "rank",
    "sort_how": "asc",
    "created_at": "2026-11-01T10:00:00.000Z",
    "updated_at": "2026-11-02T10:00:00.000Z",
    "item_count": 2,
    "comment_count": 0,
    "likes": 0,
    "ids": {"trakt": 2234573, "slug": "weekend-watch"},
    "user": {"username": "me", "private": False, "ids": {"slug": "me", "trakt": 1}},
}


def _pagination(page: int, pages: int, total: int) -> dict[str, str]:
    return {
        "X-Pagination-Page": str(page),
        "X-Pagination-Limit": "100",
        "X-Pagination-Page-Count": str(pages),
        "X-Pagination-Item-Count": str(total),
    }


def _movie_item(rank: int, trakt: int) -> dict[str, object]:
    return {
        "rank": rank,
        "id": 9000 + rank,
        "listed_at": "2026-11-01T10:00:00.000Z",
        "notes": None,
        "type": "movie",
        "movie": {
            "title": f"Movie {trakt}",
            "year": 2000 + rank,
            "ids": {"trakt": trakt, "slug": f"movie-{trakt}"},
        },
    }


@pytest.fixture
def api(mock_trakt_api: MockTraktApi) -> MockTraktApi:
    return mock_trakt_api


@pytest.fixture
def client(api: MockTraktApi, mock_auth_token: TraktAuthToken) -> ListsClient:
    lists_client = ListsClient()
    lists_client.auth_token = mock_auth_token
    api.install(lists_client)
    return lists_client


@pytest.mark.asyncio
async def test_get_user_lists_single_page(client: ListsClient, api: MockTraktApi):
    api.respond(200, [LIST], _pagination(1, 1, 1))

    result = await client.get_user_lists()

    assert not isinstance(result, str)
    assert [item.name for item in result] == ["Weekend Watch"]
    assert result[0].ids.trakt == 2234573
    assert api.requests[0].method == "GET"
    assert api.requests[0].url.path == "/users/me/lists"
    assert api.requests[0].url.params["limit"] == "100"
    assert api.requests[0].headers["Authorization"] == "Bearer mock_access_token"


@pytest.mark.asyncio
async def test_get_user_lists_without_pagination_headers(
    client: ListsClient, api: MockTraktApi
):
    api.respond(200, [LIST])

    result = await client.get_user_lists()

    assert not isinstance(result, str)
    assert len(result) == 1
    assert len(api.requests) == 1


@pytest.mark.asyncio
async def test_get_user_lists_requires_auth(api: MockTraktApi):
    unauthenticated = ListsClient()
    api.install(unauthenticated)

    async def deny() -> bool:
        return False

    unauthenticated.ensure_authenticated = deny
    with pytest.raises(AuthenticationRequiredError):
        await unauthenticated.get_user_lists()
    assert api.requests == []


@pytest.mark.asyncio
async def test_create_user_list_sends_only_set_fields(
    client: ListsClient, api: MockTraktApi
):
    api.respond(201, LIST)

    result = await client.create_user_list(TraktCreateListRequest(name="Weekend Watch"))

    assert not isinstance(result, str)
    assert result.ids.slug == "weekend-watch"
    assert api.requests[0].method == "POST"
    assert api.requests[0].url.path == "/users/me/lists"
    assert api.request_json() == {"name": "Weekend Watch"}


@pytest.mark.asyncio
async def test_create_user_list_sends_description_and_privacy(
    client: ListsClient, api: MockTraktApi
):
    api.respond(201, LIST)

    await client.create_user_list(
        TraktCreateListRequest(
            name="Weekend Watch", description="Cozy picks", privacy="link"
        )
    )

    assert api.request_json() == {
        "name": "Weekend Watch",
        "description": "Cozy picks",
        "privacy": "link",
    }


@pytest.mark.asyncio
async def test_create_user_list_limit_exceeded_surfaces_420(
    client: ListsClient, api: MockTraktApi
):
    api.respond(420, {})

    with pytest.raises(MCPError) as excinfo:
        await client.create_user_list(TraktCreateListRequest(name="One too many"))
    assert excinfo.value.data is not None
    assert excinfo.value.data["http_status"] == 420


@pytest.mark.asyncio
async def test_get_user_list_items_follows_every_page(
    client: ListsClient, api: MockTraktApi
):
    api.respond(200, [_movie_item(1, 11), _movie_item(2, 12)], _pagination(1, 3, 5))
    api.respond(200, [_movie_item(3, 13), _movie_item(4, 14)], _pagination(2, 3, 5))
    api.respond(200, [_movie_item(5, 15)], _pagination(3, 3, 5))

    result = await client.get_user_list_items("weekend-watch")

    assert not isinstance(result, str)
    assert [item.movie.ids.trakt for item in result if item.movie] == [
        11,
        12,
        13,
        14,
        15,
    ]
    assert [r.url.params["page"] for r in api.requests] == ["1", "2", "3"]
    assert all(
        r.url.path == "/users/me/lists/weekend-watch/items" for r in api.requests
    )
    assert all(r.url.params["limit"] == "100" for r in api.requests)


@pytest.mark.asyncio
async def test_get_user_list_items_is_not_capped_at_100(
    client: ListsClient, api: MockTraktApi
):
    first = [_movie_item(i, i) for i in range(1, 101)]
    second = [_movie_item(i, i) for i in range(101, 151)]
    api.respond(200, first, _pagination(1, 2, 150))
    api.respond(200, second, _pagination(2, 2, 150))

    result = await client.get_user_list_items("2234573")

    assert not isinstance(result, str)
    assert len(result) == 150
    assert api.requests[0].url.path == "/users/me/lists/2234573/items"


@pytest.mark.asyncio
async def test_get_user_list_items_parses_mixed_types(
    client: ListsClient, api: MockTraktApi
):
    show = {"title": "Severance", "year": 2022, "ids": {"trakt": 1, "slug": "sev"}}
    api.respond(
        200,
        [
            {"rank": 1, "id": 1, "type": "show", "show": show},
            {
                "rank": 2,
                "id": 2,
                "type": "season",
                "season": {"number": 2, "ids": {"trakt": 5}},
                "show": show,
            },
            {
                "rank": 3,
                "id": 3,
                "type": "episode",
                "episode": {"season": 1, "number": 3, "title": "In Perpetuity"},
                "show": show,
            },
        ],
        _pagination(1, 1, 3),
    )

    result = await client.get_user_list_items("weekend-watch")

    assert not isinstance(result, str)
    assert [item.type for item in result] == ["show", "season", "episode"]


@pytest.mark.asyncio
async def test_get_user_list_items_stops_at_page_safety_cap(
    client: ListsClient, api: MockTraktApi
):
    for page in range(1, 102):
        api.respond(200, [_movie_item(1, page)], _pagination(page, 500, 500))

    with pytest.raises(MCPError, match="safety limit"):
        await client.get_user_list_items("weekend-watch")
    assert len(api.requests) == 100


@pytest.mark.asyncio
async def test_get_user_list_items_missing_list_is_404(
    client: ListsClient, api: MockTraktApi
):
    api.respond(404, {})

    with pytest.raises(MCPError) as excinfo:
        await client.get_user_list_items("nope")
    assert excinfo.value.data is not None
    assert excinfo.value.data["http_status"] == 404


@pytest.mark.asyncio
async def test_get_user_list_items_rejects_bad_list_id(
    client: ListsClient, api: MockTraktApi
):
    with pytest.raises(ValueError, match="list_id"):
        await client.get_user_list_items("  ")
    assert api.requests == []


@pytest.mark.asyncio
async def test_add_user_list_items_request_body_and_summary(
    client: ListsClient, api: MockTraktApi
):
    api.respond(
        201,
        {
            "added": {"movies": 1, "shows": 0, "seasons": 0, "episodes": 0},
            "existing": {"movies": 1, "shows": 0, "seasons": 0, "episodes": 0},
            "not_found": {
                "movies": [{"ids": {"imdb": "tt0000001"}}],
                "shows": [],
                "seasons": [],
                "episodes": [],
            },
            "list": {"updated_at": "2026-11-22T10:00:00.000Z", "item_count": 4},
        },
    )
    request = TraktListItemsRequest.model_validate(
        {
            "movies": [
                {"ids": {"trakt": 120}},
                {"ids": {"imdb": "tt0468569"}},
                {"ids": {"slug": "tron-legacy-2010"}},
                {"ids": {"tmdb": 155}},
                {"ids": {"imdb": "tt0000001"}},
            ]
        }
    )

    result = await client.add_user_list_items("weekend-watch", request)

    assert not isinstance(result, str)
    assert result.added is not None
    assert result.added.movies == 1
    assert result.existing is not None
    assert result.existing.movies == 1
    assert result.deleted is None
    assert result.not_found.movies[0].ids is not None
    assert result.not_found.movies[0].ids.imdb == "tt0000001"
    assert result.list is not None
    assert result.list.item_count == 4
    assert api.requests[0].method == "POST"
    assert api.requests[0].url.path == "/users/me/lists/weekend-watch/items"
    assert api.request_json() == {
        "movies": [
            {"ids": {"trakt": 120}},
            {"ids": {"imdb": "tt0468569"}},
            {"ids": {"slug": "tron-legacy-2010"}},
            {"ids": {"tmdb": 155}},
            {"ids": {"imdb": "tt0000001"}},
        ]
    }


@pytest.mark.asyncio
async def test_add_user_list_items_for_shows_sends_shows_key(
    client: ListsClient, api: MockTraktApi
):
    api.respond(201, {"added": {"shows": 1}, "existing": {}, "not_found": {}})
    request = TraktListItemsRequest.model_validate(
        {"shows": [{"ids": {"tvdb": 81189}}]}
    )

    await client.add_user_list_items("2234573", request)

    assert api.request_json() == {"shows": [{"ids": {"tvdb": 81189}}]}


@pytest.mark.asyncio
async def test_add_user_list_items_over_item_limit_surfaces_420(
    client: ListsClient, api: MockTraktApi
):
    api.respond(420, {})
    request = TraktListItemsRequest.model_validate({"movies": [{"ids": {"trakt": 1}}]})

    with pytest.raises(MCPError) as excinfo:
        await client.add_user_list_items("weekend-watch", request)
    assert excinfo.value.data is not None
    assert excinfo.value.data["http_status"] == 420


@pytest.mark.asyncio
async def test_remove_user_list_items_uses_remove_endpoint(
    client: ListsClient, api: MockTraktApi
):
    api.respond(
        200,
        {
            "deleted": {"movies": 0, "shows": 1, "seasons": 0, "episodes": 0},
            "not_found": {
                "movies": [],
                "shows": [{"ids": {"slug": "missing-show"}}],
                "seasons": [],
                "episodes": [],
            },
            "list": {"updated_at": "2026-11-22T10:00:00.000Z", "item_count": 1},
        },
    )
    request = TraktListItemsRequest.model_validate(
        {"shows": [{"ids": {"trakt": 1388}}, {"ids": {"slug": "missing-show"}}]}
    )

    result = await client.remove_user_list_items("weekend-watch", request)

    assert not isinstance(result, str)
    assert result.deleted is not None
    assert result.deleted.shows == 1
    assert result.added is None
    assert len(result.not_found.shows) == 1
    assert api.requests[0].method == "POST"
    assert api.requests[0].url.path == "/users/me/lists/weekend-watch/items/remove"
    assert api.request_json() == {
        "shows": [{"ids": {"trakt": 1388}}, {"ids": {"slug": "missing-show"}}]
    }


@pytest.mark.asyncio
async def test_add_and_remove_require_auth(api: MockTraktApi):
    unauthenticated = ListsClient()
    api.install(unauthenticated)

    async def deny() -> bool:
        return False

    unauthenticated.ensure_authenticated = deny
    request = TraktListItemsRequest.model_validate({"movies": [{"ids": {"trakt": 1}}]})
    with pytest.raises(AuthenticationRequiredError):
        await unauthenticated.add_user_list_items("x", request)
    with pytest.raises(AuthenticationRequiredError):
        await unauthenticated.remove_user_list_items("x", request)
    with pytest.raises(AuthenticationRequiredError):
        await unauthenticated.create_user_list(TraktCreateListRequest(name="x"))
    assert api.requests == []
