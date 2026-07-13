"""Focused tests for non-blocking recovery services and durable category undo."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path

from bookmark_organizer_pro.models import Bookmark, Category
from bookmark_organizer_pro.services.category_delete_recovery import CategoryDeleteRecovery
from bookmark_organizer_pro.services.recovery_workflow import RecoveryWorkflow
from bookmark_organizer_pro.ui.live_workflow import LiveWorkflowDialog


@dataclass
class _Status:
    path: Path
    count: int
    recovery_required: bool = False


class _RecoveryManager:
    def __init__(self, tmp_path: Path):
        self.filepath = tmp_path / "bookmarks.json"
        self.filepath.write_text("[]", encoding="utf-8")
        self.bookmarks = [Bookmark(id=1, url="https://example.com", title="Example")]
        self.storage_status = _Status(self.filepath, 1)
        self.recovery_required = False
        self.recovery_message = ""
        self.restores: list[str] = []
        self.restore_ok = True

    def list_backups(self):
        return [("backup.json", None, 2)]

    def create_safepoint(self, _label):
        return "safepoints/pre-restore.json"

    def restore_backup(self, name):
        self.restores.append(name)
        return self.restore_ok or name.startswith("safepoints/")

    def get_all_bookmarks(self):
        return list(self.bookmarks)


def test_restore_failure_rolls_back_and_reports_preserved_source(tmp_path):
    manager = _RecoveryManager(tmp_path)
    manager.restore_ok = False
    progress = []

    result = RecoveryWorkflow(manager, lambda *event: progress.append(event)).restore("backup.json")

    assert not result.success
    assert manager.restores == ["backup.json", "safepoints/pre-restore.json"]
    assert result.preserved_source == "safepoints/pre-restore.json"
    assert "previous library was restored" in result.summary
    assert [event[1] for event in progress] == [
        "Selected recovery source",
        "Protected current library",
    ]


def test_restore_success_has_validated_terminal_progress(tmp_path):
    manager = _RecoveryManager(tmp_path)
    progress = []

    result = RecoveryWorkflow(manager, lambda *event: progress.append(event)).restore("backup.json")

    assert result.success
    assert result.recovered_count == 1
    assert progress[-1][1] == "Validated restored library"
    assert "validated 1 bookmark" in result.summary


def test_live_workflow_external_runner_terminal_state_without_desktop():
    dialog = LiveWorkflowDialog.__new__(LiveWorkflowDialog)
    scheduled = []
    dialog._schedule_pump = lambda: scheduled.append(True)
    dialog._finished = False
    dialog._finish_summary = None
    dialog._finish_outcome = "success"

    dialog.start()
    dialog.signal_finish("Restore failed validation", outcome="error")

    assert scheduled == [True]
    assert dialog._finished
    assert dialog._finish_summary == "Restore failed validation"
    assert dialog._finish_outcome == "error"


class _CategoryManager:
    def __init__(self, path: Path):
        self.filepath = path
        self.categories = {
            "Dev": Category("Dev", patterns=["github.com"], icon="D"),
            "Uncategorized / Needs Review": Category("Uncategorized / Needs Review", icon="?"),
        }
        self.save_categories()

    def save_categories(self):
        self.filepath.write_text(
            json.dumps({name: category.to_dict() for name, category in self.categories.items()}),
            encoding="utf-8",
        )

    def _rebuild_patterns(self):
        return None


class _CategoryBookmarkManager:
    def __init__(self):
        self.bookmarks = {
            1: Bookmark(id=1, url="https://example.com/1", title="One", category="Dev"),
            2: Bookmark(id=2, url="https://example.com/2", title="Two", category="Dev"),
        }
        self.snapshots = {}
        self.fail_updates = False

    def get_bookmarks_by_category(self, category):
        return [bookmark for bookmark in self.bookmarks.values() if bookmark.category == category]

    def get_bookmark(self, bookmark_id):
        return self.bookmarks.get(bookmark_id)

    def update_bookmark(self, bookmark):
        if self.fail_updates:
            self.fail_updates = False
            raise OSError("simulated bookmark write failure")
        self.bookmarks[bookmark.id] = bookmark
        return bookmark

    def create_safepoint(self, label):
        name = f"safepoints/{label}-{len(self.snapshots)}.json"
        self.snapshots[name] = {key: value.category for key, value in self.bookmarks.items()}
        return name

    def restore_backup(self, name):
        snapshot = self.snapshots.get(name)
        if snapshot is None:
            return False
        for bookmark_id, category in snapshot.items():
            self.bookmarks[bookmark_id].category = category
        return True

    def batch(self):
        return contextlib.nullcontext()


def test_category_delete_recovery_survives_restart(tmp_path):
    categories = _CategoryManager(tmp_path / "categories.json")
    bookmarks = _CategoryBookmarkManager()
    path = tmp_path / "category-delete.json"

    first_session = CategoryDeleteRecovery(categories, bookmarks, path)
    record = first_session.delete("Dev")
    assert record["state"] == "ready"
    assert "Dev" not in categories.categories
    assert {bookmark.category for bookmark in bookmarks.bookmarks.values()} == {
        "Uncategorized / Needs Review"
    }

    restarted = CategoryDeleteRecovery(categories, bookmarks, path)
    assert restarted.pending()["name"] == "Dev"
    name, restored = restarted.restore()

    assert (name, restored) == ("Dev", 2)
    assert "Dev" in categories.categories
    assert {bookmark.category for bookmark in bookmarks.bookmarks.values()} == {"Dev"}
    assert restarted.pending() is None


def test_category_delete_failure_rolls_back_to_durable_safepoint(tmp_path):
    categories = _CategoryManager(tmp_path / "categories.json")
    bookmarks = _CategoryBookmarkManager()
    bookmarks.fail_updates = True
    recovery = CategoryDeleteRecovery(categories, bookmarks, tmp_path / "category-delete.json")

    try:
        recovery.delete("Dev")
    except RuntimeError as exc:
        assert "rollback completed" in str(exc)
        assert "bookmark safepoint" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("category deletion unexpectedly succeeded")

    assert "Dev" in categories.categories
    assert {bookmark.category for bookmark in bookmarks.bookmarks.values()} == {"Dev"}
    assert recovery.pending() is None
