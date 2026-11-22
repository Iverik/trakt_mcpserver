"""Tests for UserFormatters.format_user_stats."""

from typing import Any

from models.formatters.user import NO_STATS_MESSAGE, UserFormatters
from models.user.stats import UserStats


def test_none_gives_no_stats_message() -> None:
    result = UserFormatters.format_user_stats(None)
    assert "Trakt returned no stats for this account (204 No Content)" in result
    assert NO_STATS_MESSAGE in result


def test_full_summary(user_stats_full: dict[str, Any]) -> None:
    result = UserFormatters.format_user_stats(UserStats.model_validate(user_stats_full))

    assert "**Total:** 5,732 plays, 4,910.5 h" in result
    assert "- **Movies:** 549 watched, 612 plays, 1,320.5 h" in result
    assert "- **Episodes:** 4,980 watched, 5,120 plays, 3,590.0 h" in result
    assert "- **Shows:** 87 watched" in result
    assert "- **Network:** 3 friends, 12 followers, 8 following" in result
    assert "## Ratings (803 total)" in result
    assert "- 8: 260" in result
    assert result.index("- 2: 1") < result.index("- 10: 97")


def test_partial_summary_skips_missing(user_stats_partial: dict[str, Any]) -> None:
    result = UserFormatters.format_user_stats(
        UserStats.model_validate(user_stats_partial)
    )

    assert "- **Movies:** 10 watched, 20.0 h" in result
    assert "Episodes" not in result
    assert "Seasons" not in result
    assert "**Total:**" not in result
    assert "- 8: 1.5" in result
