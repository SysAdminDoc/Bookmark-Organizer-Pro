"""Validation, quarantine, and boundary semantics for saved smart queries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from bookmark_organizer_pro.cli import BookmarkCLI
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.smart_collections import (
    SmartCollection,
    SmartCollectionDiagnostic,
    SmartCollectionFilter,
    SmartCollectionManager,
)


def _bookmark(url: str, created_at: str = "2026-01-01T12:00:00Z") -> Bookmark:
    return Bookmark(id=None, url=url, title="Example", created_at=created_at)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/openai", True),
        ("https://docs.github.com/page", True),
        ("https://evilgithub.com/page", False),
        ("https://github.com.evil.example/page", False),
    ],
)
def test_domain_filters_use_host_boundaries(url: str, expected: bool) -> None:
    collection = SmartCollection(
        id="domain",
        name="GitHub",
        filters=SmartCollectionFilter(domains=["GitHub.com"]),
    )

    assert collection.matches(_bookmark(url)) is expected


def test_date_comparisons_normalize_aware_and_naive_values_to_utc() -> None:
    collection = SmartCollection(
        id="dates",
        name="Dates",
        filters=SmartCollectionFilter(after="2026-01-01T12:00:00+02:00"),
    )

    assert not collection.matches(_bookmark("https://early.example", "2026-01-01T09:59:59Z"))
    assert collection.matches(_bookmark("https://aware.example", "2026-01-01T10:00:00Z"))
    assert collection.matches(_bookmark("https://naive.example", "2026-01-01T10:00:01"))
    assert not collection.matches(_bookmark("https://malformed.example", "not-a-date"))


@pytest.mark.parametrize(
    "filters,error",
    [
        (SmartCollectionFilter(tags="python"), "tags must be a list"),
        (SmartCollectionFilter(tags=["python", 3]), "non-empty strings"),
        (SmartCollectionFilter(after="not-a-date"), "valid ISO-8601"),
        (
            SmartCollectionFilter(after="2026-02-01", before="2026-01-01"),
            "after must not be later",
        ),
        (SmartCollectionFilter(domains=["https://github.com/path"]), "Invalid domain"),
    ],
)
def test_create_rejects_invalid_filter_shapes_and_dates(
    tmp_path: Path,
    filters: SmartCollectionFilter,
    error: str,
) -> None:
    manager = SmartCollectionManager(tmp_path / "smart.json")

    with pytest.raises(ValueError, match=error):
        manager.create("Invalid", filters)

    assert manager.list_all() == []


def test_update_rejects_invalid_filters_without_mutating_saved_state(tmp_path: Path) -> None:
    manager = SmartCollectionManager(tmp_path / "smart.json")
    collection = manager.create("Original", SmartCollectionFilter(tags=["python"]))
    original_bytes = (tmp_path / "smart.json").read_bytes()

    with pytest.raises(ValueError, match="valid ISO-8601"):
        manager.update(collection.id, filters=SmartCollectionFilter(after="soon"))

    assert manager.get(collection.id).name == "Original"
    assert manager.get(collection.id).filters.tags == ["python"]
    assert (tmp_path / "smart.json").read_bytes() == original_bytes


def test_load_quarantines_invalid_rules_and_preserves_them_across_saves(tmp_path: Path) -> None:
    path = tmp_path / "smart.json"
    invalid = {
        "id": "invalid-date",
        "name": "Broken date",
        "filters": {"after": "eventually"},
    }
    path.write_text(
        json.dumps(
            [
                {
                    "id": "valid",
                    "name": "Valid",
                    "filters": {"domains": ["example.com"]},
                },
                invalid,
            ]
        ),
        encoding="utf-8",
    )

    manager = SmartCollectionManager(path)

    assert [collection.id for collection in manager.list_all()] == ["valid"]
    assert len(manager.diagnostics) == 1
    assert "Broken date" in manager.diagnostics[0].message
    assert "valid ISO-8601" in manager.diagnostics[0].message

    manager.create("New", SmartCollectionFilter(tags=["saved"]))
    reloaded = SmartCollectionManager(path)
    assert {collection.name for collection in reloaded.list_all()} == {"Valid", "New"}
    assert len(reloaded.diagnostics) == 1
    assert reloaded.diagnostics[0].collection_id == "invalid-date"


def test_cli_surfaces_quarantine_diagnostics_on_stderr(capsys) -> None:
    manager = Mock()
    manager.list_all.return_value = []
    manager.diagnostics = [
        SmartCollectionDiagnostic(0, "broken", "Broken", "after must be ISO-8601")
    ]
    cli = BookmarkCLI.__new__(BookmarkCLI)
    namespace = argparse.Namespace(action="list")

    with patch(
        "bookmark_organizer_pro.services.smart_collections.SmartCollectionManager",
        return_value=manager,
    ):
        code = cli._cmd_smart_collections(namespace)

    assert code == 1
    captured = capsys.readouterr()
    assert "Skipped invalid smart collection" in captured.err
    assert captured.out == ""


def test_cli_create_rejects_invalid_dates_before_persistence(tmp_path: Path, capsys) -> None:
    manager = SmartCollectionManager(tmp_path / "smart.json")
    cli = BookmarkCLI.__new__(BookmarkCLI)
    namespace = argparse.Namespace(
        action="create",
        collection_id="Recent research",
        name=None,
        icon=None,
        tags="research",
        categories=None,
        domains="example.com",
        content_types=None,
        keywords=None,
        after="not-a-date",
        before=None,
        read_later_only=None,
        has_snapshot=None,
    )

    with patch(
        "bookmark_organizer_pro.services.smart_collections.SmartCollectionManager",
        return_value=manager,
    ):
        code = cli._cmd_smart_collections(namespace)

    assert code == 2
    assert manager.list_all() == []
    assert "valid ISO-8601" in capsys.readouterr().err
