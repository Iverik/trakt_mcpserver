"""Shared fixtures for calendars client tests."""

import pytest

from client.calendars import CalendarsClient
from models.auth import TraktAuthToken


@pytest.fixture
def authenticated_client(mock_auth_token: TraktAuthToken) -> CalendarsClient:
    """Create an authenticated calendars client for testing."""
    client = CalendarsClient()
    client.auth_token = mock_auth_token
    return client
