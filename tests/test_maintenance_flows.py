"""Tests for non-blocking maintenance and reversible cleanup flows."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from bookmark_organizer_pro.app_mixins.tools import ToolsActionsMixin
from bookmark_organizer_pro.models.bookmark import Bookmark
from bookmark_organizer_pro.models.category import Category
from bookmark_organizer_pro.ui.management_dialogs import CategoryManagementDialog


class FakeBookmarkManager:
    def __init__(self, bookmarks):
        self.bookmarks = list(bookmarks)
        self.created_safepoints = []
        self.restored_backups = []
        self.save_count = 0
        self.safepoint_response = None
        self.duplicates = {}

    def create_safepoint(self, label):
        self.created_safepoints.append(label)
        if self.safepoint_response is not None:
            return self.safepoint_response
        return f"safepoints/safepoint_{label}.json"

    def restore_backup(self, name):
        self.restored_backups.append(name)
        return True

    def get_all_bookmarks(self):
        return list(self.bookmarks)

    def get_bookmark(self, bookmark_id):
        return next((bm for bm in self.bookmarks if bm.id == bookmark_id), None)

    def get_bookmarks_by_category(self, category):
        return [bm for bm in self.bookmarks if bm.category == category]

    def update_bookmark(self, bookmark):
        return bookmark

    def save_bookmarks(self):
        self.save_count += 1

    def find_duplicates(self):
        return self.duplicates

    def delete_bookmark(self, bookmark_id):
        before = len(self.bookmarks)
        self.bookmarks = [bm for bm in self.bookmarks if bm.id != bookmark_id]
        return len(self.bookmarks) != before


class FakeCategoryManager:
    def __init__(self):
        self.categories = {
            "Dev": Category("Dev", patterns=["github.com"], icon="D"),
            "Uncategorized / Needs Review": Category("Uncategorized / Needs Review", icon="?"),
        }
        self.save_count = 0

    def save_categories(self):
        self.save_count += 1


class MaintenanceHarness(ToolsActionsMixin):
    def __init__(self, bookmarks):
        self.bookmark_manager = FakeBookmarkManager(bookmarks)
        self.category_manager = FakeCategoryManager()
        self.selected_bookmarks = set()
        self.statuses = []
        self.toasts = []
        self.refresh_count = 0
        self.root = object()

    def _set_status(self, message):
        self.statuses.append(message)

    def _show_toast(self, message, style="info"):
        self.toasts.append((style, message))

    def _refresh_all(self):
        self.refresh_count += 1


def bookmark(bookmark_id, url, category="Dev", tags=None, ai_tags=None):
    return Bookmark(
        id=bookmark_id,
        url=url,
        title=f"Bookmark {bookmark_id}",
        category=category,
        tags=tags or [],
        ai_tags=ai_tags or [],
    )


class TestMaintenanceFlows(unittest.TestCase):
    def test_flatten_all_folders_creates_safepoint_without_confirmation(self):
        app = MaintenanceHarness([
            bookmark(1, "https://example.com", category="Dev"),
            bookmark(2, "https://review.example", category="Uncategorized / Needs Review"),
        ])

        with patch("bookmark_organizer_pro.app_mixins.tools.messagebox.askyesno") as ask:
            app._flatten_all_folders()

        ask.assert_not_called()
        self.assertEqual(["flatten-folders"], app.bookmark_manager.created_safepoints)
        self.assertEqual("Uncategorized / Needs Review", app.bookmark_manager.get_bookmark(1).category)
        self.assertEqual(1, app.bookmark_manager.save_count)
        self.assertEqual(1, app.refresh_count)
        self.assertTrue(app._last_maintenance_safepoint.endswith("flatten-folders.json"))

        self.assertTrue(app._restore_last_maintenance_safepoint())
        self.assertEqual([app._last_maintenance_safepoint], app.bookmark_manager.restored_backups)
        self.assertEqual(2, app.refresh_count)

    def test_clear_all_tags_aborts_when_safepoint_is_unavailable(self):
        app = MaintenanceHarness([
            bookmark(1, "https://example.com", tags=["python"], ai_tags=["docs"]),
        ])
        app.bookmark_manager.safepoint_response = ""

        app._clear_all_tags()

        bm = app.bookmark_manager.get_bookmark(1)
        self.assertEqual(["python"], bm.tags)
        self.assertEqual(["docs"], bm.ai_tags)
        self.assertEqual(0, app.bookmark_manager.save_count)
        self.assertEqual(0, app.refresh_count)

    def test_find_duplicates_removes_extras_without_confirmation(self):
        first = bookmark(1, "https://example.com")
        duplicate = bookmark(2, "https://example.com")
        app = MaintenanceHarness([first, duplicate])
        app.bookmark_manager.duplicates = {"https://example.com": [first, duplicate]}

        with patch("bookmark_organizer_pro.app_mixins.tools.messagebox.askyesno") as ask:
            app._find_duplicates()

        ask.assert_not_called()
        self.assertEqual(["remove-duplicates"], app.bookmark_manager.created_safepoints)
        self.assertEqual([1], [bm.id for bm in app.bookmark_manager.bookmarks])
        self.assertEqual(1, app.bookmark_manager.save_count)
        self.assertEqual(1, app.refresh_count)

    def test_category_delete_has_inline_restore_without_confirmation(self):
        manager = FakeBookmarkManager([
            bookmark(1, "https://example.com", category="Dev"),
            bookmark(2, "https://other.example", category="Dev"),
        ])
        categories = FakeCategoryManager()
        dialog = CategoryManagementDialog.__new__(CategoryManagementDialog)
        dialog.bookmark_manager = manager
        dialog.category_manager = categories
        dialog.on_change = lambda: None
        dialog._last_deleted_category = None
        statuses = []
        dialog._set_status = statuses.append
        dialog._populate_categories = lambda: None

        with patch("bookmark_organizer_pro.ui.management_dialogs.messagebox.askyesno") as ask:
            dialog._delete_category("Dev")

        ask.assert_not_called()
        self.assertNotIn("Dev", categories.categories)
        self.assertEqual(
            ["Uncategorized / Needs Review", "Uncategorized / Needs Review"],
            [bm.category for bm in manager.bookmarks],
        )
        self.assertIn("Restore Last Delete", statuses[-1])

        self.assertTrue(dialog._restore_last_deleted_category())
        self.assertIn("Dev", categories.categories)
        self.assertEqual(["Dev", "Dev"], [bm.category for bm in manager.bookmarks])
        self.assertIn("Restored", statuses[-1])


if __name__ == "__main__":
    unittest.main()
