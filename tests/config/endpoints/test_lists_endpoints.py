"""Tests for personal list endpoints."""

from config.endpoints import TRAKT_ENDPOINTS
from config.endpoints.lists import LISTS_ENDPOINTS


class TestListsEndpoints:
    """Test personal list endpoint templates."""

    def test_endpoints(self) -> None:
        assert LISTS_ENDPOINTS["user_lists"] == "/users/me/lists"
        assert LISTS_ENDPOINTS["user_list_items"] == "/users/me/lists/:list_id/items"
        assert (
            LISTS_ENDPOINTS["user_list_items_remove"]
            == "/users/me/lists/:list_id/items/remove"
        )

    def test_merged_into_combined_endpoints(self) -> None:
        for key, value in LISTS_ENDPOINTS.items():
            assert TRAKT_ENDPOINTS[key] == value
