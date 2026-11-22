"""Tests for the sync have-I-seen formatter and lookup."""

from datetime import datetime

from models.formatters.sync_seen import SyncSeenFormatters
from models.sync.seen import SeenEntry


def test_each_line_shape() -> None:
    entries = [
        SeenEntry(
            trakt_id=1,
            title="Inception",
            year=2010,
            watched=True,
            plays=2,
            last_watched_at=datetime.fromisoformat("2024-03-01T20:00:00+00:00"),
            rating=9,
        ),
        SeenEntry(trakt_id=2, title="Memento", year=2000, rating=8),
        SeenEntry(trakt_id=3),
    ]

    output = SyncSeenFormatters.format_seen(entries)

    assert "Checked: 3 | Watched: 1 | Not watched: 2" in output
    assert "1 | Inception (2010) | watched 2x | last 2024-03-01 | rated 9/10" in output
    assert "2 | Memento (2000) | not watched | rated 8/10" in output
    assert output.endswith("3 | not found in your watch history or ratings")
