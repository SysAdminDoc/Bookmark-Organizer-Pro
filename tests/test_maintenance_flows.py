"""Tests for non-blocking maintenance and reversible cleanup flows."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from bookmark_organizer_pro.app_mixins.bookmarks import BookmarkViewMixin
from bookmark_organizer_pro.app_mixins.tools import ToolsActionsMixin
from bookmark_organizer_pro.models.bookmark import Bookmark
from bookmark_organizer_pro.models.category import Category
from bookmark_organizer_pro.ui.cleanup_review import CleanupApplyResult, CleanupReviewDialog
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
        self.review_dialogs = []

    def _set_status(self, message):
        self.statuses.append(message)

    def _show_toast(self, message, style="info"):
        self.toasts.append((style, message))

    def _refresh_all(self):
        self.refresh_count += 1

    def _show_cleanup_review_dialog(self, title, intro, groups, on_apply):
        self.review_dialogs.append({
            "title": title,
            "intro": intro,
            "groups": list(groups),
            "on_apply": on_apply,
        })


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

        safepoint = app._last_maintenance_safepoint
        self.assertTrue(app._restore_last_maintenance_safepoint())
        self.assertEqual([safepoint], app.bookmark_manager.restored_backups)
        self.assertEqual("", app._last_maintenance_safepoint)
        self.assertEqual(2, app.refresh_count)

    def test_first_maintenance_safepoint_is_stable_until_restore_or_new_workflow(self):
        app = MaintenanceHarness([bookmark(1, "https://example.com")])
        app._begin_maintenance_workflow()

        first = app._create_maintenance_safepoint("first")
        repeated = app._create_maintenance_safepoint("second")

        self.assertEqual(first, repeated)
        self.assertEqual(["first"], app.bookmark_manager.created_safepoints)
        self.assertTrue(app._restore_last_maintenance_safepoint())

        app._begin_maintenance_workflow()
        second = app._create_maintenance_safepoint("second")
        self.assertNotEqual(first, second)
        self.assertEqual(["first", "second"], app.bookmark_manager.created_safepoints)

    def test_cleanup_apply_disables_before_callback_and_is_single_use(self):
        class Value:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Button:
            def __init__(self):
                self.state = "normal"

            def set_state(self, state):
                self.state = state

        class Status:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        dialog = CleanupReviewDialog.__new__(CleanupReviewDialog)
        dialog._vars = {"one": Value(True)}
        dialog.apply_button = Button()
        dialog.skip_button = Button()
        dialog._status_var = Status()
        dialog._apply_in_progress = False
        dialog._applied = False
        calls = []

        def apply(selected):
            calls.append((selected, dialog.apply_button.state))
            dialog._apply_selected()
            return "Applied once."

        dialog._on_apply = apply
        dialog._apply_selected()
        dialog._apply_selected()

        self.assertEqual([(["one"], "disabled")], calls)
        self.assertTrue(dialog._applied)
        self.assertFalse(dialog._vars["one"].get())
        self.assertEqual("disabled", dialog.apply_button.state)
        self.assertEqual("Applied once.", dialog._status_var.value)

    def test_cleanup_apply_reenables_only_for_explicit_safe_retry(self):
        class Value:
            def __init__(self):
                self.value = True

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Control:
            def __init__(self):
                self.value = ""

            def set_state(self, value):
                self.value = value

            def set(self, value):
                self.value = value

        dialog = CleanupReviewDialog.__new__(CleanupReviewDialog)
        dialog._vars = {"one": Value()}
        dialog.apply_button = Control()
        dialog.skip_button = Control()
        dialog._status_var = Control()
        dialog._apply_in_progress = False
        dialog._applied = False
        dialog._on_apply = lambda _selected: CleanupApplyResult("Safepoint unavailable.", retryable=True)

        dialog._apply_selected()

        self.assertFalse(dialog._applied)
        self.assertTrue(dialog._vars["one"].get())
        self.assertEqual("normal", dialog.apply_button.value)

        dialog._on_apply = lambda _selected: (_ for _ in ()).throw(OSError("write failed"))
        dialog._apply_selected()
        dialog._apply_selected()
        self.assertTrue(dialog._applied)
        self.assertEqual("disabled", dialog.apply_button.value)
        self.assertIn("Reopen this workflow", dialog._status_var.value)

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

    def test_find_duplicates_opens_review_then_removes_selected_extras(self):
        first = bookmark(1, "https://example.com")
        duplicate = bookmark(2, "https://example.com")
        app = MaintenanceHarness([first, duplicate])
        app.bookmark_manager.duplicates = {"https://example.com": [first, duplicate]}

        with patch("bookmark_organizer_pro.app_mixins.tools.messagebox.askyesno") as ask:
            app._find_duplicates()

        ask.assert_not_called()
        self.assertEqual(1, len(app.review_dialogs))
        self.assertEqual("Duplicate Review", app.review_dialogs[0]["title"])
        self.assertEqual([1, 2], [bm.id for bm in app.bookmark_manager.bookmarks])
        self.assertEqual([], app.bookmark_manager.created_safepoints)

        group_key = app.review_dialogs[0]["groups"][0].key
        result = app.review_dialogs[0]["on_apply"]([group_key])

        self.assertIn("Removed 1 duplicate", result)
        self.assertEqual(["remove-duplicates"], app.bookmark_manager.created_safepoints)
        self.assertEqual([1], [bm.id for bm in app.bookmark_manager.bookmarks])
        self.assertEqual(1, app.bookmark_manager.save_count)
        self.assertEqual(1, app.refresh_count)

    def test_smart_duplicate_review_applies_selected_groups(self):
        from bookmark_organizer_pro.services.dup_hybrid import DuplicateGroup, DuplicateReport

        first = bookmark(1, "https://example.com/a")
        duplicate = bookmark(2, "https://mirror.example/a")
        app = MaintenanceHarness([first, duplicate])
        report = DuplicateReport(groups=[
            DuplicateGroup(method="simhash", canonical_id=1, bookmark_ids=[1, 2], confidence=0.85)
        ])

        app._show_dup_results(report)

        self.assertEqual(1, len(app.review_dialogs))
        self.assertEqual("Smart Duplicate Review", app.review_dialogs[0]["title"])
        group_key = app.review_dialogs[0]["groups"][0].key
        result = app.review_dialogs[0]["on_apply"]([group_key])

        self.assertIn("Removed 1 duplicate", result)
        self.assertEqual(["smart-duplicates"], app.bookmark_manager.created_safepoints)
        self.assertEqual([1], [bm.id for bm in app.bookmark_manager.bookmarks])
        self.assertEqual(1, app.bookmark_manager.save_count)
        self.assertEqual(1, app.refresh_count)

    def test_tag_lint_review_applies_selected_merges(self):
        from bookmark_organizer_pro.services.tag_linter import TagLinter

        first = bookmark(1, "https://example.com/a", tags=["Python"])
        second = bookmark(2, "https://example.com/b", tags=["python"])
        app = MaintenanceHarness([first, second])
        report = TagLinter().lint(app.bookmark_manager.get_all_bookmarks())

        app._show_lint_results(report)

        self.assertEqual(1, len(app.review_dialogs))
        self.assertEqual("Tag Cleanup Review", app.review_dialogs[0]["title"])
        group_key = app.review_dialogs[0]["groups"][0].key
        result = app.review_dialogs[0]["on_apply"]([group_key])

        self.assertIn("Applied 1 tag merge", result)
        self.assertEqual(["lint-tags"], app.bookmark_manager.created_safepoints)
        self.assertEqual([["Python"], ["Python"]], [bm.tags for bm in app.bookmark_manager.bookmarks])
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


class TestDuplicateScanCoverage(unittest.TestCase):
    """The pairwise passes are capped, so a report must say what it did not compare."""

    def _detector(self, max_pairwise):
        from bookmark_organizer_pro.services.dup_hybrid import HybridDuplicateDetector

        return HybridDuplicateDetector(max_pairwise=max_pairwise)

    def _distinct_library(self, count):
        return [bookmark(index, f"https://example-{index}.test/page-{index}") for index in range(1, count + 1)]

    def test_report_flags_the_records_the_cap_left_uncompared(self):
        library = self._distinct_library(10)

        report = self._detector(4).detect(library)

        self.assertTrue(report.truncated)
        self.assertEqual(10, report.library_size)
        self.assertEqual(4, report.pairwise_examined)
        self.assertEqual(6, report.pairwise_skipped)
        self.assertIn("Compared 4 of 10 bookmarks", report.coverage_summary())

    def test_the_same_library_reports_full_coverage_under_a_cap_that_fits(self):
        library = self._distinct_library(10)

        report = self._detector(10).detect(library)

        self.assertFalse(report.truncated)
        self.assertEqual(10, report.pairwise_examined)
        self.assertEqual(0, report.pairwise_skipped)
        self.assertEqual("Compared all 10 bookmarks.", report.coverage_summary())

    def test_url_duplicates_are_never_capped(self):
        library = self._distinct_library(8)
        library.append(bookmark(99, "https://example-1.test/page-1"))

        report = self._detector(1).detect(library)

        self.assertEqual(1, report.method_counts["url"])
        self.assertTrue(report.truncated)

    def test_empty_result_on_a_truncated_scan_does_not_claim_the_library_is_clean(self):
        from bookmark_organizer_pro.services.dup_hybrid import DuplicateReport

        report = DuplicateReport(
            method_counts={"url": 0, "simhash": 0, "embedding": 0},
            library_size=9,
            pairwise_examined=3,
            pairwise_skipped=6,
        )
        app = MaintenanceHarness([])

        app._show_dup_results(report)

        self.assertEqual(1, len(app.toasts))
        self.assertIn("were compared", app.toasts[0][1])
        self.assertIn("6 were not compared", app.statuses[-1])

    def test_empty_result_on_a_complete_scan_still_reads_as_clean(self):
        from bookmark_organizer_pro.services.dup_hybrid import DuplicateReport

        report = DuplicateReport(
            method_counts={"url": 0, "simhash": 0, "embedding": 0},
            library_size=9,
            pairwise_examined=9,
            pairwise_skipped=0,
        )
        app = MaintenanceHarness([])

        app._show_dup_results(report)

        self.assertEqual([("success", "No duplicates found")], app.toasts)
        self.assertIn("Compared all 9 bookmarks", app.statuses[-1])


class CountingBookmarkManager:
    """Counts full-library snapshots so a refresh cannot quietly take four."""

    def __init__(self, bookmarks):
        self._bookmarks = list(bookmarks)
        self.snapshot_calls = 0
        self.category_calls = 0

    def get_all_bookmarks(self):
        self.snapshot_calls += 1
        return list(self._bookmarks)

    def get_bookmarks_by_category(self, category, include_children=True):
        self.category_calls += 1
        return [
            bm for bm in self._bookmarks
            if bm.category == category
            or (include_children and bm.parent_category == category)
        ]


class RefreshHarness(BookmarkViewMixin):
    """Minimal stand-in for the app shell around the bookmark table."""

    def __init__(self, bookmarks):
        self.bookmark_manager = CountingBookmarkManager(bookmarks)
        self.tree = object()
        self.count_label = None
        self.current_category = ""
        self.search_query = ""
        self.quick_filter = None
        self.filter_button_parts = None
        self.populated = None
        self.collection_summaries = []

    def _refresh_filter_counts(self, library=None):
        self.filter_count_library = library

    def _set_collection_summary_visible(self, visible):
        pass

    def _set_content_header_visible(self, visible):
        pass

    def _refresh_collection_summary(self, **kwargs):
        self.collection_summaries.append(kwargs)

    def _populate_list_view(self, bookmarks):
        self.populated = list(bookmarks)


class TestBookmarkTableRefresh(unittest.TestCase):
    def _library(self):
        first = bookmark(1, "https://example.com/b", category="Dev")
        first.title = "beta"
        second = bookmark(2, "https://example.com/a", category="Dev")
        second.title = "Alpha"
        third = bookmark(3, "https://example.com/c", category="Ops")
        third.title = "charlie"
        third.is_pinned = True
        return [first, second, third]

    def test_a_refresh_takes_exactly_one_library_snapshot(self):
        app = RefreshHarness(self._library())

        app._refresh_bookmark_list()

        self.assertEqual(1, app.bookmark_manager.snapshot_calls)
        self.assertEqual(0, app.bookmark_manager.category_calls)

    def test_a_category_refresh_still_takes_exactly_one_snapshot(self):
        app = RefreshHarness(self._library())
        app.current_category = "Dev"

        app._refresh_bookmark_list()

        self.assertEqual(1, app.bookmark_manager.snapshot_calls)
        self.assertEqual(0, app.bookmark_manager.category_calls)
        self.assertEqual({"Alpha", "beta"}, {bm.title for bm in app.populated})

    def test_the_category_filter_matches_the_manager_it_replaced(self):
        library = self._library()
        library[0].parent_category = "Ops"
        app = RefreshHarness(library)
        app.current_category = "Ops"

        app._refresh_bookmark_list()

        expected = app.bookmark_manager.get_bookmarks_by_category("Ops")
        self.assertEqual({bm.id for bm in expected}, {bm.id for bm in app.populated})

    def test_filter_counts_reuse_the_snapshot_the_refresh_already_took(self):
        app = RefreshHarness(self._library())

        app._refresh_bookmark_list()

        self.assertEqual(3, len(app.filter_count_library))
        self.assertEqual(1, app.bookmark_manager.snapshot_calls)

    def test_pinned_first_then_case_insensitive_title_order_is_unchanged(self):
        app = RefreshHarness(self._library())

        app._refresh_bookmark_list()

        self.assertEqual(["charlie", "Alpha", "beta"], [bm.title for bm in app.populated])

    def test_the_sort_key_is_computed_once_per_record(self):
        library = self._library()
        lowered = []

        class CountingTitle(str):
            def lower(self):
                lowered.append(str(self))
                return str.lower(self)

        for bm in library:
            bm.title = CountingTitle(bm.title)
        app = RefreshHarness(library)

        app._refresh_bookmark_list()

        self.assertEqual(sorted(lowered), sorted(str(bm.title) for bm in library))


class TestDuplicateScanCoverageAccounting(unittest.TestCase):
    """A later pass must not launder records the earlier pass never compared."""

    class _Embedder:
        available = True

        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    def test_a_pass_that_skipped_records_is_not_cancelled_out_by_a_later_pass(self):
        from bookmark_organizer_pro.services.dup_hybrid import HybridDuplicateDetector

        # Five near-identical records group in the simhash pass, so the cap
        # excludes the tail from it. The embedding pass then sees a small
        # enough candidate set to run inside the same cap.
        library = [bookmark(index, f"https://same.example/{index}") for index in range(1, 6)]
        for bm in library:
            bm.title = "identical benchmark title"
        library += [
            bookmark(index, f"https://tail-{index}.example/page")
            for index in range(6, 11)
        ]

        report = HybridDuplicateDetector(self._Embedder(), max_pairwise=5).detect(library)

        self.assertTrue(
            report.truncated,
            "the simhash pass skipped records, so the report cannot claim full coverage",
        )
        self.assertGreater(report.pairwise_skipped, 0)
        self.assertNotIn("Compared all", report.coverage_summary())

    def test_an_uncapped_scan_with_both_passes_still_reports_full_coverage(self):
        from bookmark_organizer_pro.services.dup_hybrid import HybridDuplicateDetector

        library = [bookmark(index, f"https://uncapped-{index}.example/page") for index in range(1, 8)]

        report = HybridDuplicateDetector(self._Embedder(), max_pairwise=100).detect(library)

        self.assertFalse(report.truncated)
        self.assertEqual(0, report.pairwise_skipped)
        self.assertEqual("Compared all 7 bookmarks.", report.coverage_summary())
