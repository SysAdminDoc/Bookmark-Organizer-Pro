"""Unit tests for Smart Collections, EPUB Export, and Obsidian Export services.

Covers SmartCollection filter matching (tags, categories, domains, keywords,
dates), serialization roundtrips, SmartCollectionManager CRUD, EPUB structural
validity, HTML escaping, Obsidian filename safety, YAML escaping, frontmatter
correctness, YAML injection, collection filtering, and duplicate-title handling.
"""

import importlib
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


def _make_bookmark(**overrides):
    """Helper -- create a Bookmark with sensible defaults."""
    from bookmark_organizer_pro.models import Bookmark

    defaults = dict(
        id=None,
        url="https://example.com",
        title="Example",
    )
    defaults.update(overrides)
    return Bookmark(**defaults)


class _IsolatedTestBase(unittest.TestCase):
    """Redirect BOOKMARK_DATA_DIR to a temp dir, reload constants."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="bop_v62_test_")
        os.environ["BOOKMARK_DATA_DIR"] = cls._tmp

        import bookmark_organizer_pro.constants as _c
        importlib.reload(_c)
        _c.ensure_directories()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("BOOKMARK_DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)


# ===================================================================
# 1. Smart Collections
# ===================================================================

class TestSmartCollectionMatchesTags(_IsolatedTestBase):
    """SmartCollection.matches() — tag filter."""

    def _sc(self, **filter_kw):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollection, SmartCollectionFilter,
        )
        return SmartCollection(
            id="test", name="Test",
            filters=SmartCollectionFilter(**filter_kw),
        )

    def test_tag_match(self):
        sc = self._sc(tags=["python"])
        bm = _make_bookmark(tags=["Python", "tutorial"])
        self.assertTrue(sc.matches(bm))

    def test_tag_no_match(self):
        sc = self._sc(tags=["rust"])
        bm = _make_bookmark(tags=["python", "tutorial"])
        self.assertFalse(sc.matches(bm))


class TestSmartCollectionMatchesCategory(_IsolatedTestBase):
    """SmartCollection.matches() — category filter (regression: 'AI' must not match 'Email')."""

    def _sc(self, **filter_kw):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollection, SmartCollectionFilter,
        )
        return SmartCollection(
            id="test", name="Test",
            filters=SmartCollectionFilter(**filter_kw),
        )

    def test_category_exact_match(self):
        sc = self._sc(categories=["Development"])
        bm = _make_bookmark(category="Development")
        self.assertTrue(sc.matches(bm))

    def test_category_ai_does_not_match_email(self):
        """Regression: substring 'ai' inside 'Email' must NOT match category 'AI'."""
        sc = self._sc(categories=["AI"])
        bm = _make_bookmark(category="Email")
        self.assertFalse(sc.matches(bm))


class TestSmartCollectionMatchesDomain(_IsolatedTestBase):
    """SmartCollection.matches() — domain filter (case-insensitive)."""

    def _sc(self, **filter_kw):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollection, SmartCollectionFilter,
        )
        return SmartCollection(
            id="test", name="Test",
            filters=SmartCollectionFilter(**filter_kw),
        )

    def test_domain_case_insensitive(self):
        sc = self._sc(domains=["GitHub.com"])
        bm = _make_bookmark(url="https://GITHUB.COM/user/repo")
        self.assertTrue(sc.matches(bm))

    def test_domain_no_match(self):
        sc = self._sc(domains=["gitlab.com"])
        bm = _make_bookmark(url="https://github.com/user/repo")
        self.assertFalse(sc.matches(bm))


class TestSmartCollectionMatchesKeyword(_IsolatedTestBase):
    """SmartCollection.matches() — keyword filter."""

    def _sc(self, **filter_kw):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollection, SmartCollectionFilter,
        )
        return SmartCollection(
            id="test", name="Test",
            filters=SmartCollectionFilter(**filter_kw),
        )

    def test_keyword_in_title(self):
        sc = self._sc(keywords=["machine learning"])
        bm = _make_bookmark(title="Intro to Machine Learning")
        self.assertTrue(sc.matches(bm))

    def test_keyword_no_match(self):
        sc = self._sc(keywords=["quantum"])
        bm = _make_bookmark(title="Intro to Machine Learning")
        self.assertFalse(sc.matches(bm))


class TestSmartCollectionMatchesDate(_IsolatedTestBase):
    """SmartCollection.matches() — after/before date filters."""

    def _sc(self, **filter_kw):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollection, SmartCollectionFilter,
        )
        return SmartCollection(
            id="test", name="Test",
            filters=SmartCollectionFilter(**filter_kw),
        )

    def test_after_filter_passes(self):
        sc = self._sc(after="2026-01-01T00:00:00")
        bm = _make_bookmark(created_at="2026-06-01T12:00:00")
        self.assertTrue(sc.matches(bm))

    def test_after_filter_rejects(self):
        sc = self._sc(after="2026-06-01T00:00:00")
        bm = _make_bookmark(created_at="2025-12-31T23:59:59")
        self.assertFalse(sc.matches(bm))

    def test_before_filter_passes(self):
        sc = self._sc(before="2026-06-01T00:00:00")
        bm = _make_bookmark(created_at="2025-12-31T23:59:59")
        self.assertTrue(sc.matches(bm))

    def test_before_filter_rejects(self):
        sc = self._sc(before="2025-01-01T00:00:00")
        bm = _make_bookmark(created_at="2026-06-01T12:00:00")
        self.assertFalse(sc.matches(bm))


class TestSmartCollectionFromDict(_IsolatedTestBase):
    """SmartCollection.from_dict — valid and corrupt data."""

    def test_valid_roundtrip(self):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollection, SmartCollectionFilter,
        )
        original = SmartCollection(
            id="abc123", name="My Collection", icon="star",
            filters=SmartCollectionFilter(tags=["python"], domains=["github.com"]),
            created_at="2026-01-01T00:00:00", modified_at="2026-01-02T00:00:00",
        )
        d = original.to_dict()
        restored = SmartCollection.from_dict(d)
        self.assertEqual(restored.id, "abc123")
        self.assertEqual(restored.name, "My Collection")
        self.assertEqual(restored.filters.tags, ["python"])
        self.assertEqual(restored.filters.domains, ["github.com"])

    def test_corrupt_data_gets_defaults(self):
        from bookmark_organizer_pro.services.smart_collections import SmartCollection
        # Missing most fields -- should not raise
        sc = SmartCollection.from_dict({})
        self.assertEqual(sc.name, "Untitled")
        self.assertIsInstance(sc.id, str)
        self.assertTrue(len(sc.id) > 0)

    def test_filters_missing_key(self):
        from bookmark_organizer_pro.services.smart_collections import SmartCollection
        # Partial filters dict
        sc = SmartCollection.from_dict({"filters": {"tags": ["rust"]}})
        self.assertEqual(sc.filters.tags, ["rust"])
        self.assertEqual(sc.filters.domains, [])
        self.assertEqual(sc.filters.after, "")


class TestSmartCollectionManager(_IsolatedTestBase):
    """SmartCollectionManager create/delete/evaluate roundtrip."""

    def _manager(self):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollectionManager, SmartCollectionFilter,
        )
        fp = Path(self._tmp) / f"sc_mgr_{id(self)}.json"
        return SmartCollectionManager(filepath=fp), SmartCollectionFilter

    def test_create_delete_roundtrip(self):
        mgr, FilterCls = self._manager()
        sc = mgr.create("Test Collection", filters=FilterCls(tags=["python"]))
        self.assertTrue(sc.id)
        self.assertEqual(sc.name, "Test Collection")
        self.assertEqual(len(mgr.list_all()), 1)

        ok = mgr.delete(sc.id)
        self.assertTrue(ok)
        self.assertEqual(len(mgr.list_all()), 0)

    def test_evaluate_filters_bookmarks(self):
        mgr, FilterCls = self._manager()
        sc = mgr.create("Python Only", filters=FilterCls(tags=["python"]))

        bm_match = _make_bookmark(url="https://a.com", tags=["python"])
        bm_miss = _make_bookmark(url="https://b.com", tags=["rust"])
        results = mgr.evaluate(sc.id, [bm_match, bm_miss])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://a.com")

    def test_evaluate_nonexistent_returns_empty(self):
        mgr, _ = self._manager()
        results = mgr.evaluate("nonexistent-id", [_make_bookmark()])
        self.assertEqual(results, [])


# ===================================================================
# 2. EPUB Export
# ===================================================================

class TestEpubExportEmpty(_IsolatedTestBase):
    """export_epub with empty bookmark list -- should produce a valid ZIP."""

    def test_empty_produces_valid_zip(self):
        from bookmark_organizer_pro.services.epub_export import export_epub

        out_dir = Path(tempfile.mkdtemp(prefix="bop_epub_"))
        try:
            out = export_epub([], output_path=out_dir / "empty.epub")
            self.assertTrue(out.exists())
            with zipfile.ZipFile(out) as zf:
                self.assertIsNone(zf.testzip(), "ZIP should be valid")
                names = zf.namelist()
                self.assertIn("mimetype", names)
                self.assertIn("META-INF/container.xml", names)
                self.assertIn("OEBPS/content.opf", names)
                self.assertIn("OEBPS/toc.xhtml", names)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


class TestEpubExportThreeBookmarks(_IsolatedTestBase):
    """export_epub with 3 bookmarks -- verify structure."""

    def test_three_bookmarks_structure(self):
        from bookmark_organizer_pro.services.epub_export import export_epub

        bookmarks = [
            _make_bookmark(url=f"https://site{i}.com", title=f"Site {i}")
            for i in range(3)
        ]
        out_dir = Path(tempfile.mkdtemp(prefix="bop_epub_"))
        try:
            out = export_epub(bookmarks, output_path=out_dir / "three.epub")
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
                self.assertIn("mimetype", names)
                self.assertIn("META-INF/container.xml", names)
                self.assertIn("OEBPS/content.opf", names)
                self.assertIn("OEBPS/toc.xhtml", names)
                for i in range(3):
                    self.assertIn(f"OEBPS/chapter_{i:04d}.xhtml", names)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


class TestEpubMimetypeEntry(_IsolatedTestBase):
    """mimetype must be first entry, stored (not deflated), no extra field."""

    def test_mimetype_spec_compliance(self):
        from bookmark_organizer_pro.services.epub_export import export_epub

        out_dir = Path(tempfile.mkdtemp(prefix="bop_epub_"))
        try:
            out = export_epub(
                [_make_bookmark()],
                output_path=out_dir / "spec.epub",
            )
            with zipfile.ZipFile(out) as zf:
                info = zf.infolist()[0]
                self.assertEqual(info.filename, "mimetype")
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.extra, b"")
                self.assertEqual(
                    zf.read("mimetype"), b"application/epub+zip",
                )
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


class TestEpubHtmlEscaping(_IsolatedTestBase):
    """Bookmark title with <script> must not appear as raw HTML."""

    def test_script_tag_escaped(self):
        from bookmark_organizer_pro.services.epub_export import export_epub

        evil_title = '<script>alert("xss")</script>'
        bm = _make_bookmark(url="https://evil.com", title=evil_title)
        out_dir = Path(tempfile.mkdtemp(prefix="bop_epub_"))
        try:
            out = export_epub([bm], output_path=out_dir / "escape.epub")
            with zipfile.ZipFile(out) as zf:
                chapter = zf.read("OEBPS/chapter_0000.xhtml").decode("utf-8")
                self.assertNotIn("<script>", chapter)
                self.assertIn("&lt;script&gt;", chapter)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)


# ===================================================================
# 3. Obsidian Export
# ===================================================================

class TestObsidianSafeFilename(_IsolatedTestBase):
    """_safe_filename edge cases."""

    def _fn(self, title):
        from bookmark_organizer_pro.services.obsidian_export import _safe_filename
        return _safe_filename(title)

    def test_empty_string(self):
        self.assertEqual(self._fn(""), "bookmark.md")

    def test_long_title_truncated(self):
        result = self._fn("A" * 200)
        # 120 chars + ".md" = 123
        self.assertEqual(len(result), 123)
        self.assertTrue(result.endswith(".md"))

    def test_special_chars_stripped(self):
        result = self._fn('My <Site> "Best" | Page?')
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        self.assertNotIn('"', result)
        self.assertNotIn("|", result)
        self.assertNotIn("?", result)
        self.assertTrue(result.endswith(".md"))


class TestObsidianYamlEscape(_IsolatedTestBase):
    """_yaml_escape handles dangerous characters."""

    def _esc(self, value):
        from bookmark_organizer_pro.services.obsidian_export import _yaml_escape
        return _yaml_escape(value)

    def test_quotes(self):
        result = self._esc('He said "hello"')
        self.assertIn('\\"', result)
        # Must be wrapped in outer quotes
        self.assertTrue(result.startswith('"') and result.endswith('"'))

    def test_newlines(self):
        result = self._esc("line1\nline2")
        self.assertNotIn("\n", result)
        self.assertIn("\\n", result)

    def test_colons_safe(self):
        result = self._esc("key: value")
        # Double-quoted, so colons are safe
        self.assertTrue(result.startswith('"'))

    def test_hash_safe(self):
        result = self._esc("# heading")
        self.assertTrue(result.startswith('"'))


class TestObsidianExportBookmark(_IsolatedTestBase):
    """export_bookmark produces valid YAML frontmatter."""

    def test_frontmatter_fields(self):
        from bookmark_organizer_pro.services.obsidian_export import export_bookmark

        vault = Path(tempfile.mkdtemp(prefix="bop_obs_"))
        try:
            bm = _make_bookmark(
                url="https://example.com/page",
                title="Example Page",
                category="Dev",
                tags=["python", "tutorial"],
                created_at="2026-01-15T10:30:00",
            )
            path = export_bookmark(bm, vault)
            content = path.read_text(encoding="utf-8")

            # Must start with YAML frontmatter
            self.assertTrue(content.startswith("---\n"))
            # Must have closing ---
            second_fence = content.index("---", 4)
            self.assertGreater(second_fence, 4)

            fm = content[4:second_fence]
            self.assertIn("url:", fm)
            self.assertIn("title:", fm)
            self.assertIn("category:", fm)
            self.assertIn("tags:", fm)
            self.assertIn("created:", fm)
        finally:
            shutil.rmtree(vault, ignore_errors=True)

    def test_yaml_injection_blocked(self):
        """Title with embedded newline+key must not create a new YAML key."""
        from bookmark_organizer_pro.services.obsidian_export import export_bookmark

        vault = Path(tempfile.mkdtemp(prefix="bop_obs_"))
        try:
            evil_title = '"\nnew_key: injected'
            bm = _make_bookmark(url="https://inject.com", title=evil_title)
            path = export_bookmark(bm, vault)
            content = path.read_text(encoding="utf-8")

            # Extract frontmatter between the two --- fences
            parts = content.split("---")
            fm_text = parts[1]

            # The raw newline in the title must have been escaped (\\n),
            # so the frontmatter should NOT contain a bare line starting
            # with "new_key:" as a top-level YAML key.
            fm_lines = fm_text.strip().splitlines()
            top_level_keys = [
                ln.split(":")[0].strip()
                for ln in fm_lines
                if ln and not ln.startswith(" ") and ":" in ln
            ]
            self.assertNotIn(
                "new_key", top_level_keys,
                "Injected key must not appear as a top-level YAML key",
            )
        finally:
            shutil.rmtree(vault, ignore_errors=True)


class TestObsidianExportCollection(_IsolatedTestBase):
    """export_collection with tag_filter and since filter."""

    def test_tag_filter(self):
        from bookmark_organizer_pro.services.obsidian_export import export_collection

        vault = Path(tempfile.mkdtemp(prefix="bop_obs_"))
        try:
            bm_match = _make_bookmark(url="https://a.com", title="A", tags=["python"])
            bm_miss = _make_bookmark(url="https://b.com", title="B", tags=["rust"])
            paths = export_collection([bm_match, bm_miss], vault, tag_filter="python")
            self.assertEqual(len(paths), 1)
        finally:
            shutil.rmtree(vault, ignore_errors=True)

    def test_since_filter(self):
        from bookmark_organizer_pro.services.obsidian_export import export_collection

        vault = Path(tempfile.mkdtemp(prefix="bop_obs_"))
        try:
            old = _make_bookmark(
                url="https://old.com", title="Old",
                created_at="2020-01-01T00:00:00",
            )
            new = _make_bookmark(
                url="https://new.com", title="New",
                created_at="2026-06-01T00:00:00",
            )
            paths = export_collection(
                [old, new], vault, since="2025-01-01T00:00:00",
            )
            self.assertEqual(len(paths), 1)
            # The one exported should be the new bookmark
            content = paths[0].read_text(encoding="utf-8")
            self.assertIn("new.com", content)
        finally:
            shutil.rmtree(vault, ignore_errors=True)


class TestObsidianDuplicateTitle(_IsolatedTestBase):
    """Duplicate titles get a _1, _2, ... suffix on the filename."""

    def test_duplicate_title_suffix(self):
        from bookmark_organizer_pro.services.obsidian_export import export_bookmark

        vault = Path(tempfile.mkdtemp(prefix="bop_obs_"))
        try:
            bm1 = _make_bookmark(url="https://a.com", title="Same Title")
            bm2 = _make_bookmark(url="https://b.com", title="Same Title")
            bm3 = _make_bookmark(url="https://c.com", title="Same Title")

            p1 = export_bookmark(bm1, vault)
            p2 = export_bookmark(bm2, vault)
            p3 = export_bookmark(bm3, vault)

            # All three files must exist and be distinct
            self.assertTrue(p1.exists())
            self.assertTrue(p2.exists())
            self.assertTrue(p3.exists())
            self.assertEqual(len({p1, p2, p3}), 3)

            # The suffixed ones should have _1 and _2
            names = sorted([p1.name, p2.name, p3.name])
            self.assertIn("Same Title.md", names)
            self.assertIn("Same Title_1.md", names)
            self.assertIn("Same Title_2.md", names)
        finally:
            shutil.rmtree(vault, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
