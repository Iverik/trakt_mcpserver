"""Formatting for the have-I-seen-it lookup."""

from models.formatters.utils import format_title_year
from models.sync.seen import SeenEntry


class SyncSeenFormatters:
    """Helper class for formatting watched and rated state per movie id."""

    @staticmethod
    def format_seen(entries: list[SeenEntry]) -> str:
        """Format one line per id.

        Args:
            entries: Watched state and rating for each requested id

        Returns:
            Markdown with a count header and one pipe-separated line per id
        """
        watched_count = sum(1 for entry in entries if entry.watched)
        lines = [
            "# Have you seen these movies?",
            "",
            f"Checked: {len(entries)} | Watched: {watched_count} | "
            + f"Not watched: {len(entries) - watched_count}",
            "",
        ]
        lines.extend(SyncSeenFormatters._format_entry(entry) for entry in entries)
        return "\n".join(lines)

    @staticmethod
    def _format_entry(entry: SeenEntry) -> str:
        parts = [str(entry.trakt_id)]
        if entry.title:
            parts.append(format_title_year(entry.title, entry.year))
        if entry.watched:
            plays = f"watched {entry.plays}x" if entry.plays else "watched"
            parts.append(plays)
            if entry.last_watched_at:
                parts.append(f"last {entry.last_watched_at.strftime('%Y-%m-%d')}")
        elif entry.rating is None:
            parts.append("not found in your watch history or ratings")
        else:
            parts.append("not watched")
        if entry.rating is not None:
            parts.append(f"rated {entry.rating}/10")
        return " | ".join(parts)
