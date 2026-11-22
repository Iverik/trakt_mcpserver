"""Personal list endpoints."""

from collections.abc import Mapping
from typing import Final

from .keys import EndpointKey

LISTS_ENDPOINTS: Final[Mapping[EndpointKey, str]] = {
    "user_lists": "/users/me/lists",
    "user_list_items": "/users/me/lists/:list_id/items",
    "user_list_items_remove": "/users/me/lists/:list_id/items/remove",
}
