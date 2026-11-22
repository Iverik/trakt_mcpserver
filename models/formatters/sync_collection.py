"""Sync collection formatting methods for the Trakt MCP server."""

from models.formatters.utils import format_title_year
from models.sync.collection import (
    CollectionFetchResult,
    CollectionItem,
    CollectionMetadata,
)


class SyncCollectionFormatters:
    """Helper class for formatting the user's collection for MCP responses."""

    @staticmethod
    def format_user_collection(
        result: CollectionFetchResult, collection_type: str
    ) -> str:
        """Format a full collection as one compact line per item.

        Args:
            result: Every collection item fetched across all pages
            collection_type: Collection that was fetched (movies or shows)

        Returns:
            Markdown starting with a total count line
        """
        count = len(result.items)
        noun = collection_type[:-1] if count == 1 else collection_type
        lines: list[str] = [f"# Your Collection ({collection_type})", ""]
        lines.append(f"Total: {count} {noun}")

        if result.truncated:
            lines.append(
                f"WARNING: stopped after {result.pages_fetched} pages; "
                + "this list is incomplete."
            )
        if not result.items:
            return "\n".join(lines)

        lines.append("")
        lines.extend(
            SyncCollectionFormatters._format_item(item) for item in result.items
        )
        return "\n".join(lines)

    @staticmethod
    def _format_item(item: CollectionItem) -> str:
        """Format one collection item as a single markdown list line."""
        media = item.movie or item.show
        if media is None:
            return "- Unknown"
        line = f"- {format_title_year(media.title, media.year)}"

        if item.movie is not None:
            if item.collected_at:
                line += f", collected {item.collected_at.strftime('%Y-%m-%d')}"
            details = SyncCollectionFormatters._format_metadata(item.metadata)
            if details:
                line += f" ({details})"
        else:
            episodes = item.collected_episode_count
            line += f", {episodes} {'episode' if episodes == 1 else 'episodes'}"
        return line

    @staticmethod
    def _format_metadata(metadata: CollectionMetadata | None) -> str:
        """Join the resolution, HDR and audio values that are present."""
        if metadata is None:
            return ""
        parts = (metadata.resolution, metadata.hdr, metadata.audio)
        return ", ".join(part for part in parts if part)
