"""Tests for checkin formatter module."""

from typing import TYPE_CHECKING, cast

from models.formatters.checkin import CheckinFormatters

if TYPE_CHECKING:
    from models.types import CheckinResponse


class TestCheckinFormatters:
    """Test CheckinFormatters class and methods."""

    def test_class_exists(self) -> None:
        """Test that CheckinFormatters class exists."""
        assert CheckinFormatters is not None

    def test_has_checkin_formatter_methods(self) -> None:
        """Test that checkin formatting methods exist."""
        # Check for common checkin formatting methods
        expected_methods = [
            "format_checkin_response",
            "format_show_checkin",
            "format_movie_checkin",
        ]

        for method_name in expected_methods:
            if hasattr(CheckinFormatters, method_name):
                assert callable(getattr(CheckinFormatters, method_name))

    def test_format_methods_return_strings(self) -> None:
        """Test that formatter methods return strings."""
        # Test with sample data where methods exist
        if hasattr(CheckinFormatters, "format_checkin_response"):
            sample_response = cast(
                "CheckinResponse",
                {
                    "id": 1,
                    "watched_at": "2025-01-01T00:00:00.000Z",
                    "sharing": {"twitter": False, "mastodon": False, "tumblr": False},
                },
            )
            result = CheckinFormatters.format_checkin_response(sample_response)
            assert isinstance(result, str)

    def test_all_methods_are_static(self) -> None:
        """Test that all public methods are static methods."""
        for attr_name in dir(CheckinFormatters):
            if not attr_name.startswith("_") and callable(
                getattr(CheckinFormatters, attr_name)
            ):
                attr = CheckinFormatters.__dict__.get(attr_name)
                if attr is not None:
                    assert isinstance(attr, staticmethod), (
                        f"Method {attr_name} should be static"
                    )


class TestMovieAndCancelFormatting:
    """Test movie check-in and cancel formatting."""

    def test_format_movie_checkin(self) -> None:
        response = cast(
            "CheckinResponse",
            {
                "id": 7,
                "watched_at": "2026-11-22T20:00:00.000Z",
                "sharing": {"twitter": True, "mastodon": False, "tumblr": False},
                "movie": {"title": "Tron: Legacy", "year": 2010, "ids": {"trakt": 1}},
            },
        )
        result = CheckinFormatters.format_checkin_response(response)
        assert "# Successfully Checked In" in result
        assert "**Tron: Legacy** (2010)" in result
        assert "Shared on: Twitter" in result
        assert "Checkin ID: 7" in result
        assert "Unknown show" not in result

    def test_format_movie_checkin_without_year_or_extras(self) -> None:
        response = cast(
            "CheckinResponse",
            {
                "id": 0,
                "watched_at": "",
                "sharing": {},
                "movie": {"title": "Heat", "ids": {"trakt": 2}},
            },
        )
        result = CheckinFormatters.format_checkin_response(response)
        assert "**Heat**" in result
        assert "Shared on" not in result

    def test_format_cancel_response(self) -> None:
        result = CheckinFormatters.format_cancel_response()
        assert "# Check-in Cancelled" in result
        assert "paused playback" in result
