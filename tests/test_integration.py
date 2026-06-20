"""End-to-end integration tests exercising the full bookmark pipeline.

Each test flows through multiple subsystems (import -> categorize -> search,
add -> tag -> export, etc.) to catch regressions that unit tests miss.

Uses the CLI entry point so module-level constants resolve correctly
regardless of test ordering.
"""

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path


class _IntegrationBase(unittest.TestCase):
    """Isolated data directory for integration tests."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="bop_integ_")
        os.environ["BOOKMARK_DATA_DIR"] = cls._tmp
        import bookmark_organizer_pro.constants as _c
        importlib.reload(_c)
        _c.ensure_directories()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("BOOKMARK_DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _run_cli(self, args):
        from bookmark_organizer_pro.cli import BookmarkCLI
        cli = BookmarkCLI()
        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            cli.run(args)
        except SystemExit:
            pass
        finally:
            sys.stdout = old_stdout
        return captured.getvalue(), cli

    def _managers(self):
        from bookmark_organizer_pro.cli import BookmarkCLI
        cli = BookmarkCLI()
        return cli.bookmark_manager, cli.category_manager, cli.tag_manager


class TestImportAndSearch(_IntegrationBase):
    """Import HTML bookmarks -> keyword search -> verify results."""

    def test_html_import_then_search(self):
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="https://docs.python.org/3/library/argparse.html">argparse docs</A>
<DT><A HREF="https://github.com/python/cpython">CPython on GitHub</A>
<DT><A HREF="https://stackoverflow.com/questions/tagged/python">Python Q&amp;A</A>
</DL>"""
        html_path = Path(self._tmp) / "import_test.html"
        html_path.write_text(html, encoding="utf-8")

        out, _ = self._run_cli(["import", str(html_path)])
        self.assertIn("3", out)

        out, _ = self._run_cli(["search", "argparse"])
        self.assertIn("argparse", out.lower())

    def test_duplicate_import_skips(self):
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="https://integ-dup.example.com">Dup Test</A>
</DL>"""
        html_path = Path(self._tmp) / "dup_test.html"
        html_path.write_text(html, encoding="utf-8")

        out1, _ = self._run_cli(["import", str(html_path)])
        self.assertIn("1", out1)

        out2, _ = self._run_cli(["import", str(html_path)])
        self.assertIn("0", out2)
        self.assertIn("1", out2)


class TestAddAndExport(_IntegrationBase):
    """Add bookmark -> tag it -> export JSON -> verify in output."""

    def test_add_tag_and_export_json(self):
        out, cli = self._run_cli(["add", "https://integ-export.example.com", "Integration", "Export"])
        self.assertIn("Added", out)

        export_path = Path(self._tmp) / "exported.json"
        out, _ = self._run_cli(["export", str(export_path)])
        self.assertTrue(export_path.exists())

        data = json.loads(export_path.read_text(encoding="utf-8"))
        bookmarks = data.get("bookmarks", []) if isinstance(data, dict) else data
        urls = [b["url"] for b in bookmarks if isinstance(b, dict)]
        self.assertIn("https://integ-export.example.com", urls)


class TestContentSearch(_IntegrationBase):
    """Add bookmark with extracted text -> search with content: filter."""

    def test_content_filter_finds_extracted_text(self):
        _, cli = self._run_cli(["add", "https://content-integ.example.com", "Content", "Test"])
        bm_mgr = cli.bookmark_manager
        bm = [b for b in bm_mgr.get_all_bookmarks()
              if b.url == "https://content-integ.example.com"]
        self.assertTrue(bm)
        bm = bm[0]

        from bookmark_organizer_pro.constants import EXTRACTED_DIR
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        text_path = EXTRACTED_DIR / f"{bm.id}.txt"
        text_path.write_text(
            "This article discusses quantum entanglement in detail.",
            encoding="utf-8",
        )

        from bookmark_organizer_pro.search import SearchEngine, _load_extracted_text
        _load_extracted_text.cache_clear()
        engine = SearchEngine()
        all_bms = bm_mgr.get_all_bookmarks()

        results = engine.search(all_bms, "content:entanglement")
        found_ids = [b.id for b, _ in results]
        self.assertIn(bm.id, found_ids)

        _load_extracted_text.cache_clear()
        results_miss = engine.search(all_bms, "content:blockchain")
        found_ids_miss = [b.id for b, _ in results_miss]
        self.assertNotIn(bm.id, found_ids_miss)


class TestStatsAndDigest(_IntegrationBase):
    """Add bookmarks -> stats -> digest pipeline."""

    def test_stats_counts_bookmarks(self):
        self._run_cli(["add", "https://stats-test-1.example.com", "Stats1"])
        self._run_cli(["add", "https://stats-test-2.example.com", "Stats2"])

        out, _ = self._run_cli(["stats"])
        self.assertIn("bookmark", out.lower())

    def test_digest_runs(self):
        out, _ = self._run_cli(["digest"])
        self.assertIsInstance(out, str)


class TestAISnapshot(_IntegrationBase):
    """AI operation snapshots for undo/rollback."""

    def test_create_and_restore_snapshot(self):
        from bookmark_organizer_pro.services.ai_snapshot import (
            AI_SNAPSHOTS_DIR,
            create_snapshot,
            delete_snapshot,
            list_snapshots,
            restore_snapshot,
        )

        AI_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

        _, cli = self._run_cli(["add", "https://snap-test.example.com", "Snap", "Test"])
        bm_mgr = cli.bookmark_manager
        bms = [b for b in bm_mgr.get_all_bookmarks() if b.url == "https://snap-test.example.com"]
        self.assertTrue(bms)
        bm = bms[0]
        self.assertEqual(bm.category, "Uncategorized / Needs Review")

        snap_id = create_snapshot("test_op", [bm])

        bm.category = "AI Changed"
        bm.tags = ["ai-generated"]
        bm_mgr.save_bookmarks()

        snapshots = list_snapshots()
        self.assertTrue(any(s["snapshot_id"] == snap_id for s in snapshots))

        count = restore_snapshot(snap_id, bm_mgr)
        self.assertEqual(count, 1)
        restored = bm_mgr.get_bookmark(bm.id)
        self.assertEqual(restored.category, "Uncategorized / Needs Review")
        self.assertEqual(restored.tags, [])

        delete_snapshot(snap_id)
        self.assertFalse(any(s["snapshot_id"] == snap_id for s in list_snapshots()))


class TestTagHierarchy(_IntegrationBase):
    """Tag hierarchy: slash-separated tags create parent/child relationships."""

    def test_slash_tag_creates_hierarchy(self):
        from bookmark_organizer_pro.managers.tags import TagManager
        tm = TagManager(filepath=Path(self._tmp) / "tags.json")

        tag = tm.add_tag("programming/python")
        self.assertIsNotNone(tag)
        self.assertEqual(tag.name, "python")
        self.assertEqual(tag.parent, "programming")
        self.assertEqual(tag.full_path, "programming/python")

        parent = tm.get_tag("programming")
        self.assertIsNotNone(parent)
        self.assertEqual(parent.parent, "")

    def test_get_children_returns_child_tags(self):
        from bookmark_organizer_pro.managers.tags import TagManager
        tm = TagManager(filepath=Path(self._tmp) / "tags.json")

        tm.add_tag("dev/python")
        tm.add_tag("dev/rust")
        tm.add_tag("music")

        children = tm.get_child_tags("dev")
        child_names = {c.name for c in children}
        self.assertEqual(child_names, {"python", "rust"})

    def test_tag_filter_matches_children(self):
        from bookmark_organizer_pro.search import SearchEngine
        from bookmark_organizer_pro.models import Bookmark

        bm1 = Bookmark(id=1, url="https://a.example.com", title="A", tags=["dev/python"])
        bm2 = Bookmark(id=2, url="https://b.example.com", title="B", tags=["dev/rust"])
        bm3 = Bookmark(id=3, url="https://c.example.com", title="C", tags=["music"])

        engine = SearchEngine()
        results = engine.search([bm1, bm2, bm3], "tag:dev")
        found_ids = {b.id for b, _ in results}
        self.assertIn(1, found_ids)
        self.assertIn(2, found_ids)
        self.assertNotIn(3, found_ids)

    def test_flat_tags_preserved(self):
        from bookmark_organizer_pro.managers.tags import TagManager
        tm = TagManager(filepath=Path(self._tmp) / "tags.json")

        tag = tm.add_tag("simple-tag")
        self.assertIsNotNone(tag)
        self.assertEqual(tag.name, "simple-tag")
        self.assertEqual(tag.parent, "")
        self.assertEqual(tag.full_path, "simple-tag")


if __name__ == "__main__":
    unittest.main()
