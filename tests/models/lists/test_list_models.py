"""Tests for personal list models."""

import pytest
from pydantic import ValidationError

from models.lists import (
    TraktCreateListRequest,
    TraktListItemsRequest,
    TraktListItemsSummary,
)


class TestCreateListRequest:
    def test_name_only_dumps_without_nulls(self) -> None:
        request = TraktCreateListRequest(name="Weekend Watch")
        assert request.model_dump(mode="json", exclude_none=True) == {
            "name": "Weekend Watch"
        }

    @pytest.mark.parametrize("privacy", ["private", "link", "friends", "public"])
    def test_valid_privacy(self, privacy: str) -> None:
        request = TraktCreateListRequest.model_validate(
            {"name": "x", "privacy": privacy}
        )
        assert request.privacy == privacy

    @pytest.mark.parametrize("privacy", ["secret", "Public", ""])
    def test_invalid_privacy(self, privacy: str) -> None:
        with pytest.raises(ValidationError):
            TraktCreateListRequest.model_validate({"name": "x", "privacy": privacy})

    def test_name_required(self) -> None:
        with pytest.raises(ValidationError):
            TraktCreateListRequest.model_validate({"description": "no name"})
        with pytest.raises(ValidationError):
            TraktCreateListRequest(name="")

    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TraktCreateListRequest.model_validate({"name": "x", "sort_by": "rank"})


class TestListItemsRequest:
    def test_movies_only(self) -> None:
        request = TraktListItemsRequest.model_validate(
            {"movies": [{"ids": {"trakt": "120"}}]}
        )
        assert request.model_dump(mode="json", exclude_none=True) == {
            "movies": [{"ids": {"trakt": 120}}]
        }

    def test_requires_one_collection(self) -> None:
        with pytest.raises(ValidationError, match="movies or shows"):
            TraktListItemsRequest.model_validate({})

    def test_rejects_both_collections(self) -> None:
        with pytest.raises(ValidationError, match="Only one"):
            TraktListItemsRequest.model_validate(
                {"movies": [{"ids": {"trakt": 1}}], "shows": [{"ids": {"trakt": 2}}]}
            )

    def test_rejects_empty_collection(self) -> None:
        with pytest.raises(ValidationError):
            TraktListItemsRequest.model_validate({"movies": []})

    def test_rejects_unsupported_collection(self) -> None:
        with pytest.raises(ValidationError):
            TraktListItemsRequest.model_validate({"seasons": [{"ids": {"trakt": 1}}]})


class TestListItemsSummary:
    def test_add_shape(self) -> None:
        summary = TraktListItemsSummary.model_validate(
            {
                "added": {"movies": 2, "shows": 0, "seasons": 0, "episodes": 0},
                "existing": {"movies": 1, "shows": 0, "seasons": 0, "episodes": 0},
                "not_found": {"movies": [], "shows": [], "seasons": [], "episodes": []},
                "list": {"updated_at": "2026-11-22T10:00:00.000Z", "item_count": 9},
            }
        )
        assert summary.added is not None
        assert summary.added.movies == 2
        assert summary.existing is not None
        assert summary.existing.movies == 1
        assert summary.deleted is None

    def test_remove_shape(self) -> None:
        summary = TraktListItemsSummary.model_validate(
            {"deleted": {"movies": 3}, "not_found": {}}
        )
        assert summary.deleted is not None
        assert summary.deleted.movies == 3
        assert summary.deleted.shows == 0
        assert summary.added is None
