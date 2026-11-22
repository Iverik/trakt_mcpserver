"""Tests for the user stats model."""

from typing import Any

from models.user.stats import UserStats


def test_full_response_parses(user_stats_full: dict[str, Any]) -> None:
    stats = UserStats.model_validate(user_stats_full)
    assert stats.movies is not None and stats.movies.watched == 549
    assert stats.episodes is not None and stats.episodes.plays == 5120
    assert stats.network is not None and stats.network.followers == 12
    assert stats.progress is not None and stats.progress.dropped == 5
    assert stats.total_minutes == 294630


def test_partial_response_parses(user_stats_partial: dict[str, Any]) -> None:
    stats = UserStats.model_validate(user_stats_partial)
    assert stats.movies is not None and stats.movies.collected is None
    assert stats.seasons is None
    assert stats.ratings is not None and stats.ratings.distribution == {"8": 1.5}


def test_null_optional_sections_and_unknown_fields() -> None:
    stats = UserStats.model_validate({"progress": None, "lists": None, "new": 1})
    assert stats.progress is None
    assert stats.lists is None
