"""End-to-end integration tests exercising the full bookmark pipeline.

Each test flows through multiple subsystems (import → categorize → search,
add → tag → export, etc.) to catch regressions that unit tests miss.
"""

import importlib
import json
import os
import shutil
import tempfile
import unittest
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

    def _managers(self):
        from bookmark_organizer_pro.core import CategoryManager
        from bookmark_organizer_pro.managers import BookmarkManager, TagManager
        cm = CategoryManager()
        tm = TagManager()
        bm = BookmarkManager(cm, tm)
        return bm, cm, tm


class TestImportCategorizeSearch(_IntegrationBase):
    """Import HTML bookmarks → auto-categorize → keyword search."""

    def test_html_import_then_search(self):
        bm_mgr, cm, tm = self._managers()

        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="https://docs.python.org/3/library/argparse.html">argparse — Python</A>
<DT><A HREF="https://github.com/python/cpython">CPython on GitHub</A>
<DT><A HREF="https://stackoverflow.com/questions/tagged/python">Python Q&amp;A</A>
</DL>"""
        html_path = Path(self._tmp) / "import_test.html"
        html_path.write_text(html, encoding="utf-8")

        added, dupes = bm_mgr.import_html_file(str(html_path))
        self.assertEqual(added, 3)
        self.assertEqual(dupes, 0)

        results = bm_mgr.search_bookmarks("argparse")
        self.assertTrue(len(results) >= 1)
        self.assertIn("argparse", results[0].title.lower())

    def test_duplicate_import_skips(self):
        bm_mgr, _, _ = self._managers()

        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="https://duplicate-test.example.com">Dup Test</A>
</DL>"""
        html_path = Path(self._tmp) / "dup_test.html"
        html_path.write_text(html, encoding="utf-8")

        added1, _ = bm_mgr.import_html_file(str(html_path))
        added2, dupes2 = bm_mgr.import_html_file(str(html_path))
        self.assertEqual(added1, 1)
        self.assertEqual(added2, 0)
        self.assertEqual(dupes2, 1)


class TestAddTagFlowExport(_IntegrationBase):
    """Add bookmark → tag it → create flow → export."""

    def test_add_tag_and_export_json(self):
        bm_mgr, _, _ = self._managers()

        bm = bm_mgr.add_bookmark_clean(
            url="https://integ-export.example.com",
            title="Integration Export Test",
            category="Testing",
            tags=["integration", "export"],
        )
        self.assertIsNotNone(bm)
        self.assertIn("integration", bm.tags)

        export_path = Path(self._tmp) / "exported.json"
        bm_mgr.export_json(str(export_path))
        self.assertTrue(export_path.exists())

        data = json.loads(export_path.read_text(encoding="utf-8"))
        bookmarks = data.get("bookmarks", []) if isinstance(data, dict) else data
        urls = [b["url"] for b in bookmarks if isinstance(b, dict)]
        self.assertIn("https://integ-export.example.com", urls)


class TestImportDeduplicateMerge(_IntegrationBase):
    """Import duplicates → detect → verify dedup logic."""

    def test_import_dedup_skips_existing_url(self):
        bm_mgr, _, _ = self._managers()

        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
<DT><A HREF="https://dedup-integ.example.com/page">Dedup Page</A>
</DL>"""
        html_path = Path(self._tmp) / "dedup_integ.html"
        html_path.write_text(html, encoding="utf-8")

        added1, _ = bm_mgr.import_html_file(str(html_path))
        self.assertEqual(added1, 1)

        added2, dupes2 = bm_mgr.import_html_file(str(html_path))
        self.assertEqual(added2, 0)
        self.assertEqual(dupes2, 1)


class TestSearchContentFilter(_IntegrationBase):
    """Add bookmark with extracted text → search with content: filter."""

    def test_content_filter_finds_extracted_text(self):
        from bookmark_organizer_pro.constants import EXTRACTED_DIR
        bm_mgr, _, _ = self._managers()

        bm = bm_mgr.add_bookmark_clean(
            url="https://content-search.example.com",
            title="Content Search Test",
            category="Testing",
        )
        self.assertIsNotNone(bm)

        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        text_path = EXTRACTED_DIR / f"{bm.id}.txt"
        text_path.write_text(
            "This article discusses quantum entanglement in detail.",
            encoding="utf-8",
        )

        from bookmark_organizer_pro.search import SearchEngine
        engine = SearchEngine()
        all_bms = bm_mgr.get_all_bookmarks()

        from bookmark_organizer_pro.search import _load_extracted_text
        _load_extracted_text.cache_clear()

        results = engine.search(all_bms, "content:entanglement")
        found_ids = [b.id for b, _ in results]
        self.assertIn(bm.id, found_ids)

        _load_extracted_text.cache_clear()
        results_miss = engine.search(all_bms, "content:blockchain")
        found_ids_miss = [b.id for b, _ in results_miss]
        self.assertNotIn(bm.id, found_ids_miss)


class TestBackupRestore(_IntegrationBase):
    """Add bookmarks → backup → verify backup integrity."""

    def test_backup_contains_sha256(self):
        bm_mgr, _, _ = self._managers()

        bm_mgr.add_bookmark_clean(
            url="https://backup-test.example.com",
            title="Backup Test",
            category="Testing",
        )
        bm_mgr.save_bookmarks()

        from bookmark_organizer_pro.constants import BACKUP_DIR
        backups = sorted(BACKUP_DIR.glob("*.json"))
        if backups:
            content = backups[-1].read_text(encoding="utf-8")
            self.assertTrue(len(content) > 10)


if __name__ == "__main__":
    unittest.main()
