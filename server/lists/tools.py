"""Personal list tools for the Trakt MCP server."""

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, ClassVar

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationError, field_validator

from client.lists.client import ListsClient
from client.pool import get_client
from client.validation import validate_media_id
from config.mcp.annotations import DESTRUCTIVE, READ_ONLY, WRITE
from config.mcp.descriptions import (
    LIST_DESCRIPTION_DESCRIPTION,
    LIST_ID_DESCRIPTION,
    LIST_ITEM_TYPE_DESCRIPTION,
    LIST_ITEMS_DESCRIPTION,
    LIST_NAME_DESCRIPTION,
    LIST_PRIVACY_DESCRIPTION,
    LIST_REMOVE_ITEMS_DESCRIPTION,
)
from models.formatters.lists import ListsFormatters
from models.lists import (
    ListItemType,
    ListPrivacy,
    TraktCreateListRequest,
    TraktListItemRef,
    TraktListItemsRequest,
)
from models.types.ids import TraktIds
from server.base import IdentifierValidatorMixin, ToolErrors
from utils.api.errors import handle_api_errors_func

logger = logging.getLogger("trakt_mcp")

type ToolHandler = Callable[..., Awaitable[str]]


class UserListItem(IdentifierValidatorMixin):
    """A movie or show to add to, or remove from, a personal list."""

    _identifier_error_prefix: ClassVar[str] = "List item"


class UserListIdParam(BaseModel):
    """Validated list identifier."""

    list_id: str

    @field_validator("list_id", mode="after")
    @classmethod
    def _validate_list_id(cls, value: str) -> str:
        return validate_media_id(value, "list_id")


def _validation_error(error: ValidationError, operation: str) -> Exception:
    messages = [
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in error.errors()
    ]
    return ToolErrors.handle_validation_error(
        f"Invalid parameters for {operation.replace('_', ' ')}: " + "; ".join(messages),
        operation=f"{operation}_validation",
    )


def _validated_list_id(list_id: str, operation: str) -> str:
    try:
        return UserListIdParam(list_id=list_id).list_id
    except ValidationError as e:
        raise _validation_error(e, operation) from e


def _build_items_request(
    item_type: ListItemType, items: list[UserListItem], operation: str
) -> TraktListItemsRequest:
    refs = [
        TraktListItemRef(
            title=item.title,
            year=item.year,
            ids=TraktIds.model_validate(ids)
            if (ids := item.build_ids_dict())
            else None,
        )
        for item in items
    ]
    try:
        return TraktListItemsRequest.model_validate({item_type: refs})
    except ValidationError as e:
        raise _validation_error(e, operation) from e


@handle_api_errors_func
async def fetch_user_lists() -> str:
    """Fetch the authenticated user's personal lists from Trakt.

    Returns:
        Markdown list of every personal list with its ID, slug and item count

    Raises:
        AuthenticationRequiredError: If user is not authenticated
    """
    client = get_client(ListsClient)
    result = await client.get_user_lists()
    if isinstance(result, str):
        raise ToolErrors.handle_api_string_error(
            resource_type="user_lists",
            resource_id="authenticated_user",
            error_message=result,
            operation="fetch_user_lists",
        )
    return ListsFormatters.format_user_lists(result)


@handle_api_errors_func
async def create_user_list(
    name: str,
    description: str | None = None,
    privacy: ListPrivacy | None = None,
) -> str:
    """Create a personal list for the authenticated user.

    Args:
        name: Name of the list
        description: Optional list description
        privacy: Optional visibility: private, link, friends or public

    Returns:
        Confirmation with the new list's ID and slug

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InvalidParamsError: If name is empty or privacy is not a valid value
    """
    try:
        request = TraktCreateListRequest.model_validate(
            {"name": name.strip(), "description": description, "privacy": privacy}
        )
    except ValidationError as e:
        raise _validation_error(e, "create_user_list") from e

    client = get_client(ListsClient)
    result = await client.create_user_list(request)
    if isinstance(result, str):
        raise ToolErrors.handle_api_string_error(
            resource_type="user_list",
            resource_id=request.name,
            error_message=result,
            operation="create_user_list",
        )
    return ListsFormatters.format_created_list(result)


@handle_api_errors_func
async def fetch_user_list_items(list_id: str) -> str:
    """Fetch every item on one of the authenticated user's lists.

    Args:
        list_id: Trakt list ID or slug

    Returns:
        Markdown list of all items, following every page

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InvalidParamsError: If list_id is empty or malformed
    """
    list_id = _validated_list_id(list_id, "fetch_user_list_items")
    client = get_client(ListsClient)
    result = await client.get_user_list_items(list_id)
    if isinstance(result, str):
        raise ToolErrors.handle_api_string_error(
            resource_type="user_list_items",
            resource_id=list_id,
            error_message=result,
            operation="fetch_user_list_items",
        )
    return ListsFormatters.format_list_items(result, list_id)


@handle_api_errors_func
async def add_user_list_items(
    list_id: str,
    item_type: ListItemType,
    items: list[UserListItem],
) -> str:
    """Add movies or shows to one of the authenticated user's lists.

    Args:
        list_id: Trakt list ID or slug
        item_type: 'movies' or 'shows'
        items: Items to add, identified by ID or by title and year

    Returns:
        Counts of added, already present and not found items

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InvalidParamsError: If list_id or items are invalid
    """
    list_id = _validated_list_id(list_id, "add_user_list_items")
    request = _build_items_request(item_type, items, "add_user_list_items")
    client = get_client(ListsClient)
    result = await client.add_user_list_items(list_id, request)
    if isinstance(result, str):
        raise ToolErrors.handle_api_string_error(
            resource_type="user_list_items",
            resource_id=list_id,
            error_message=result,
            operation="add_user_list_items",
        )
    return ListsFormatters.format_items_summary(result, "added", list_id)


@handle_api_errors_func
async def remove_user_list_items(
    list_id: str,
    item_type: ListItemType,
    items: list[UserListItem],
) -> str:
    """Remove movies or shows from one of the authenticated user's lists.

    Args:
        list_id: Trakt list ID or slug
        item_type: 'movies' or 'shows'
        items: Items to remove, each with at least one ID (title and year
            alone are not enough to remove an item)

    Returns:
        Counts of removed and not found items

    Raises:
        AuthenticationRequiredError: If user is not authenticated
        InvalidParamsError: If list_id or items are invalid, or an item has
            no ID
    """
    list_id = _validated_list_id(list_id, "remove_user_list_items")
    for index, item in enumerate(items):
        if not item.build_ids_dict():
            raise ToolErrors.handle_validation_error(
                f"items.{index}: removal needs at least one ID "
                + "(trakt_id, slug, imdb_id, tmdb_id or tvdb_id); "
                + "title and year alone are not accepted",
                operation="remove_user_list_items_validation",
            )
    request = _build_items_request(item_type, items, "remove_user_list_items")
    client = get_client(ListsClient)
    result = await client.remove_user_list_items(list_id, request)
    if isinstance(result, str):
        raise ToolErrors.handle_api_string_error(
            resource_type="user_list_items",
            resource_id=list_id,
            error_message=result,
            operation="remove_user_list_items",
        )
    return ListsFormatters.format_items_summary(result, "removed", list_id)


def register_lists_tools(
    mcp: FastMCP,
) -> tuple[ToolHandler, ToolHandler, ToolHandler, ToolHandler, ToolHandler]:
    """Register personal list tools with the MCP server.

    Returns:
        Tuple of tool handlers for type checker visibility
    """

    @mcp.tool(
        name="fetch_user_lists",
        annotations=READ_ONLY,
        description=(
            "Fetch the authenticated user's personal lists from Trakt. "
            "Requires OAuth authentication."
        ),
    )
    async def fetch_user_lists_tool() -> str:
        return await fetch_user_lists()

    @mcp.tool(
        name="create_user_list",
        annotations=WRITE,
        description=(
            "Create a new personal list on Trakt. Lists are private unless "
            "privacy is set. Requires OAuth authentication."
        ),
    )
    async def create_user_list_tool(
        name: Annotated[str, Field(min_length=1, description=LIST_NAME_DESCRIPTION)],
        description: Annotated[
            str | None, Field(description=LIST_DESCRIPTION_DESCRIPTION)
        ] = None,
        privacy: Annotated[
            ListPrivacy | None, Field(description=LIST_PRIVACY_DESCRIPTION)
        ] = None,
    ) -> str:
        return await create_user_list(name, description, privacy)

    @mcp.tool(
        name="fetch_user_list_items",
        annotations=READ_ONLY,
        description=(
            "Fetch all items on one of the authenticated user's personal lists, "
            "following every page. Requires OAuth authentication."
        ),
    )
    async def fetch_user_list_items_tool(
        list_id: Annotated[str, Field(description=LIST_ID_DESCRIPTION)],
    ) -> str:
        return await fetch_user_list_items(list_id)

    @mcp.tool(
        name="add_user_list_items",
        annotations=WRITE,
        description=(
            "Add movies or shows to one of the authenticated user's personal "
            "lists. Reports how many were added, already present or not found. "
            "Requires OAuth authentication."
        ),
    )
    async def add_user_list_items_tool(
        list_id: Annotated[str, Field(description=LIST_ID_DESCRIPTION)],
        item_type: Annotated[
            ListItemType, Field(description=LIST_ITEM_TYPE_DESCRIPTION)
        ],
        items: Annotated[
            list[UserListItem],
            Field(min_length=1, description=LIST_ITEMS_DESCRIPTION),
        ],
    ) -> str:
        return await add_user_list_items(list_id, item_type, items)

    @mcp.tool(
        name="remove_user_list_items",
        annotations=DESTRUCTIVE,
        description=(
            "Remove movies or shows from one of the authenticated user's "
            "personal lists. Reports how many were removed or not found. "
            "Requires OAuth authentication."
        ),
    )
    async def remove_user_list_items_tool(
        list_id: Annotated[str, Field(description=LIST_ID_DESCRIPTION)],
        item_type: Annotated[
            ListItemType, Field(description=LIST_ITEM_TYPE_DESCRIPTION)
        ],
        items: Annotated[
            list[UserListItem],
            Field(min_length=1, description=LIST_REMOVE_ITEMS_DESCRIPTION),
        ],
    ) -> str:
        return await remove_user_list_items(list_id, item_type, items)

    return (
        fetch_user_lists_tool,
        create_user_list_tool,
        fetch_user_list_items_tool,
        add_user_list_items_tool,
        remove_user_list_items_tool,
    )
