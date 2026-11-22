"""Tests for movie check-in and cancel on the check-in client."""

import pytest

from client.checkin import CheckinClient
from models.auth import TraktAuthToken
from tests.conftest import MockTraktApi
from utils.api.error_types import AuthenticationRequiredError
from utils.api.errors import InvalidRequestError

MOVIE_CHECKIN = {
    "id": 3373536619,
    "watched_at": "2026-11-22T20:00:00.000Z",
    "sharing": {"twitter": False, "mastodon": True, "tumblr": False},
    "movie": {
        "title": "The Dark Knight",
        "year": 2008,
        "ids": {"trakt": 120, "slug": "the-dark-knight-2008", "imdb": "tt0468569"},
    },
}
EPISODE_CHECKIN = {
    "id": 42,
    "watched_at": "2026-11-22T20:00:00.000Z",
    "sharing": {"twitter": False, "mastodon": False, "tumblr": False},
    "show": {"title": "Breaking Bad", "year": 2008, "ids": {"trakt": 1}},
    "episode": {"season": 1, "number": 1, "title": "Pilot", "ids": {"trakt": 73640}},
}
CONFLICT = {"expires_at": "2026-11-22T22:30:00.000Z"}


@pytest.fixture
def client(
    mock_trakt_api: MockTraktApi, mock_auth_token: TraktAuthToken
) -> CheckinClient:
    checkin_client = CheckinClient()
    checkin_client.auth_token = mock_auth_token
    mock_trakt_api.install(checkin_client)
    return checkin_client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("movie_id", "expected_ids"),
    [
        ("120", {"trakt": 120}),
        ("the-dark-knight-2008", {"slug": "the-dark-knight-2008"}),
        ("tt0468569", {"imdb": "tt0468569"}),
    ],
)
async def test_checkin_to_movie_id_types(
    client: CheckinClient,
    mock_trakt_api: MockTraktApi,
    movie_id: str,
    expected_ids: dict[str, object],
) -> None:
    mock_trakt_api.respond(201, MOVIE_CHECKIN)

    result = await client.checkin_to_movie(movie_id=movie_id)

    assert not isinstance(result, str)
    assert result["id"] == 3373536619
    movie = result.get("movie")
    assert movie is not None
    assert movie["title"] == "The Dark Knight"
    request = mock_trakt_api.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/checkin"
    assert mock_trakt_api.request_json() == {"movie": {"ids": expected_ids}}


@pytest.mark.asyncio
async def test_checkin_to_movie_title_and_year(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(201, MOVIE_CHECKIN)

    await client.checkin_to_movie(movie_title="The Dark Knight", movie_year=2008)

    assert mock_trakt_api.request_json() == {
        "movie": {"title": "The Dark Knight", "year": 2008}
    }


@pytest.mark.asyncio
async def test_checkin_to_movie_message_and_sharing(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(201, MOVIE_CHECKIN)

    await client.checkin_to_movie(
        movie_id="120",
        message="Why so serious?",
        share_twitter=True,
        share_mastodon=False,
        share_tumblr=True,
    )

    assert mock_trakt_api.request_json() == {
        "movie": {"ids": {"trakt": 120}},
        "message": "Why so serious?",
        "sharing": {"twitter": True, "mastodon": False, "tumblr": True},
    }


@pytest.mark.asyncio
async def test_checkin_to_movie_omits_sharing_when_not_requested(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(201, MOVIE_CHECKIN)

    await client.checkin_to_movie(movie_id="120")

    body = mock_trakt_api.request_json()
    assert isinstance(body, dict)
    assert "sharing" not in body
    assert "message" not in body


@pytest.mark.asyncio
async def test_checkin_to_movie_requires_id_or_title(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    with pytest.raises(ValueError, match="movie_id or movie_title"):
        await client.checkin_to_movie()
    assert mock_trakt_api.requests == []


@pytest.mark.asyncio
async def test_checkin_to_movie_rejects_malformed_imdb_id(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    with pytest.raises(ValueError, match="IMDB"):
        await client.checkin_to_movie(movie_id="ttabc")
    assert mock_trakt_api.requests == []


@pytest.mark.asyncio
async def test_checkin_to_movie_requires_auth(
    mock_trakt_api: MockTraktApi,
) -> None:
    unauthenticated = CheckinClient()
    mock_trakt_api.install(unauthenticated)

    async def deny() -> bool:
        return False

    unauthenticated.ensure_authenticated = deny
    with pytest.raises(AuthenticationRequiredError, match="check in to a movie"):
        await unauthenticated.checkin_to_movie(movie_id="120")
    assert mock_trakt_api.requests == []


@pytest.mark.asyncio
async def test_checkin_to_movie_409_reports_expiry(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(409, CONFLICT)

    with pytest.raises(InvalidRequestError) as excinfo:
        await client.checkin_to_movie(movie_id="120")

    assert "already checked in" in excinfo.value.message
    assert "2026-11-22T22:30:00.000Z" in excinfo.value.message
    assert "cancel_checkin" in excinfo.value.message
    assert excinfo.value.data is not None
    assert excinfo.value.data["http_status"] == 409
    assert excinfo.value.data["expires_at"] == "2026-11-22T22:30:00.000Z"


@pytest.mark.asyncio
async def test_checkin_to_movie_409_without_body(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(409)

    with pytest.raises(InvalidRequestError) as excinfo:
        await client.checkin_to_movie(movie_id="120")

    assert "already checked in" in excinfo.value.message
    assert excinfo.value.data is not None
    assert "expires_at" not in excinfo.value.data


@pytest.mark.asyncio
async def test_checkin_to_show_409_reports_expiry_too(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(409, CONFLICT)

    with pytest.raises(InvalidRequestError, match=r"2026-11-22T22:30:00\.000Z"):
        await client.checkin_to_show(episode_season=1, episode_number=1, show_id="1")


@pytest.mark.asyncio
async def test_checkin_to_show_request_body_unchanged(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(201, EPISODE_CHECKIN)

    await client.checkin_to_show(
        episode_season=1,
        episode_number=1,
        show_id="1",
        show_year=2008,
        message="Hi",
        share_twitter=True,
    )

    assert mock_trakt_api.request_json() == {
        "episode": {"season": 1, "number": 1},
        "show": {"ids": {"trakt": "1"}, "year": 2008},
        "message": "Hi",
        "sharing": {"twitter": True, "mastodon": False, "tumblr": False},
    }


@pytest.mark.asyncio
async def test_cancel_checkin_sends_delete_and_accepts_204(
    client: CheckinClient, mock_trakt_api: MockTraktApi
) -> None:
    mock_trakt_api.respond(204)

    result = await client.cancel_checkin()

    assert result is None
    request = mock_trakt_api.requests[0]
    assert request.method == "DELETE"
    assert request.url.path == "/checkin"
    assert request.content == b""


@pytest.mark.asyncio
async def test_cancel_checkin_requires_auth(mock_trakt_api: MockTraktApi) -> None:
    unauthenticated = CheckinClient()
    mock_trakt_api.install(unauthenticated)

    async def deny() -> bool:
        return False

    unauthenticated.ensure_authenticated = deny
    with pytest.raises(AuthenticationRequiredError, match="cancel your check-in"):
        await unauthenticated.cancel_checkin()
    assert mock_trakt_api.requests == []
