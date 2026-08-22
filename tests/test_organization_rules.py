"""Tests for the versioned, declarative organization-rule workflow."""

from __future__ import annotations

import json

import pytest

from bookmark_organizer_pro.core import CategoryManager
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.organization_rules import (
    ORGANIZATION_RULES_SCHEMA,
    ORGANIZATION_RULES_VERSION,
    OrganizationRule,
    OrganizationRulesService,
)


def _manager(tmp_path, *bookmarks: Bookmark) -> BookmarkManager:
    tmp_path.mkdir(parents=True, exist_ok=True)
    manager = BookmarkManager(
        CategoryManager(filepath=tmp_path / "categories.json"),
        TagManager(filepath=tmp_path / "tags.json"),
        filepath=tmp_path / "bookmarks.json",
    )
    for bookmark in bookmarks:
        manager.add_bookmark(bookmark, save=False)
    if bookmarks:
        manager.save_bookmarks()
    return manager


def _service(tmp_path, monkeypatch, manager) -> OrganizationRulesService:
    monkeypatch.setattr(OrganizationRulesService, "RULES_FILE", tmp_path / "organization_rules.json")
    monkeypatch.setattr(OrganizationRulesService, "LEGACY_RULES_FILE", tmp_path / "smart_tag_rules.json")
    return OrganizationRulesService(manager)


def _domain_condition(value="example.com"):
    return {"field": "domain", "operator": "equals", "value": value}


def test_rule_schema_is_strict_and_actions_are_allowlisted():
    with pytest.raises(ValueError, match="Unsupported condition field"):
        OrganizationRule(
            name="Unsafe",
            conditions=({"field": "python", "operator": "equals", "value": "x"},),
            actions=({"action": "add_tag", "value": "x"},),
        )
    with pytest.raises(ValueError, match="Unsupported organization action"):
        OrganizationRule(
            name="Unsafe",
            conditions=(_domain_condition(),),
            actions=({"action": "run_code", "value": "__import__('os')"},),
        )
    with pytest.raises(ValueError, match="Invalid regex"):
        OrganizationRule(
            name="Broken regex",
            conditions=({"field": "title", "operator": "regex", "value": "["},),
            actions=({"action": "add_tag", "value": "x"},),
        )


def test_legacy_smart_tag_rules_migrate_to_versioned_document(tmp_path, monkeypatch):
    legacy_path = tmp_path / "smart_tag_rules.json"
    legacy_path.write_text(
        json.dumps(
            [
                {
                    "name": "GitHub",
                    "tag": "code",
                    "conditions": [_domain_condition("github.com")],
                    "enabled": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    service = _service(tmp_path, monkeypatch, _manager(tmp_path))
    assert len(service.rules) == 1
    assert service.rules[0].actions == ({"action": "add_tag", "value": "code"},)
    document = json.loads((tmp_path / "organization_rules.json").read_text(encoding="utf-8"))
    assert document["schema"] == ORGANIZATION_RULES_SCHEMA
    assert document["schema_version"] == ORGANIZATION_RULES_VERSION


def test_preview_is_deterministic_and_reports_conflicting_actions(tmp_path, monkeypatch):
    manager = _manager(
        tmp_path,
        Bookmark(id=20, url="https://example.com/two", title="Two"),
        Bookmark(id=10, url="https://example.com/one", title="One"),
    )
    service = _service(tmp_path, monkeypatch, manager)
    service.add_rule(
        OrganizationRule(
            name="Tag examples",
            conditions=(_domain_condition(),),
            actions=({"action": "add_tag", "value": "reference"},),
        )
    )
    service.add_rule(
        OrganizationRule(
            name="Category A",
            conditions=(_domain_condition(),),
            actions=({"action": "set_category", "value": "A"},),
        )
    )
    service.add_rule(
        OrganizationRule(
            name="Category B",
            conditions=(_domain_condition(),),
            actions=({"action": "set_category", "value": "B"},),
        )
    )
    preview = service.preview()
    assert preview.scope_ids == (10, 20)
    assert preview.affected_count == 2
    assert [(change.bookmark_id, change.field) for change in preview.changes] == [
        (10, "tags"),
        (20, "tags"),
    ]
    assert preview.conflict_count == 2
    assert all(conflict.field == "category" for conflict in preview.conflicts)
    assert manager.get_bookmark(10).tags == []


def test_apply_uses_one_atomic_save_and_undo_restores_exact_snapshots(tmp_path, monkeypatch):
    bookmark = Bookmark(
        id=1,
        url="https://example.com/one",
        title="One",
        tags=["old"],
        modified_at="before",
    )
    manager = _manager(tmp_path, bookmark)
    service = _service(tmp_path, monkeypatch, manager)
    service.add_rule(
        OrganizationRule(
            name="Organize",
            conditions=(_domain_condition(),),
            actions=(
                {"action": "add_tag", "value": "new"},
                {"action": "set_pinned", "value": True},
            ),
        )
    )
    calls = []
    original_save = manager.storage.save

    def save_once(payload, expected_revision=0):
        calls.append(list(payload))
        return original_save(payload, expected_revision=expected_revision)

    monkeypatch.setattr(manager.storage, "save", save_once)
    report = service.apply()
    assert report.status == "applied"
    assert report.undo_available is True
    assert len(calls) == 1
    assert manager.get_bookmark(1).tags == ["old", "new"]
    assert manager.get_bookmark(1).is_pinned is True

    undo = service.undo_last()
    assert undo.status == "undone"
    assert len(calls) == 2
    restored = manager.get_bookmark(1)
    assert restored.tags == ["old"]
    assert restored.is_pinned is False
    assert restored.modified_at == "before"


def test_failed_batch_does_not_leave_partial_rule_changes(tmp_path, monkeypatch):
    manager = _manager(tmp_path, Bookmark(id=1, url="https://example.com", title="Example"))
    service = _service(tmp_path, monkeypatch, manager)
    service.add_rule(
        OrganizationRule(
            name="Failing save",
            conditions=(_domain_condition(),),
            actions=({"action": "add_tag", "value": "should-not-stick"},),
        )
    )

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(manager.storage, "save", fail_save)
    report = service.apply()
    assert report.status == "failed"
    assert manager.get_bookmark(1).tags == []
    assert service.undo_last().status == "no_undo"


def test_stale_preview_is_rejected_without_mutation(tmp_path, monkeypatch):
    manager = _manager(tmp_path, Bookmark(id=1, url="https://example.com", title="Example"))
    service = _service(tmp_path, monkeypatch, manager)
    service.add_rule(
        OrganizationRule(
            name="Tag",
            conditions=(_domain_condition(),),
            actions=({"action": "add_tag", "value": "reference"},),
        )
    )
    preview = service.preview()
    manager.bookmarks[1].title = "Changed outside preview"
    report = service.apply(preview)
    assert report.status == "stale"
    assert manager.get_bookmark(1).tags == []


def test_import_and_export_round_trip_only_versioned_rules(tmp_path, monkeypatch):
    source = _service(tmp_path / "source", monkeypatch, _manager(tmp_path / "source"))
    source.add_rule(
        OrganizationRule(
            name="Export me",
            conditions=(_domain_condition(),),
            actions=({"action": "set_read_later", "value": True},),
        )
    )
    exported = tmp_path / "rules-export.json"
    assert source.export_rules(exported) == exported
    document = json.loads(exported.read_text(encoding="utf-8"))
    assert set(document) == {"schema", "schema_version", "rules"}

    target = _service(tmp_path / "target", monkeypatch, _manager(tmp_path / "target"))
    assert target.import_rules(exported) == 1
    assert target.rules[0].name == "Export me"
    assert target.rules[0].actions[0]["action"] == "set_read_later"
