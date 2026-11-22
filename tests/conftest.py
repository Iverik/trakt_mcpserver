import json
import os
import sys
import time
from collections.abc import Generator
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

if TYPE_CHECKING:
    from client.base import BaseClient
    from client.sync.client import SyncClient
    from models.auth.auth import TraktAuthToken

# Add project root to path - more explicit approach
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also add project root using pathlib as backup
project_root_pathlib = str(Path(__file__).parent.parent.resolve())
if project_root_pathlib not in sys.path:
    sys.path.insert(0, project_root_pathlib)


@pytest.fixture(autouse=True, scope="session")
def _isolate_auth_token_file(  # pyright: ignore[reportUnusedFunction]
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None, None, None]:
    """Prevent tests from reading/writing the real auth_token.json.

    Patches AUTH_TOKEN_FILE to a temp path so no test can accidentally
    overwrite the user's real OAuth token.
    """
    safe_token_path = str(tmp_path_factory.mktemp("auth") / "auth_token.json")
    with (
        patch.dict(os.environ, {"TRAKT_AUTH_TOKEN_PATH": safe_token_path}),
        patch("client.auth.client.AUTH_TOKEN_FILE", safe_token_path),
    ):
        yield


@pytest.fixture(autouse=True)
def _fresh_token_stores() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Give each test its own process-wide token stores.

    AuthClient instances share a TokenStore per token path, which would
    otherwise carry one test's token into the next.
    """
    from client.auth import token_store

    token_store._stores.clear()  # pyright: ignore[reportPrivateUsage]
    yield
    token_store._stores.clear()  # pyright: ignore[reportPrivateUsage]


@pytest.fixture(autouse=True, scope="session")
def trakt_env() -> Generator[None, None, None]:  # pyright: ignore[reportUnusedFunction]
    """Patch environment variables with test Trakt credentials.

    This fixture patches the environment with test credentials for
    TRAKT_CLIENT_ID and TRAKT_CLIENT_SECRET.
    """
    with patch.dict(
        os.environ,
        {"TRAKT_CLIENT_ID": "test_id", "TRAKT_CLIENT_SECRET": "test_secret"},
    ):
        yield


class MockTraktApi:
    """Scripted Trakt API served through ``httpx.MockTransport``.

    Queue responses with ``respond``; every request the client sends is kept
    in ``requests`` so tests can assert on method, URL, query and JSON body.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._responses: list[httpx.Response] = []

    def respond(
        self,
        status: int,
        body: object = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Queue the next response."""
        if body is None:
            self._responses.append(httpx.Response(status, headers=headers))
        else:
            self._responses.append(httpx.Response(status, json=body, headers=headers))

    def request_json(self, index: int = 0) -> object:
        """Return the decoded JSON body of a recorded request."""
        return json.loads(self.requests[index].content)

    def install(self, client: "BaseClient") -> None:
        """Route a client's HTTP calls to this scripted API."""
        client._client = httpx.AsyncClient(  # pyright: ignore[reportPrivateUsage]
            base_url="https://api.trakt.tv",
            transport=httpx.MockTransport(self._handle),
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responses.pop(0)


@pytest.fixture
def mock_trakt_api() -> MockTraktApi:
    """Scripted Trakt API; see ``MockTraktApi``."""
    return MockTraktApi()


@pytest.fixture
def mock_httpx_client() -> MagicMock:
    """Create a mock httpx.AsyncClient for testing with shared client pattern.

    Returns a mock instance that properly supports async methods like
    get(), post(), and aclose() for use with the new shared HTTP client pattern.
    """
    mock_instance = MagicMock()
    mock_instance.get = AsyncMock()
    mock_instance.post = AsyncMock()
    mock_instance.request = AsyncMock()
    mock_instance.aclose = AsyncMock()
    return mock_instance


@pytest.fixture
def patched_httpx_client(
    mock_httpx_client: MagicMock,
) -> Generator[MagicMock, None, None]:
    """Patch httpx.AsyncClient and return the mock instance.

    This fixture patches httpx.AsyncClient to return the mock_httpx_client
    instance, making it easy to configure mock responses in tests.

    Usage:
        async def test_something(patched_httpx_client: MagicMock):
            patched_httpx_client.get.return_value = mock_response
            # Your test code here
    """
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value = mock_httpx_client
        yield mock_httpx_client


@pytest.fixture
def mock_auth_token():
    """Create a mock auth token for testing."""
    from models.auth import TraktAuthToken

    return TraktAuthToken(
        access_token="mock_access_token",
        refresh_token="mock_refresh_token",
        expires_in=7200,
        created_at=int(time.time()),
        scope="public",
        token_type="bearer",
    )


@pytest.fixture
def authenticated_sync_client(
    mock_auth_token: "TraktAuthToken",
) -> Generator["SyncClient", None, None]:
    """Create an authenticated sync client for testing."""
    from client.sync.client import SyncClient

    client = SyncClient()
    client.auth_token = mock_auth_token

    yield client

    # Cleanup: check for and call client.close() if it exists
    if hasattr(client, "close"):
        # Ignore cleanup errors to avoid breaking tests
        with suppress(Exception):
            client.close()  # type: ignore[attr-defined]


@pytest.fixture
def sample_show_data():
    """Sample show data for testing."""
    return {
        "title": "Breaking Bad",
        "year": 2008,
        "ids": {
            "trakt": "1",
            "slug": "breaking-bad",
            "tvdb": "81189",
            "imdb": "tt0903747",
            "tmdb": "1396",
        },
        "overview": (
            "A high school chemistry teacher diagnosed with inoperable lung cancer"
            " turns to manufacturing and selling methamphetamine."
        ),
    }


@pytest.fixture
def sample_movie_data():
    """Sample movie data for testing."""
    return {
        "title": "Inception",
        "year": 2010,
        "ids": {
            "trakt": "1",
            "slug": "inception-2010",
            "imdb": "tt1375666",
            "tmdb": "27205",
        },
        "overview": (
            "A thief who steals corporate secrets through the use of dream-sharing"
            " technology is given the inverse task of planting an idea into the"
            " mind of a C.E.O."
        ),
    }


@pytest.fixture
def sample_trending_shows():
    """Sample trending shows data for testing."""
    return [
        {
            "watchers": 100,
            "show": {
                "title": "Breaking Bad",
                "year": 2008,
                "ids": {"trakt": "1"},
                "overview": (
                    "A high school chemistry teacher diagnosed"
                    " with inoperable lung cancer."
                ),
            },
        },
        {
            "watchers": 80,
            "show": {
                "title": "Stranger Things",
                "year": 2016,
                "ids": {"trakt": "2"},
                "overview": (
                    "When a young boy disappears, his mother, a police chief,"
                    " and his friends must confront terrifying forces."
                ),
            },
        },
    ]


@pytest.fixture
def sample_trending_movies():
    """Sample trending movies data for testing."""
    return [
        {
            "watchers": 150,
            "movie": {
                "title": "Inception",
                "year": 2010,
                "ids": {"trakt": "1"},
                "overview": (
                    "A thief who steals corporate secrets through the use"
                    " of dream-sharing technology."
                ),
            },
        },
        {
            "watchers": 120,
            "movie": {
                "title": "The Dark Knight",
                "year": 2008,
                "ids": {"trakt": "2"},
                "overview": (
                    "When the menace known as the Joker wreaks havoc and chaos"
                    " on the people of Gotham."
                ),
            },
        },
    ]


@pytest.fixture
def user_stats_full() -> dict[str, Any]:
    """Recorded-shape /users/me/stats response with every field present."""
    return json.loads(
        (Path(__file__).parent / "fixtures/user_stats/full.json").read_text()
    )


@pytest.fixture
def user_stats_partial() -> dict[str, Any]:
    """Sparse /users/me/stats response (most sections missing)."""
    return json.loads(
        (Path(__file__).parent / "fixtures/user_stats/partial.json").read_text()
    )
