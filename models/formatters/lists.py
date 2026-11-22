"""Personal list formatting methods for the Trakt MCP server."""

from models.lists import (
    TraktListItem,
    TraktListItemRef,
    TraktListItemsSummary,
    TraktListSummaryCount,
    TraktUserList,
)

_COUNT_LABELS = ("movies", "shows", "seasons", "episodes")


class ListsFormatters:
    """Helper class for formatting personal list data for MCP responses."""

    @staticmethod
    def format_user_lists(lists: list[TraktUserList]) -> str:
        """Format the authenticated user's lists."""
        if not lists:
            return (
                "# Your Lists\n\nYou have no lists yet. "
                "Use the `create_user_list` tool to create one."
            )

        lines = ["# Your Lists", "", f"Found {len(lists)} lists:", ""]
        lines.extend(ListsFormatters._format_list_line(item) for item in lists)
        return "\n".join(lines)

    @staticmethod
    def format_created_list(user_list: TraktUserList) -> str:
        """Format a freshly created list."""
        lines = ["# List Created", "", f"**{user_list.name}** ({user_list.privacy})"]
        if user_list.description:
            lines.extend(["", user_list.description])
        lines.extend(
            ["", f"List ID: {user_list.ids.trakt}", f"Slug: {user_list.ids.slug}"]
        )
        if user_list.share_link:
            lines.append(f"Share link: {user_list.share_link}")
        return "\n".join(lines)

    @staticmethod
    def format_list_items(items: list[TraktListItem], list_id: str) -> str:
        """Format every item on a list."""
        if not items:
            return f"# List Items\n\nList `{list_id}` is empty."

        lines = ["# List Items", "", f"Found {len(items)} items on `{list_id}`:", ""]
        lines.extend(ListsFormatters._format_item_line(item) for item in items)
        return "\n".join(lines)

    @staticmethod
    def format_items_summary(
        summary: TraktListItemsSummary, action: str, list_id: str
    ) -> str:
        """Format an add or remove summary.

        Args:
            summary: Trakt's response
            action: "added" or "removed"
            list_id: The list that was changed
        """
        lines = [f"# Items {action.capitalize()} ({list_id})", ""]

        if action == "added":
            lines.append(ListsFormatters._count_line("Added", summary.added))
            lines.append(
                ListsFormatters._count_line("Already on the list", summary.existing)
            )
        else:
            lines.append(ListsFormatters._count_line("Removed", summary.deleted))

        missing = [
            f"- {label[:-1]}: {ListsFormatters._describe_ref(entry)}"
            for label in _COUNT_LABELS
            for entry in getattr(summary.not_found, label)
        ]
        if missing:
            lines.extend(["", "Not found:", *missing])

        if summary.list and summary.list.item_count is not None:
            lines.extend(["", f"The list now has {summary.list.item_count} items."])
        return "\n".join(lines)

    @staticmethod
    def _describe_ref(entry: TraktListItemRef) -> str:
        if entry.title:
            return entry.title
        if entry.ids:
            pairs = entry.ids.model_dump(exclude_none=True)
            return ", ".join(f"{key} {value}" for key, value in pairs.items())
        return "unknown"

    @staticmethod
    def _count_line(label: str, counts: TraktListSummaryCount | None) -> str:
        counts = counts or TraktListSummaryCount()
        parts = [f"{getattr(counts, name)} {name}" for name in _COUNT_LABELS]
        return f"- {label}: {', '.join(parts)}"

    @staticmethod
    def _format_list_line(user_list: TraktUserList) -> str:
        return (
            f"- **{user_list.name}** (ID: {user_list.ids.trakt}, "
            f"slug: {user_list.ids.slug}): {user_list.item_count} items, "
            f"{user_list.privacy}"
        )

    @staticmethod
    def _format_item_line(item: TraktListItem) -> str:
        rank = f"{item.rank}. " if item.rank else "- "
        if item.type == "movie" and item.movie:
            year = f" ({item.movie.year})" if item.movie.year else ""
            return f"{rank}Movie: {item.movie.title}{year}"
        if item.type == "show" and item.show:
            year = f" ({item.show.year})" if item.show.year else ""
            return f"{rank}Show: {item.show.title}{year}"
        if item.type == "season" and item.show and item.season:
            return f"{rank}Season {item.season.number} of {item.show.title}"
        if item.type == "episode" and item.show and item.episode:
            return (
                f"{rank}Episode: {item.show.title} "
                f"S{item.episode.season:02d}E{item.episode.number:02d}"
            )
        return f"{rank}{item.type.capitalize()}"
