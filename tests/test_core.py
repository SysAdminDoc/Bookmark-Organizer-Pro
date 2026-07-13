"""Core tests for pattern engine, URL normalization, search, and bookmark model."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import tokenize
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

# Ensure package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookmark_organizer_pro.models.bookmark import Bookmark
from bookmark_organizer_pro.models.category import Category
from bookmark_organizer_pro.ai import AIClient, AIConfigManager
from bookmark_organizer_pro.constants import IS_WINDOWS
from bookmark_organizer_pro.core.category_manager import CategoryManager
from bookmark_organizer_pro.core.sqlite_storage import SQLiteStorageManager, migrate_json_to_sqlite
from bookmark_organizer_pro.core.storage_manager import (
    StorageConflictError,
    StorageManager,
    StorageRecoveryRequiredError,
)
from bookmark_organizer_pro.core.pattern_engine import PatternEngine
from bookmark_organizer_pro.importers import OPMLExporter, OPMLImporter, RaindropImporter, TextURLImporter
from bookmark_organizer_pro.io_formats import XBELHandler
from bookmark_organizer_pro.link_checker import LinkChecker
from bookmark_organizer_pro.search import SearchQuery, SearchEngine, levenshtein_distance, fuzzy_match
from bookmark_organizer_pro.ui import (
    DensityManager,
    DisplayDensity,
    ReportGenerator,
    SearchHighlighter,
    SystemThemeDetector,
    ThemeColors,
    ThemeInfo,
    ThemeManager,
    build_collection_pulse,
    build_collection_summary,
    build_dashboard_statistics,
    build_filter_counts,
    contrast_ratio,
    format_compact_count,
    NonBlockingTaskRunner,
    pick_default_category,
    prepare_quick_add_payload,
    readable_text_on,
    truncate_middle,
)
from bookmark_organizer_pro.utils.url import normalize_url
from bookmark_organizer_pro.utils.safe import safe_get_domain, truncate_string
from bookmark_organizer_pro.utils.runtime import run_with_timeout
from bookmark_organizer_pro.utils.dependencies import DependencyManager, is_frozen_runtime
from bookmark_organizer_pro.utils.health import calculate_health_score, merge_duplicate_bookmarks
from bookmark_organizer_pro.utils.validators import validate_path, validate_url
from bookmark_organizer_pro.url_utils import URLUtilities


class TestBookmarkModel(unittest.TestCase):
    """Test Bookmark creation, serialization, and validation."""

    def test_create_bookmark(self):
        bm = Bookmark(id=None, url="https://example.com", title="Example")
        self.assertIsNotNone(bm.id)
        self.assertEqual(bm.url, "https://example.com")
        self.assertTrue(bm.id.bit_length() <= 64)  # 8-byte ID

    def test_round_trip_serialization(self):
        bm = Bookmark(id=42, url="https://test.com", title="Test", tags=["a", "b"])
        d = bm.to_dict()
        bm2 = Bookmark.from_dict(d)
        self.assertEqual(bm.id, bm2.id)
        self.assertEqual(bm.url, bm2.url)
        self.assertEqual(bm.tags, bm2.tags)

    def test_from_dict_empty_url_raises(self):
        with self.assertRaises(ValueError):
            Bookmark.from_dict({"url": "", "title": "empty"})

    def test_from_dict_non_string_url_raises(self):
        with self.assertRaises(ValueError):
            Bookmark.from_dict({"url": None, "title": "none"})
        with self.assertRaises(ValueError):
            Bookmark.from_dict({"url": 123, "title": "number"})

    def test_bookmark_constructor_rejects_empty_url_and_sanitizes_custom_data(self):
        with self.assertRaises(ValueError):
            Bookmark(id=1, url="", title="empty")
        bm = Bookmark(id=1, url=" https://x.com ", title="", custom_data=["bad"])
        self.assertEqual(bm.url, "https://x.com")
        self.assertEqual(bm.title, "https://x.com")
        self.assertEqual(bm.custom_data, {})

    def test_from_dict_corrupt_numerics(self):
        bm = Bookmark.from_dict({
            "url": "https://x.com",
            "visit_count": "not_a_number",
            "ai_confidence": 999,
            "http_status": -5,
        })
        self.assertEqual(bm.visit_count, 0)
        self.assertEqual(bm.ai_confidence, 1.0)
        self.assertEqual(bm.http_status, 0)

    def test_from_dict_tags_as_string(self):
        bm = Bookmark.from_dict({"url": "https://x.com", "tags": "a,b, c, A"})
        self.assertEqual(bm.tags, ["a", "b", "c"])

    def test_add_tag_is_case_insensitive_and_strips_input(self):
        bm = Bookmark(id=1, url="https://x.com", title="X", tags=["AI"])
        bm.add_tag(" ai ")
        bm.add_tag("Tools")
        self.assertEqual(bm.tags, ["AI", "Tools"])

    def test_from_dict_coerces_string_booleans_and_bad_id(self):
        bm = Bookmark.from_dict({
            "id": "not_an_id",
            "url": "https://x.com",
            "is_valid": "false",
            "is_pinned": "yes",
            "is_archived": "0",
        })
        self.assertIsInstance(bm.id, int)
        self.assertFalse(bm.is_valid)
        self.assertTrue(bm.is_pinned)
        self.assertFalse(bm.is_archived)

    def test_clean_url_strips_tracking(self):
        bm = Bookmark(id=1, url="https://example.com/page?utm_source=test&real=1", title="T")
        cleaned = bm.clean_url()
        self.assertNotIn("utm_source", cleaned)
        self.assertIn("real=1", cleaned)

    def test_domain_property(self):
        bm = Bookmark(id=1, url="https://www.github.com/user/repo", title="T")
        self.assertEqual(bm.domain, "github.com")

    def test_domain_strips_only_leading_www(self):
        bm = Bookmark(id=1, url="https://mywww.example.com/path", title="T")
        self.assertEqual(bm.domain, "mywww.example.com")
        self.assertEqual(
            safe_get_domain("https://www.notwww.example.com/path"),
            "notwww.example.com",
        )


class TestCategoryModelAndManager(unittest.TestCase):
    """Test category deserialization and hierarchy safeguards."""

    def test_category_from_dict_sanitizes_fields(self):
        cat = Category.from_dict({
            "name": "  Dev  ",
            "patterns": [" domain:github.com ", "", None],
            "is_collapsed": "false",
            "sort_order": "5",
        })
        self.assertEqual(cat.name, "Dev")
        self.assertEqual(cat.patterns, ["domain:github.com"])
        self.assertFalse(cat.is_collapsed)
        self.assertEqual(cat.sort_order, 5)

    def test_category_manager_trims_names_and_blocks_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "categories.json"
            manager = CategoryManager(filepath=path)
            self.assertTrue(manager.add_category(" Work "))
            self.assertFalse(manager.add_category("Work"))
            self.assertTrue(manager.add_category("Child", parent="Work"))
            self.assertFalse(manager.move_category("Work", "Child"))
            self.assertEqual(manager.categories["Work"].parent, "")

    def test_category_manager_removes_descendants_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "categories.json"
            manager = CategoryManager(filepath=path)
            self.assertTrue(manager.add_category("Parent"))
            self.assertTrue(manager.add_category("Child", parent="Parent"))
            self.assertTrue(manager.add_category("Grandchild", parent="Child"))

            self.assertTrue(manager.remove_category("Parent"))

            self.assertNotIn("Parent", manager.categories)
            self.assertNotIn("Child", manager.categories)
            self.assertNotIn("Grandchild", manager.categories)

    def test_category_manager_blocks_merge_into_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "categories.json"
            manager = CategoryManager(filepath=path)
            self.assertTrue(manager.add_category("Parent", patterns=["domain:example.com"]))
            self.assertTrue(manager.add_category("Child", parent="Parent", patterns=["domain:child.example"]))

            self.assertFalse(manager.merge_categories("Parent", "Child"))
            self.assertIn("Parent", manager.categories)
            self.assertEqual(manager.categories["Child"].parent, "Parent")

    def test_category_manager_sanitizes_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "categories.json"
            manager = CategoryManager(filepath=path)
            self.assertTrue(manager.add_category("Clean", patterns=[" domain:x.com ", "", "DOMAIN:x.com"]))
            self.assertEqual(manager.get_patterns("Clean"), ["domain:x.com"])

    def test_category_manager_recovers_invalid_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "categories.json"
            path.write_text("[]", encoding="utf-8")
            manager = CategoryManager(filepath=path)
            self.assertIn("Uncategorized / Needs Review", manager.categories)

    def test_category_manager_repairs_cycles_loaded_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "categories.json"
            path.write_text(
                '{"A": {"name": "A", "parent": "B"}, '
                '"B": {"name": "B", "parent": "A"}}',
                encoding="utf-8",
            )
            manager = CategoryManager(filepath=path)
            self.assertEqual(manager.categories["A"].parent, "")


class TestPatternEngine(unittest.TestCase):
    """Test URL/title categorization engine."""

    def setUp(self):
        self.engine = PatternEngine({
            "Development": ["domain:github.com", "domain:gitlab.com", "keyword:api documentation"],
            "News": ["domain:cnn.com", "keyword:breaking news"],
            "AI": ["regex:\\.ai(/|$)"],
        })

    def test_domain_match(self):
        self.assertEqual(self.engine.match("https://github.com/user/repo"), "Development")

    def test_domain_suffix_match(self):
        self.assertEqual(self.engine.match("https://gist.github.com/123"), "Development")

    def test_domain_patterns_normalize_leading_www(self):
        engine = PatternEngine({"Development": ["domain:www.github.com"]})
        self.assertEqual(engine.match("https://github.com/user/repo"), "Development")

    def test_domain_no_false_positive(self):
        self.assertIsNone(self.engine.match("https://notgithub.com"))

    def test_keyword_match(self):
        self.assertEqual(
            self.engine.match("https://example.com/docs", "API Documentation for Python"),
            "Development"
        )

    def test_regex_match(self):
        self.assertEqual(self.engine.match("https://openai.ai/research"), "AI")

    def test_no_match(self):
        self.assertIsNone(self.engine.match("https://randomsite.xyz/page"))

    def test_non_string_patterns_skipped(self):
        engine = PatternEngine({"Cat": [123, None, "", "domain:test.com"]})
        self.assertEqual(engine.match("https://test.com"), "Cat")

    def test_long_regex_skipped(self):
        engine = PatternEngine({"Cat": [f"regex:{'a' * 501}"]})
        self.assertEqual(len(engine.rules), 0)

    def test_empty_typed_patterns_do_not_match_everything(self):
        engine = PatternEngine({"Cat": ["keyword:", "title:", "path:", "domain:", "ext:"]})
        self.assertIsNone(engine.match("https://example.com", "Example"))

    def test_non_string_url_does_not_crash_matcher(self):
        engine = PatternEngine({"Cat": ["keyword:example"]})
        self.assertIsNone(engine.match(None, None))

    def test_regex_timeout_is_safe_across_worker_threads(self):
        from concurrent.futures import ThreadPoolExecutor

        engine = PatternEngine({"Cat": ["regex:(a+)+$"]})
        adversarial_url = f"https://example.test/{'a' * 1900}!"

        with patch(
            "bookmark_organizer_pro.core.pattern_engine._REGEX_TIMEOUT_SECONDS",
            0.01,
        ):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(engine.match, [adversarial_url] * 16))

        self.assertEqual(results, [None] * 16)

    def test_default_category_patterns_have_no_implicit_string_concatenation(self):
        path = Path(__file__).resolve().parents[1] / "bookmark_organizer_pro" / "core" / "default_categories.py"
        previous_string = None
        suspects = []
        with path.open("rb") as handle:
            for token in tokenize.tokenize(handle.readline):
                if token.type in {
                    tokenize.ENCODING,
                    tokenize.NL,
                    tokenize.NEWLINE,
                    tokenize.COMMENT,
                    tokenize.INDENT,
                    tokenize.DEDENT,
                }:
                    continue
                if token.type == tokenize.STRING:
                    if previous_string is not None:
                        suspects.append((previous_string.start[0], token.start[0]))
                    previous_string = token
                else:
                    previous_string = None

        self.assertEqual(suspects, [])


class TestPatternEngineTwoPass(unittest.TestCase):
    """Test two-pass priority: domain rules beat keyword rules across categories."""

    def test_domain_beats_keyword_across_categories(self):
        engine = PatternEngine({
            "Generic": ["keyword:community"],
            "Design": ["domain:figma.com"],
        })
        self.assertEqual(
            engine.match("https://figma.com/community"),
            "Design",
        )

    def test_domain_beats_keyword_reverse_order(self):
        engine = PatternEngine({
            "Design": ["domain:dribbble.com"],
            "Forums": ["keyword:shots"],
        })
        self.assertEqual(
            engine.match("https://dribbble.com/shots"),
            "Design",
        )

    def test_keyword_fires_when_no_domain_match(self):
        engine = PatternEngine({
            "Finance": ["keyword:stock market"],
            "News": ["domain:cnn.com"],
        })
        self.assertEqual(
            engine.match("https://obscure-blog.com/page", "stock market analysis"),
            "Finance",
        )

    def test_regex_in_pass2_after_domain_miss(self):
        engine = PatternEngine({
            "Education": ["regex:\\.edu(/|$)"],
            "News": ["domain:cnn.com"],
        })
        self.assertEqual(
            engine.match("https://mit.edu/courses"),
            "Education",
        )


class TestPatternEngineIntegration(unittest.TestCase):
    """Smoke test with the real DEFAULT_CATEGORIES (7,500+ patterns)."""

    @classmethod
    def setUpClass(cls):
        from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES
        cls.engine = PatternEngine(DEFAULT_CATEGORIES)

    def test_github_to_software_development(self):
        self.assertEqual(self.engine.match("https://github.com/torvalds/linux"), "Software Development")

    def test_youtube_to_video(self):
        self.assertEqual(self.engine.match("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "Video")

    def test_amazon_to_shopping(self):
        self.assertEqual(self.engine.match("https://www.amazon.com/dp/B0123"), "Shopping")

    def test_cnn_to_news(self):
        self.assertEqual(self.engine.match("https://www.cnn.com/2025/article"), "News")

    def test_figma_community_to_design(self):
        self.assertEqual(self.engine.match("https://figma.com/community"), "Design")

    def test_unknown_domain_unmatched(self):
        self.assertIsNone(self.engine.match("https://totallyunknown98765.zzz/page", "Totally Unknown Page"))

    def test_weather_gov(self):
        self.assertEqual(self.engine.match("https://weather.gov/forecast"), "Weather")

    def test_zillow_to_real_estate(self):
        self.assertEqual(self.engine.match("https://www.zillow.com/homes/123"), "Real Estate")


class TestURLNormalization(unittest.TestCase):
    """Test URL normalization for deduplication."""

    def test_strips_tracking_params(self):
        url = "https://example.com/page?utm_source=google&real=1"
        normalized = normalize_url(url)
        self.assertNotIn("utm_source", normalized)
        self.assertIn("real=1", normalized)

    def test_strips_www(self):
        url = "https://www.example.com/page"
        normalized = normalize_url(url)
        self.assertNotIn("www.", normalized)

    def test_normalizes_scheme(self):
        url1 = normalize_url("http://example.com/page")
        url2 = normalize_url("https://example.com/page")
        # Both should normalize (exact behavior depends on implementation)
        self.assertIsInstance(url1, str)
        self.assertIsInstance(url2, str)

    def test_empty_url(self):
        self.assertEqual(normalize_url(""), "")

    def test_invalid_url(self):
        result = normalize_url("not a url")
        self.assertEqual(result, "not a url")

    def test_bare_domain_normalizes_as_https_url(self):
        self.assertEqual(normalize_url("Example.com/index.html"), "https://example.com")

    def test_normalization_strips_userinfo_and_handles_non_string_input(self):
        self.assertEqual(
            normalize_url("https://user:secret@www.example.com:443/path"),
            "https://example.com/path",
        )
        self.assertEqual(normalize_url(None), "")
        self.assertEqual(normalize_url(123), "https://123")


class TestStorageAndExportSafety(unittest.TestCase):
    """Test persistence and interchange safety guards."""

    def test_restore_backup_blocks_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "backups"
            backup_dir.mkdir()
            target = Path(tmp) / "bookmarks.json"
            manager = StorageManager(target)
            with patch("bookmark_organizer_pro.core.storage_manager.BACKUP_DIR", backup_dir):
                self.assertFalse(manager.restore_backup("../outside.json"))

    def test_opml_export_escapes_head_title_and_bookmark_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "bookmarks.opml"
            bookmarks = [
                Bookmark(
                    id=1,
                    url='https://example.com?a=1&b="x"',
                    title='A <Title> & "quote"',
                    category='Cat & <Group>',
                )
            ]
            OPMLExporter.export(bookmarks, str(output), title='Export <unsafe> & "quoted"')
            text = output.read_text(encoding="utf-8")
            self.assertIn("Export &lt;unsafe&gt; &amp; &quot;quoted&quot;", text)
            self.assertIn("Cat &amp; &lt;Group&gt;", text)
            self.assertIn("A &lt;Title&gt; &amp; &quot;quote&quot;", text)
            self.assertIn("https://example.com?a=1&amp;b=&quot;x&quot;", text)

    def test_opml_import_uses_xml_parser_for_attribute_order_and_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            opml = Path(tmp) / "bookmarks.opml"
            opml.write_text(
                """<?xml version="1.0"?>
<opml version="2.0">
  <body>
    <outline text="Research">
      <outline title="Paper" htmlUrl="https://example.com/paper?a=1&amp;b=2" />
    </outline>
  </body>
</opml>
""",
                encoding="utf-8",
            )
            bookmarks = OPMLImporter.import_from_opml(str(opml))
            self.assertEqual(len(bookmarks), 1)
            self.assertEqual(bookmarks[0].category, "Research")
            self.assertEqual(bookmarks[0].title, "Paper")
            self.assertEqual(bookmarks[0].url, "https://example.com/paper?a=1&b=2")

    def test_importers_skip_unsupported_or_malformed_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            text_file = Path(tmp) / "urls.txt"
            text_file.write_text(
                "https://safe.example/path\nhttp:///missing-host\njavascript:alert(1)",
                encoding="utf-8",
            )
            self.assertEqual(
                [bm.url for bm in TextURLImporter.import_from_text(str(text_file))],
                ["https://safe.example/path"],
            )

            csv_file = Path(tmp) / "raindrop.csv"
            csv_file.write_text(
                "url,title\njavascript:alert(1),Bad\nhttps://safe.example,Good\n",
                encoding="utf-8",
            )
            self.assertEqual(
                [bm.title for bm in RaindropImporter.import_from_csv(str(csv_file))],
                ["Good"],
            )

    def test_storage_backups_do_not_collide_with_rapid_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_dir = Path(tmp) / "backups"
            backup_dir.mkdir()
            target = Path(tmp) / "bookmarks.json"
            manager = StorageManager(target)
            with patch("bookmark_organizer_pro.core.storage_manager.BACKUP_DIR", backup_dir):
                manager.save([Bookmark(id=1, url="https://one.example", title="One").to_dict()])
                manager.save([Bookmark(id=2, url="https://two.example", title="Two").to_dict()])
                manager.save([Bookmark(id=3, url="https://three.example", title="Three").to_dict()])
                backups = list(backup_dir.glob("bookmarks_*.json"))
                self.assertEqual(len(backups), 2)
                self.assertEqual(len({p.name for p in backups}), 2)

    def test_storage_load_rejects_non_list_data_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.json"
            target.write_text('{"data": {"url": "https://example.com"}}', encoding="utf-8")
            manager = StorageManager(target)
            self.assertEqual(manager.load(), [])
            self.assertEqual(manager.status.state, "corrupt")

    def test_storage_distinguishes_absent_valid_empty_and_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.json"
            manager = StorageManager(target)

            self.assertEqual(manager.load(), [])
            self.assertEqual(manager.status.state, "absent")

            manager.save([])
            self.assertEqual(manager.load(), [])
            self.assertEqual(manager.status.state, "valid_empty")

            damaged = '{"data": ['
            target.write_text(damaged, encoding="utf-8")
            self.assertEqual(manager.load(), [])
            self.assertEqual(manager.status.state, "corrupt")
            self.assertIn("line 1, column", manager.status.error)
            with self.assertRaisesRegex(StorageRecoveryRequiredError, "Restore a verified backup"):
                manager.save([])
            self.assertEqual(target.read_text(encoding="utf-8"), damaged)

    def test_storage_salvage_preserves_corrupt_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.json"
            recovery_dir = Path(tmp) / "backups" / "recovery"
            damaged = (
                '{"data":['
                '{"id":1,"url":"https://one.example","title":"One"},'
                '{"id":2,"url":"https://two.example","title":"Two"}'
            )
            target.write_text(damaged, encoding="utf-8")
            manager = StorageManager(target)
            self.assertEqual(manager.load(), [])

            with patch("bookmark_organizer_pro.core.storage_manager.RECOVERY_DIR", recovery_dir):
                recovered = manager.salvage()
                preserved = Path(manager.commit_salvage(recovered))

            self.assertEqual([bookmark.id for bookmark in recovered], [1, 2])
            self.assertEqual(preserved.read_text(encoding="utf-8"), damaged)
            self.assertEqual([bookmark.id for bookmark in manager.load()], [1, 2])
            self.assertEqual(manager.status.state, "valid")

    def test_sqlite_storage_round_trips_bookmarks_with_wal(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.sqlite"
            manager = SQLiteStorageManager(target)
            bookmark = Bookmark(
                id=42,
                url="https://sqlite.example",
                title="SQLite",
                category="Research",
                tags=["db", "wal"],
                is_pinned=True,
                read_later=True,
            )

            manager.save([bookmark.to_dict()])
            loaded = manager.load()

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].id, 42)
            self.assertEqual(loaded[0].tags, ["db", "wal"])
            self.assertTrue(loaded[0].is_pinned)
            self.assertTrue(loaded[0].read_later)
            self.assertEqual(manager.get_metadata()["count"], "1")
            conn = sqlite3.connect(target)
            try:
                self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            finally:
                conn.close()

            explicit_conn = manager._connect()
            try:
                self.assertIsNone(explicit_conn.isolation_level)
            finally:
                explicit_conn.close()

    def test_sqlite_replacement_rejects_invalid_row_without_changing_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.sqlite"
            manager = SQLiteStorageManager(target)
            original = Bookmark(id=1, url="https://original.example", title="Original")
            manager.save([original.to_dict()])

            replacement = Bookmark(id=2, url="https://replacement.example", title="Replacement")
            with self.assertRaisesRegex(ValueError, "index 1.*URL is required"):
                manager.save([replacement.to_dict(), {"id": 3, "url": "", "title": "Bad"}])

            self.assertEqual([bookmark.id for bookmark in manager.load()], [1])
            self.assertEqual(manager.get_metadata()["count"], "1")

    def test_sqlite_replacement_rejects_duplicate_ids_and_records_validated_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.sqlite"
            manager = SQLiteStorageManager(target)
            first = Bookmark(id=1, url="https://first.example", title="First")
            second = Bookmark(id=1, url="https://second.example", title="Second")

            with self.assertRaisesRegex(ValueError, "duplicate bookmark id 1"):
                manager.save([first.to_dict(), second.to_dict()])
            self.assertEqual(manager.load(), [])

            manager.save([first.to_dict()], metadata={"count": 999, "saved_at": "test"})
            self.assertEqual(manager.get_metadata()["count"], "1")

    def test_sqlite_storage_preserves_unsigned_bookmark_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.sqlite"
            manager = SQLiteStorageManager(target)
            large_id = 2**63 + 99

            manager.save([Bookmark(id=large_id, url="https://large-id.example", title="Large").to_dict()])
            loaded = manager.load()

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].id, large_id)

    def test_sqlite_storage_fails_closed_on_corrupt_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "bookmarks.sqlite"
            manager = SQLiteStorageManager(target)
            manager.save([Bookmark(id=1, url="https://ok.example", title="OK").to_dict()])
            conn = manager._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO bookmarks(
                        id, position, url, title, payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (2, 2, "https://bad.example", "Bad", "{not json"),
                )
                conn.commit()
            finally:
                conn.close()

            loaded = manager.load()

            self.assertEqual(loaded, [])
            self.assertTrue(manager.status.recovery_required)
            with self.assertRaisesRegex(Exception, "Restore a verified backup"):
                manager.save([])

    def test_migrate_json_to_sqlite_copies_existing_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bookmarks.json"
            target = Path(tmp) / "bookmarks.sqlite"
            backups = Path(tmp) / "backups"
            bookmark = Bookmark(id=7, url="https://migrate.example", title="Migrate")
            source_manager = StorageManager(source)
            source_manager.save([bookmark.to_dict()])
            source_manager.save([bookmark.to_dict()], expected_revision=1)

            with (
                patch("bookmark_organizer_pro.core.sqlite_storage.BACKUP_DIR", backups),
                patch("bookmark_organizer_pro.core.storage_manager.BACKUP_DIR", backups),
                patch(
                    "bookmark_organizer_pro.core.storage_manager.SAFEPOINT_DIR",
                    backups / "safepoints",
                ),
            ):
                count = migrate_json_to_sqlite(source, target)

            self.assertEqual(count, 1)
            destination = SQLiteStorageManager(target)
            loaded = destination.load()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].url, "https://migrate.example")
            self.assertEqual(destination.current_revision(), 2)
            safepoints = list((backups / "safepoints").glob("*.json"))
            self.assertEqual(len(safepoints), 1)
            self.assertTrue(safepoints[0].with_suffix(".sha256").is_file())

    def test_migrate_json_to_sqlite_rejects_corrupt_and_future_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backups = root / "backups"
            cases = {
                "corrupt": b'{"version": 4, "data": [',
                "future": json.dumps(
                    {"version": StorageManager.CURRENT_VERSION + 1, "revision": 9, "data": []}
                ).encode("utf-8"),
            }
            for label, original in cases.items():
                with self.subTest(label=label):
                    source = root / f"{label}.json"
                    target = root / f"{label}.sqlite"
                    source.write_bytes(original)
                    with (
                        patch("bookmark_organizer_pro.core.sqlite_storage.BACKUP_DIR", backups),
                        patch("bookmark_organizer_pro.core.storage_manager.BACKUP_DIR", backups),
                        patch(
                            "bookmark_organizer_pro.core.storage_manager.SAFEPOINT_DIR",
                            backups / "safepoints",
                        ),
                        self.assertRaises(StorageRecoveryRequiredError),
                    ):
                        migrate_json_to_sqlite(source, target)
                    self.assertEqual(source.read_bytes(), original)
                    self.assertFalse(target.exists())

    def test_migrate_json_to_sqlite_verification_failure_never_activates_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bookmarks.json"
            target = root / "bookmarks.sqlite"
            backups = root / "backups"
            bookmark = Bookmark(id=17, url="https://authoritative.example", title="Source")
            StorageManager(source).save([bookmark.to_dict()])
            original = source.read_bytes()

            from bookmark_organizer_pro.core import sqlite_storage

            real_identity = sqlite_storage._migration_identity
            calls = 0

            def mismatched_destination(bookmarks, revision):
                nonlocal calls
                calls += 1
                identity = real_identity(bookmarks, revision)
                if calls == 3:
                    return (*identity[:-1], "mismatched-digest")
                return identity

            with (
                patch("bookmark_organizer_pro.core.sqlite_storage.BACKUP_DIR", backups),
                patch("bookmark_organizer_pro.core.storage_manager.BACKUP_DIR", backups),
                patch(
                    "bookmark_organizer_pro.core.storage_manager.SAFEPOINT_DIR",
                    backups / "safepoints",
                ),
                patch(
                    "bookmark_organizer_pro.core.sqlite_storage._migration_identity",
                    side_effect=mismatched_destination,
                ),
                self.assertRaisesRegex(StorageRecoveryRequiredError, "verification failed"),
            ):
                migrate_json_to_sqlite(source, target)

            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(target.exists())
            self.assertEqual(list(root.glob(".*.migration-*.tmp*")), [])

    def test_migrate_json_to_sqlite_does_not_replace_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bookmarks.json"
            target = root / "bookmarks.sqlite"
            StorageManager(source).save(
                [Bookmark(id=1, url="https://source.example", title="Source").to_dict()]
            )
            destination = SQLiteStorageManager(target)
            destination.save(
                [Bookmark(id=2, url="https://existing.example", title="Existing").to_dict()]
            )
            original = target.read_bytes()

            with self.assertRaises(FileExistsError):
                migrate_json_to_sqlite(source, target)

            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(
                [bookmark.id for bookmark in SQLiteStorageManager(target).load()],
                [2],
            )

    def test_migrate_json_to_sqlite_rejects_source_change_before_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bookmarks.json"
            target = root / "bookmarks.sqlite"
            backups = root / "backups"
            StorageManager(source).save(
                [Bookmark(id=1, url="https://first.example", title="First").to_dict()]
            )
            replacement = Bookmark(id=2, url="https://newer.example", title="Newer")
            real_validate = SQLiteStorageManager._validate_database_file

            def validate_then_change_source(path):
                migrated = real_validate(path)
                StorageManager(source).save(
                    [replacement.to_dict()],
                    expected_revision=1,
                )
                return migrated

            with (
                patch("bookmark_organizer_pro.core.sqlite_storage.BACKUP_DIR", backups),
                patch("bookmark_organizer_pro.core.storage_manager.BACKUP_DIR", backups),
                patch(
                    "bookmark_organizer_pro.core.storage_manager.SAFEPOINT_DIR",
                    backups / "safepoints",
                ),
                patch.object(
                    SQLiteStorageManager,
                    "_validate_database_file",
                    side_effect=validate_then_change_source,
                ),
                self.assertRaisesRegex(StorageConflictError, "source changed"),
            ):
                migrate_json_to_sqlite(source, target)

            self.assertFalse(target.exists())
            self.assertEqual(
                [bookmark.id for bookmark in StorageManager(source).load()],
                [2],
            )

    def test_xbel_export_creates_parent_dirs_and_imports_own_doctype(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "nested" / "bookmarks.xbel"
            XBELHandler.export(
                [Bookmark(id=1, url="https://example.com", title="Example", category="Research")],
                str(output),
            )

            self.assertTrue(output.exists())
            bookmarks = XBELHandler.import_from_xbel(str(output))
            self.assertEqual(len(bookmarks), 1)
            self.assertEqual(bookmarks[0].category, "Research")
            self.assertEqual(bookmarks[0].url, "https://example.com")

    def test_xbel_import_rejects_xml_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            xbel = Path(tmp) / "unsafe.xbel"
            xbel.write_text(
                """<?xml version="1.0"?>
<!DOCTYPE xbel [
  <!ENTITY unsafe "expanded">
]>
<xbel version="1.0"><bookmark href="https://example.com"><title>&unsafe;</title></bookmark></xbel>
""",
                encoding="utf-8",
            )
            self.assertEqual(XBELHandler.import_from_xbel(str(xbel)), [])

    def test_xbel_import_preserves_nested_folder_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            xbel = Path(tmp) / "nested.xbel"
            xbel.write_text(
                """<?xml version="1.0"?>
<xbel version="1.0">
  <title>Bookmarks</title>
  <folder>
    <title>Research</title>
    <folder>
      <title>Papers</title>
      <bookmark href="https://example.com/paper"><title>Paper</title></bookmark>
    </folder>
  </folder>
</xbel>
""",
                encoding="utf-8",
            )
            bookmarks = XBELHandler.import_from_xbel(str(xbel))
            self.assertEqual(len(bookmarks), 1)
            self.assertEqual(bookmarks[0].category, "Research / Papers")


    def test_xbel_round_trip_preserves_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = [
                Bookmark(id=1, url="https://example.com/a", title="Alpha",
                         category="Research / Papers", tags=["python", "ml"],
                         description="A test bookmark"),
                Bookmark(id=2, url="https://example.com/b", title="Beta",
                         category="Development", tags=["rust"],
                         description="Another bookmark"),
                Bookmark(id=3, url="https://example.com/c", title="Gamma",
                         category="General"),
            ]
            xbel_path = Path(tmp) / "round_trip.xbel"
            XBELHandler.export(original, str(xbel_path))
            imported = XBELHandler.import_from_xbel(str(xbel_path))

            self.assertEqual(len(imported), len(original))
            by_url = {bm.url: bm for bm in imported}
            for orig in original:
                imp = by_url.get(orig.url)
                self.assertIsNotNone(imp, f"Missing URL: {orig.url}")
                self.assertEqual(imp.title, orig.title)
                self.assertEqual(imp.category, orig.category)


class TestNetworkSafety(unittest.TestCase):
    """Test network helpers avoid unsafe targets before making requests."""

    def test_private_urls_are_not_safe_fetch_targets(self):
        self.assertFalse(URLUtilities._is_safe_url("http://127.0.0.1/admin"))
        self.assertFalse(URLUtilities._is_safe_url("file:///etc/passwd"))

    def test_shortener_detection_avoids_substring_false_positive(self):
        self.assertTrue(URLUtilities.is_shortened_url("https://bit.ly/abc"))
        self.assertFalse(URLUtilities.is_shortened_url("https://notbit.ly.evil/abc"))

    def test_link_checker_rejects_localhost_without_network_request(self):
        bm = Bookmark(id=1, url="http://127.0.0.1/admin", title="Local")
        ok, status = LinkChecker()._check_url(bm)
        self.assertFalse(ok)
        self.assertEqual(status, 0)

    def test_non_global_ip_urls_are_not_safe_fetch_targets(self):
        self.assertFalse(URLUtilities._is_safe_url("http://169.254.169.254/latest"))
        self.assertFalse(URLUtilities._is_safe_url("http://224.0.0.1/"))

    def test_package_wayback_helpers_close_responses(self):
        from bookmark_organizer_pro.utils import metadata

        class FakeResponse:
            def __init__(self, payload, url="https://web.archive.org/save/https://example.com"):
                self.payload = payload
                self.url = url
                self.status_code = 200
                self.headers = {"Content-Location": "/web/20200101000000/https://example.com"}
                self.closed = False

            def json(self):
                return self.payload

            def close(self):
                self.closed = True

        check_response = FakeResponse({
            "archived_snapshots": {
                "closest": {"available": True, "url": "https://web.archive.org/web/x"}
            }
        })
        save_response = FakeResponse({})

        class FakeRequests:
            def __init__(self):
                self.responses = [check_response, save_response]

            def get(self, *args, **kwargs):
                return self.responses.pop(0)

        fake_requests = FakeRequests()
        with patch("bookmark_organizer_pro.utils.metadata._is_safe_url", return_value=True), \
                patch(
                    "bookmark_organizer_pro.services.egress.public_egress.get",
                    side_effect=fake_requests.get,
                ):
            self.assertEqual(metadata.wayback_check("https://example.com"), "https://web.archive.org/web/x")
            self.assertEqual(
                metadata.wayback_save("https://example.com"),
                "https://web.archive.org/web/20200101000000/https://example.com",
            )

        self.assertTrue(check_response.closed)
        self.assertTrue(save_response.closed)

    def test_main_wayback_snapshot_requests_are_closed_and_bounded(self):
        import main

        class FakeResponse:
            status_code = 200
            closed = False

            def json(self):
                return [
                    ["timestamp", "original", "statuscode"],
                    ["20200101000000", "https://example.com", "200"],
                ]

            def close(self):
                self.closed = True

        response = FakeResponse()
        captured = {}

        class FakeRequests:
            def get(self, *args, **kwargs):
                captured.update(kwargs)
                return response

        with patch("bookmark_organizer_pro.services.web_tools.URLUtilities._is_safe_url", return_value=True), \
                patch("bookmark_organizer_pro.services.web_tools.requests", FakeRequests()):
            snapshots = main.WaybackMachine.get_snapshots("https://example.com", limit=999)

        self.assertTrue(response.closed)
        self.assertEqual(captured["params"]["limit"], 100)
        self.assertEqual(snapshots[0]["date"], "2020-01-01")


class TestAIConfigHardening(unittest.TestCase):
    """Test malformed AI config files are normalized defensively."""

    def test_ai_config_normalizes_corrupt_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_config.json"
            path.write_text(
                '{"provider": "unknown", "batch_size": "bad", '
                '"requests_per_minute": 999, "min_confidence": "bad", '
                '"api_keys": []}',
                encoding="utf-8",
            )
            config = AIConfigManager(filepath=path)
            self.assertEqual(config.get_provider(), "google")
            self.assertEqual(config.get_batch_size(), 20)
            self.assertEqual(config.get_rate_limit(), 120)
            self.assertEqual(config.get_min_confidence(), 0.5)
            config.set_batch_size("bad")
            self.assertEqual(config.get_batch_size(), 20)


class TestAIResponseParsing(unittest.TestCase):
    """Test AI provider response parsing tolerates imperfect model output."""

    def test_ai_response_parser_preserves_title_and_sanitizes_fields(self):
        original = [
            {"url": "https://one.example"},
            {"url": "https://missing.example"},
        ]
        response = json.dumps({
            "results": [{
                "url": "https://one.example",
                "category": "Development",
                "confidence": "not-a-number",
                "tags": "AI, ai, machine learning, tools",
                "suggested_title": "Better Title",
                "reasoning": "Useful developer tooling.",
            }]
        })

        parsed = AIClient()._parse_response(response, original)

        self.assertEqual(parsed[0]["category"], "Development")
        self.assertEqual(parsed[0]["confidence"], 0.5)
        self.assertEqual(parsed[0]["tags"], ["ai", "machine-learning", "tools"])
        self.assertEqual(parsed[0]["suggested_title"], "Better Title")
        self.assertEqual(parsed[1]["url"], "https://missing.example")
        self.assertEqual(parsed[1]["confidence"], 0.0)


class TestSearchQuery(unittest.TestCase):
    """Test search query parsing."""

    def test_basic_text_search(self):
        q = SearchQuery("python tutorial")
        self.assertEqual(q.text_terms, ["python", "tutorial"])

    def test_domain_filter(self):
        q = SearchQuery("domain:github.com")
        self.assertEqual(q.domain_filters, ["github.com"])

    def test_tag_filter(self):
        q = SearchQuery("tag:python")
        self.assertEqual(q.tag_filters, ["python"])

    def test_hashtag_filter(self):
        q = SearchQuery("#javascript")
        self.assertEqual(q.tag_filters, ["javascript"])

    def test_category_filter(self):
        q = SearchQuery("cat:Development")
        self.assertEqual(q.category_filters, ["Development"])

    def test_regex_mode(self):
        q = SearchQuery("/github\\.com/")
        self.assertTrue(q.is_regex)
        self.assertIsNotNone(q.regex_pattern)

    def test_status_filters(self):
        q = SearchQuery("is:pinned has:notes")
        self.assertTrue(q.is_pinned)
        self.assertTrue(q.has_notes)

    def test_visit_filter(self):
        q = SearchQuery("visits:>5")
        self.assertEqual(q.min_visits, 5)

    def test_matches_basic(self):
        bm = Bookmark(id=1, url="https://github.com/user", title="Python tutorial")
        q = SearchQuery("python")
        self.assertTrue(q.matches(bm))

    def test_matches_domain_filter(self):
        bm = Bookmark(id=1, url="https://github.com/user", title="Repo")
        q = SearchQuery("domain:github.com")
        self.assertTrue(q.matches(bm))

    def test_matches_ai_tags(self):
        bm = Bookmark(id=1, url="https://example.com", title="Example", ai_tags=["research"])
        self.assertTrue(SearchQuery("tag:research").matches(bm))
        self.assertTrue(SearchQuery("has:tags").matches(bm))

    def test_timezone_date_filter_is_applied(self):
        bm = Bookmark(
            id=1,
            url="https://example.com",
            title="Example",
            created_at="2024-01-02T00:00:00",
        )
        self.assertTrue(SearchQuery("after:2024-01-01T00:00:00Z").matches(bm))
        self.assertFalse(SearchQuery("after:2024-01-03T00:00:00Z").matches(bm))

    def test_long_regex_query_is_ignored(self):
        q = SearchQuery(f"/{'a' * 251}/")
        self.assertFalse(q.is_regex)

    def test_empty_typed_filters_do_not_match_everything(self):
        bm = Bookmark(id=1, url="https://example.com", title="Hello")
        q = SearchQuery("cat: tag: domain: #")

        self.assertEqual(q.category_filters, [])
        self.assertEqual(q.tag_filters, [])
        self.assertEqual(q.domain_filters, [])
        self.assertTrue(q.matches(bm))

    def test_search_query_accepts_none_and_ignores_negative_visits(self):
        self.assertEqual(SearchQuery(None).text_terms, [])
        q = SearchQuery("visits:-1")
        self.assertIsNone(q.min_visits)

    def test_no_match(self):
        bm = Bookmark(id=1, url="https://example.com", title="Hello")
        q = SearchQuery("nonexistent")
        self.assertFalse(q.matches(bm))

    def test_search_engine_accepts_none_query(self):
        bm = Bookmark(id=1, url="https://example.com", title="Hello")
        results = SearchEngine().search([bm], None)
        self.assertEqual(results, [])

    def test_search_helpers_normalize_bad_inputs(self):
        from bookmark_organizer_pro.search import FuzzySearchEngine

        bm = Bookmark(id=1, url="https://example.com", title="Hello World", tags=["docs"])
        engine = SearchEngine()
        engine.save_search("", "ignored")
        engine.save_search(" Docs ", " tag:docs ")
        self.assertEqual(engine.get_saved_searches(), {"Docs": "tag:docs"})

        self.assertEqual(fuzzy_match(None, None, threshold="bad"), (False, 0.0))
        suggestions = FuzzySearchEngine().get_suggestions(None, [bm], limit="bad")
        self.assertIn("Hello", suggestions)

    def test_boolean_and_negative_text_terms(self):
        react = Bookmark(id=1, url="https://example.com/react", title="React guide")
        vue = Bookmark(id=2, url="https://example.com/vue", title="Vue guide")
        deprecated = Bookmark(
            id=3,
            url="https://example.com/python",
            title="Python tutorial",
            notes="deprecated",
        )

        self.assertTrue(SearchQuery("react OR vue").matches(react))
        self.assertTrue(SearchQuery("react OR vue").matches(vue))
        self.assertFalse(SearchQuery("react OR vue").matches(deprecated))
        self.assertTrue(SearchQuery("python AND tutorial").matches(deprecated))
        self.assertFalse(SearchQuery("python -deprecated").matches(deprecated))


class TestValidators(unittest.TestCase):
    """Test URL/path validators against platform and malformed-input edge cases."""

    def test_validate_url_rejects_whitespace_and_missing_host(self):
        self.assertFalse(validate_url("https://exa mple.com")[0])
        self.assertFalse(validate_url("https:///missing-host")[0])
        self.assertTrue(validate_url("https://example.com/path")[0])
        self.assertTrue(validate_url("file:///C:/tmp/bookmarks.html")[0])

    def test_validate_url_rejects_bad_ports_and_malformed_hosts(self):
        self.assertFalse(validate_url("https://example.com:99999/path")[0])
        self.assertFalse(validate_url("https://bad_host.example/path")[0])
        self.assertFalse(validate_url("https://-bad.example/path")[0])
        self.assertTrue(validate_url("https://[2001:db8::1]/docs")[0])

    def test_validate_path_allows_windows_drive_and_rejects_bad_segments(self):
        if IS_WINDOWS:
            self.assertTrue(validate_path(r"C:\Temp\bookmarks.json")[0])
            self.assertFalse(validate_path(r"C:\Temp\bad:name.json")[0])
            self.assertFalse(validate_path(r"C:\Temp\CON.txt")[0])
        else:
            self.assertTrue(validate_path("/tmp/bookmarks.json")[0])
        self.assertFalse(validate_path("bad\x00name")[0])


class TestRuntimeHelpers(unittest.TestCase):
    """Test generic utility helpers used by the GUI and managers."""

    def test_run_with_timeout_returns_without_waiting_for_slow_function(self):
        blocker = threading.Event()
        started = time.perf_counter()
        result = run_with_timeout(lambda: (blocker.wait(2.0), "done")[1], 0.05, default="timeout")
        elapsed = time.perf_counter() - started

        self.assertEqual(result, "timeout")
        self.assertLess(elapsed, 0.25)

    def test_truncate_string_respects_tiny_limits(self):
        self.assertEqual(truncate_string("abcdef", 2), "..")
        self.assertEqual(truncate_string("abcdef", 0), "")


class TestHealthHelpers(unittest.TestCase):
    """Test health scoring and duplicate merge edge cases."""

    def test_health_score_handles_missing_or_corrupt_attributes(self):
        class PartialBookmark:
            url = "https://example.com"
            title = "Example"
            tags = "one,two"
            http_status = "bad"
            category = "Research"

            @property
            def is_stale(self):
                raise RuntimeError("stale check failed")

        self.assertEqual(calculate_health_score(None), 0)
        self.assertGreaterEqual(calculate_health_score(PartialBookmark()), 0)

    def test_merge_duplicate_bookmarks_sanitizes_dict_inputs(self):
        merged = merge_duplicate_bookmarks([
            {
                "url": "https://example.com",
                "title": "https://example.com",
                "tags": "AI,ai,Tools",
                "ai_tags": ["Research", "research"],
                "visit_count": "4",
                "custom_data": ["bad"],
            },
            {
                "url": "https://example.com",
                "title": "A much better title",
                "tags": ["tools", "Docs"],
                "visit_count": "not-a-number",
                "description": 12345,
                "modified_at": "2024-01-01T00:00:00",
                "category": "Research",
            },
        ])

        self.assertEqual(merged["title"], "A much better title")
        self.assertEqual(merged["tags"], ["AI", "Tools", "Docs"])
        self.assertEqual(merged["ai_tags"], ["Research"])
        self.assertEqual(merged["visit_count"], 4)
        self.assertEqual(merged["custom_data"], {})


class TestDependencyManager(unittest.TestCase):
    """Test runtime dependency discovery and install guardrails."""

    def test_frozen_runtime_detects_pyinstaller_bundle_marker(self):
        with (
            patch.object(sys, "frozen", False, create=True),
            patch.object(sys, "_MEIPASS", "bundle-root", create=True),
        ):
            self.assertTrue(is_frozen_runtime())

    def test_check_all_reports_required_and_optional_packages(self):
        manager = DependencyManager()
        manager.REQUIRED_PACKAGES = {
            "required-ok": {"import_name": "ok_mod", "required": True, "description": "ok"},
            "required-missing": {"import_name": "missing_mod", "required": True, "description": "missing"},
        }
        manager.OPTIONAL_PACKAGES = {
            "optional-missing": {"import_name": "optional_mod", "required": False, "description": "optional"},
        }

        with patch.object(manager, "_is_installed", side_effect=lambda name: name == "ok_mod"):
            all_ok, missing_required, missing_optional = manager.check_all()

        self.assertFalse(all_ok)
        self.assertEqual(missing_required, ["required-missing"])
        self.assertEqual(missing_optional, ["optional-missing"])
        self.assertTrue(manager.installed["required-ok"])

    def test_install_package_rejects_unknown_dependencies_without_pip(self):
        manager = DependencyManager()

        with patch("bookmark_organizer_pro.utils.dependencies.subprocess.run") as run_mock:
            self.assertFalse(manager.install_package("not-a-known-package"))
            run_mock.assert_not_called()

        self.assertIn("not-a-known-package", manager.install_errors)

    def test_install_package_in_frozen_runtime_returns_repair_guidance_without_pip(self):
        manager = DependencyManager()
        progress = []

        with (
            patch("bookmark_organizer_pro.utils.dependencies.is_frozen_runtime", return_value=True),
            patch("bookmark_organizer_pro.utils.dependencies.subprocess.run") as run_mock,
        ):
            self.assertFalse(manager.install_package("Pillow", progress.append))

        run_mock.assert_not_called()
        self.assertEqual(progress, [manager.install_errors["Pillow"]])
        self.assertEqual(
            manager.install_errors["Pillow"],
            "Missing packaged component: Pillow. This packaged build cannot install Python "
            "components at runtime. Reinstall Bookmark Organizer Pro from the complete release package.",
        )

    def test_install_package_source_runtime_retains_pip_path(self):
        manager = DependencyManager()
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        with (
            patch("bookmark_organizer_pro.utils.dependencies.is_frozen_runtime", return_value=False),
            patch("bookmark_organizer_pro.utils.dependencies.subprocess.run", return_value=completed) as run_mock,
        ):
            self.assertTrue(manager.install_package("Pillow"))

        run_mock.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "Pillow", "--quiet"],
            capture_output=True,
            text=True,
            timeout=120,
        )


class TestMainAppManagers(unittest.TestCase):
    """Regression tests for main.py manager behavior that the GUI/CLI rely on."""

    def _make_manager(self, tmp: str):
        import main

        root = Path(tmp)
        category_manager = CategoryManager(filepath=root / "categories.json")
        tag_manager = main.TagManager(filepath=root / "tags.json")
        return main.BookmarkManager(
            category_manager,
            tag_manager,
            filepath=root / "bookmarks.json",
        )

    def test_bookmark_manager_regenerates_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            first = Bookmark(id=7, url="https://one.example", title="One")
            second = Bookmark(id=7, url="https://two.example", title="Two")

            manager.add_bookmark(first, save=False)
            manager.add_bookmark(second, save=False)

            self.assertEqual(len(manager.bookmarks), 2)
            self.assertEqual(len(set(manager.bookmarks.keys())), 2)
            self.assertIn(7, manager.bookmarks)
            self.assertNotEqual(second.id, 7)

    def test_statistics_use_one_consistent_bookmark_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(
                Bookmark(
                    id=1,
                    url="https://example.com/page?utm_source=one",
                    title="First",
                    tags=["Research"],
                    notes="Note",
                    is_pinned=True,
                ),
                save=False,
            )
            manager.add_bookmark(
                Bookmark(
                    id=2,
                    url="https://example.com/page",
                    title="Duplicate",
                    tags=["Research", "Later"],
                    is_archived=True,
                    is_valid=False,
                ),
                save=False,
            )

            with patch.object(manager, "_iter_snapshot", wraps=manager._iter_snapshot) as snapshot:
                stats = manager.get_statistics()

            snapshot.assert_called_once_with()
            self.assertEqual(stats["total_bookmarks"], 2)
            self.assertEqual(stats["tag_counts"], {"Research": 2, "Later": 1})
            self.assertEqual(stats["top_domains"], [("example.com", 2)])
            self.assertEqual(stats["duplicate_groups"], 1)
            self.assertEqual(stats["duplicate_bookmarks"], 1)
            self.assertEqual(stats["pinned"], 1)
            self.assertEqual(stats["archived"], 1)
            self.assertEqual(stats["broken"], 1)
            self.assertEqual(stats["with_notes"], 1)
            self.assertEqual(stats["with_tags"], 2)

    def test_import_json_uses_canonical_duplicate_detection_without_id_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(
                Bookmark(id=1, url="https://example.com/page?utm_source=x", title="Existing"),
                save=False,
            )
            import_file = Path(tmp) / "import.json"
            import_file.write_text(
                json.dumps({
                    "bookmarks": [
                        {"id": 1, "url": "https://example.com/page", "title": "Duplicate"},
                        {"id": 1, "url": "https://other.example", "title": "Other"},
                    ]
                }),
                encoding="utf-8",
            )

            added, duplicates = manager.import_json_file(str(import_file))

            self.assertEqual(added, 1)
            self.assertEqual(duplicates, 1)
            self.assertEqual(manager.bookmarks[1].title, "Existing")
            self.assertEqual(len(manager.bookmarks), 2)

    def test_import_json_rejects_unsupported_url_schemes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            import_file = Path(tmp) / "import.json"
            import_file.write_text(
                json.dumps({
                    "bookmarks": [
                        {"id": 1, "url": "javascript:alert(1)", "title": "Bad"},
                        {"id": 2, "url": "https://safe.example", "title": "Good"},
                    ]
                }),
                encoding="utf-8",
            )

            added, duplicates = manager.import_json_file(str(import_file))

            self.assertEqual(added, 1)
            self.assertEqual(duplicates, 0)
            self.assertEqual([bm.url for bm in manager.bookmarks.values()], ["https://safe.example"])

    def test_import_json_skips_non_string_url_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            import_file = Path(tmp) / "import.json"
            import_file.write_text(
                json.dumps({
                    "bookmarks": [
                        {"id": 1, "url": None, "title": "None"},
                        {"id": 2, "url": 123, "title": "Number"},
                        {"id": 3, "url": "https://safe.example", "title": "Good"},
                    ]
                }),
                encoding="utf-8",
            )

            added, duplicates = manager.import_json_file(str(import_file))

            self.assertEqual(added, 1)
            self.assertEqual(duplicates, 0)
            self.assertEqual([bm.title for bm in manager.bookmarks.values()], ["Good"])

    def test_import_html_skips_malformed_http_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            html_path = Path(tmp) / "bookmarks.html"
            html_path.write_text(
                """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
  <DT><A HREF="http:///missing-host">Bad</A>
  <DT><A HREF="https://safe.example/path">Good</A>
</DL><p>
""",
                encoding="utf-8",
            )

            added, duplicates = manager.import_html_file(str(html_path))

            self.assertEqual((added, duplicates), (1, 0))
            self.assertEqual([bm.url for bm in manager.bookmarks.values()], ["https://safe.example/path"])

    def test_tag_manager_ignores_corrupt_empty_tags_on_load(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.json"
            path.write_text(json.dumps({"tags": [{"name": ""}, {"name": "Useful"}]}), encoding="utf-8")
            manager = main.TagManager(filepath=path)

            self.assertEqual([tag.name for tag in manager.get_all_tags()], ["Useful"])

    def test_smart_tag_manager_persists_and_blocks_empty_match_all_rules(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            original_file = main.SmartTagManager.RULES_FILE
            try:
                main.SmartTagManager.RULES_FILE = Path(tmp) / "smart_rules.json"
                manager = main.SmartTagManager()
                bookmark = Bookmark(id=1, url="https://example.com", title="Example")

                match_all = main.SmartTagRule(
                    name="Empty Value",
                    tag="bad",
                    conditions=[{"field": "title", "operator": "contains", "value": ""}],
                )
                self.assertFalse(match_all.matches(bookmark))

                manager.add_rule(main.SmartTagRule(
                    name="Example",
                    tag="Example",
                    conditions=[{"field": "domain", "operator": "equals", "value": "example.com"}],
                ))
                bookmark.tags = ["example"]
                self.assertEqual(manager.apply_rules(bookmark), [])
                self.assertTrue(main.SmartTagManager.RULES_FILE.exists())
            finally:
                main.SmartTagManager.RULES_FILE = original_file

    def test_collection_manager_sanitizes_load_and_uses_unique_ids(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            original_file = main.CollectionManager.COLLECTIONS_FILE
            try:
                main.CollectionManager.COLLECTIONS_FILE = Path(tmp) / "collections.json"
                main.CollectionManager.COLLECTIONS_FILE.write_text(
                    json.dumps([
                        {"id": "bad", "name": ""},
                        {"id": "ok", "name": "Keep", "bookmark_ids": ["1", "bad", 1]},
                    ]),
                    encoding="utf-8",
                )
                manager = main.CollectionManager()
                self.assertEqual(list(manager.collections), ["ok"])
                self.assertEqual(manager.collections["ok"].bookmark_ids, [1])

                first = manager.create_collection("New")
                second = manager.create_collection("New")
                self.assertNotEqual(first.id, second.id)
            finally:
                main.CollectionManager.COLLECTIONS_FILE = original_file

    def test_settings_profiles_history_colors_and_fonts_are_defensive(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            originals = (
                main.SettingsProfileManager.PROFILES_FILE,
                main.VersionHistory.HISTORY_FILE,
                main.CategoryColorManager.COLORS_FILE,
                main.FontManager.FONTS_FILE,
            )
            try:
                main.SettingsProfileManager.PROFILES_FILE = base / "profiles.json"
                profile_manager = main.SettingsProfileManager()
                profile = profile_manager.save_profile(" Work ", {"theme": "light"}, "Desk")
                export_path = base / "exports" / "profile.json"
                profile_manager.export_profile(profile.name, str(export_path))
                self.assertTrue(export_path.exists())
                self.assertEqual(profile_manager.import_profile(str(export_path)).name, "Work")

                main.VersionHistory.HISTORY_FILE = base / "history.json"
                history = main.VersionHistory()
                history.record_bulk_change("tag", ["1", "bad"], "Tagged")
                self.assertEqual(history.get_history(99)[0]["bookmark_ids"], [1])
                history.versions.append({"bookmark_ids": None})
                self.assertEqual(len(history.get_bookmark_history(1)), 1)

                main.CategoryColorManager.COLORS_FILE = base / "colors.json"
                color_manager = main.CategoryColorManager()
                color_manager.set_color("Dev", "not-a-color")
                color_manager.set_color("Dev", "#123abc")
                self.assertEqual(color_manager.get_color("Dev"), "#123abc")

                main.FontManager.FONTS_FILE = base / "fonts.json"
                main.FontManager.FONTS_FILE.write_text(
                    json.dumps({"ui_size": 999, "mono_size": "bad"}),
                    encoding="utf-8",
                )
                font_manager = main.FontManager()
                self.assertEqual(font_manager.settings["ui_size"], 32)
                self.assertEqual(font_manager.settings["mono_size"], 10)
            finally:
                (
                    main.SettingsProfileManager.PROFILES_FILE,
                    main.VersionHistory.HISTORY_FILE,
                    main.CategoryColorManager.COLORS_FILE,
                    main.FontManager.FONTS_FILE,
                ) = originals

    def test_local_archiver_delete_is_confined_to_archive_directory(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            original_dir = main.LocalArchiver.ARCHIVE_DIR
            try:
                main.LocalArchiver.ARCHIVE_DIR = Path(tmp) / "archives"
                archiver = main.LocalArchiver()

                outside = Path(tmp) / "outside.html"
                outside.write_text("keep", encoding="utf-8")
                inside = main.LocalArchiver.ARCHIVE_DIR / "inside.html"
                inside.write_text("delete", encoding="utf-8")

                self.assertFalse(archiver.delete_archive(str(outside)))
                self.assertTrue(outside.exists())
                self.assertTrue(archiver.delete_archive(str(inside)))
                self.assertFalse(inside.exists())
            finally:
                main.LocalArchiver.ARCHIVE_DIR = original_dir

    def test_screenshot_cache_deletion_rejects_invalid_ids(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            original_dir = main.ScreenshotCapture.SCREENSHOT_DIR
            try:
                main.ScreenshotCapture.SCREENSHOT_DIR = Path(tmp) / "screens"
                capture = main.ScreenshotCapture()
                screenshot = main.ScreenshotCapture.SCREENSHOT_DIR / "screenshot_1.png"
                screenshot.write_bytes(b"png")

                self.assertFalse(capture.delete_screenshot("../1"))
                self.assertTrue(screenshot.exists())
                self.assertFalse(capture.delete_screenshot(-1))
                self.assertTrue(capture.delete_screenshot(1))
                self.assertFalse(screenshot.exists())
            finally:
                main.ScreenshotCapture.SCREENSHOT_DIR = original_dir

    def test_bookmark_manager_html_export_escapes_attributes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            bookmark = Bookmark(
                id=1,
                url='https://example.com/?q="x"',
                title="<Title>",
                add_date='1" onmouseover="x',
                icon='https://icons.example/icon.png?name="bad"',
                tags=['a"b'],
            )
            manager.add_bookmark(bookmark, save=False)
            export_path = Path(tmp) / "nested" / "bookmarks.html"

            manager.export_html(str(export_path))
            output = export_path.read_text(encoding="utf-8")

            self.assertIn('HREF="https://example.com/?q=&quot;x&quot;"', output)
            self.assertIn('ADD_DATE="1&quot; onmouseover=&quot;x"', output)
            self.assertIn('ICON="https://icons.example/icon.png?name=&quot;bad&quot;"', output)
            self.assertIn('TAGS="a&quot;b"', output)
            self.assertIn("&lt;Title&gt;", output)

    def test_plain_exports_create_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(
                Bookmark(id=1, url="https://example.com", title="Example", tags=["tag"]),
                save=False,
            )
            targets = [
                Path(tmp) / "csv" / "bookmarks.csv",
                Path(tmp) / "md" / "bookmarks.md",
                Path(tmp) / "txt" / "bookmarks.txt",
                Path(tmp) / "urls" / "bookmarks.txt",
            ]

            manager.export_csv(str(targets[0]))
            manager.export_markdown(str(targets[1]))
            manager.export_txt(str(targets[2]))
            manager.export_urls_only(str(targets[3]))

            for target in targets:
                self.assertTrue(target.exists(), target)

    def test_full_markdown_export_escapes_user_fields(self):
        from bookmark_organizer_pro.services.extraction_templates import STRUCTURED_METADATA_KEY

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(
                Bookmark(
                    id=1,
                    url="https://example.com/a_(b)",
                    title="A [Title] `x`",
                    category="Cat #1",
                    tags=["tag`x`"],
                    notes="Line (one)\nLine [two]",
                    custom_data={
                        STRUCTURED_METADATA_KEY: {
                            "schema_version": 1,
                            "template": "Docs",
                            "fields": {"heading": "Install [Guide]", "topics": ["alpha", "beta"]},
                        },
                    },
                ),
                save=False,
            )
            output = Path(tmp) / "nested" / "bookmarks.md"

            manager.export_markdown(str(output))
            text = output.read_text(encoding="utf-8")

            self.assertIn("## Cat \\#1", text)
            self.assertIn("- [A \\[Title\\] \\`x\\`](https://example.com/a_\\(b\\))", text)
            self.assertIn("`tag\\`x\\``", text)
            self.assertIn("> Line (one)", text)
            self.assertIn("> Line \\[two\\]", text)
            self.assertIn("Structured metadata (Docs)", text)
            self.assertIn("heading: Install \\[Guide\\]", text)
            self.assertIn("topics: alpha, beta", text)

    def test_pdf_export_escapes_bookmark_fields(self):
        import main

        captured = {}

        class FakeHTML:
            def __init__(self, string, base_url=None):
                captured["html"] = string
                captured["base_url"] = base_url

            def write_pdf(self, path):
                Path(path).write_bytes(b"%PDF")

        old_weasyprint = sys.modules.get("weasyprint")
        had_weasyprint = "weasyprint" in sys.modules
        try:
            sys.modules["weasyprint"] = type("FakeWeasyPrint", (), {"HTML": FakeHTML})
            with tempfile.TemporaryDirectory() as tmp:
                exporter = main.PDFExporter()
                output_path = Path(tmp) / "nested" / "bookmarks.pdf"
                bookmark = Bookmark(
                    id=1,
                    url='https://example.com/path?a=1&b="x"',
                    title="<script>alert(1)</script>",
                    category="<Cat>",
                    tags=["a<b", 'x"y'],
                )

                self.assertTrue(exporter.export_bookmarks_pdf([bookmark], str(output_path)))
                html = captured["html"]

                self.assertTrue(output_path.exists())
                self.assertNotIn("<script>alert", html)
                self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
                self.assertIn('href="https://example.com/path?a=1&amp;b=&quot;x&quot;"', html)
                self.assertIn("&lt;Cat&gt;", html)
                self.assertIn("#a&lt;b", html)
                self.assertIn("#x&quot;y", html)
        finally:
            if had_weasyprint:
                sys.modules["weasyprint"] = old_weasyprint
            else:
                sys.modules.pop("weasyprint", None)

    def test_selected_exports_create_parents_and_escape_markdown(self):
        import main

        class FakeVar:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            bookmark = Bookmark(
                id=1,
                url="https://example.com/a(b)",
                title="Title [A](bad)",
                category="Cat [x]",
                notes="Line (one)\nLine two",
                tags=["tag`x`"],
            )
            manager.category_manager.add_category("Cat [x]")

            dialog = main.SelectiveExportDialog.__new__(main.SelectiveExportDialog)
            dialog.bookmark_manager = manager
            dialog.include_tags_var = FakeVar(True)
            dialog.include_notes_var = FakeVar(True)
            dialog.include_metadata_var = FakeVar(True)

            json_path = Path(tmp) / "selected" / "bookmarks.json"
            csv_path = Path(tmp) / "selected" / "bookmarks.csv"
            md_path = Path(tmp) / "selected" / "bookmarks.md"

            dialog._export_selected_json([bookmark], str(json_path))
            dialog._export_selected_csv([bookmark], str(csv_path))
            dialog._export_selected_markdown([bookmark], str(md_path))

            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            markdown = md_path.read_text(encoding="utf-8")
            self.assertIn("## Cat \\[x\\]", markdown)
            self.assertIn("- [Title \\[A\\]\\(bad\\)](https://example.com/a%28b%29)", markdown)
            self.assertIn("`tag\\`x\\``", markdown)
            self.assertIn("> Line \\(one\\)", markdown)

    def test_local_archiver_persists_archive_path_and_closes_response(self):
        import main

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/html", "content-length": "41"}
            encoding = "utf-8"

            def __init__(self):
                self.closed = False

            def iter_content(self, chunk_size=16384):
                yield b"<main>Archived page body with enough text</main>"

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as tmp:
            original_dir = main.LocalArchiver.ARCHIVE_DIR
            response = FakeResponse()
            try:
                main.LocalArchiver.ARCHIVE_DIR = Path(tmp) / "nested" / "archives"
                bookmark = Bookmark(id=1, url="https://example.com", title="Example/Page")
                archiver = main.LocalArchiver()

                class FakeRequests:
                    def get(self, *args, **kwargs):
                        return response

                with patch("bookmark_organizer_pro.services.web_tools.URLUtilities._is_safe_url", return_value=True), \
                        patch("bookmark_organizer_pro.services.web_tools.requests", FakeRequests()):
                    ok, archive_path = archiver.archive_page(bookmark, "HTML")

                self.assertTrue(ok)
                self.assertTrue(response.closed)
                self.assertTrue(Path(archive_path).exists())
                self.assertEqual(bookmark.custom_data["local_archive_path"], archive_path)
                self.assertEqual(archiver.get_archive_size()[0], 1)
                self.assertEqual(archiver.get_archived_pages()[0]["path"], archive_path)
            finally:
                main.LocalArchiver.ARCHIVE_DIR = original_dir

    def test_local_archiver_writes_real_bounded_mhtml_with_embedded_resources(self):
        import email
        import main

        class FakeResponse:
            status_code = 200
            encoding = "utf-8"

            def __init__(self, body: bytes, content_type: str):
                self.body = body
                self.headers = {
                    "content-type": content_type,
                    "content-length": str(len(body)),
                }
                self.closed = False

            def iter_content(self, chunk_size=16384):
                yield self.body

            def close(self):
                self.closed = True

        responses = {
            "https://example.com/page": FakeResponse(
                b'<html><head><link rel="stylesheet" href="/site.css"></head>'
                b'<body><script>alert(1)</script><img src="/hero.png"></body></html>',
                "text/html",
            ),
            "https://example.com/site.css": FakeResponse(
                b"@font-face{src:url('/font.woff2')} body{color:#123}",
                "text/css",
            ),
            "https://example.com/hero.png": FakeResponse(b"PNG", "image/png"),
            "https://example.com/font.woff2": FakeResponse(b"FONT", "font/woff2"),
        }

        class FakeRequests:
            def get(self, url, *args, **kwargs):
                return responses[url]

        with tempfile.TemporaryDirectory() as tmp:
            original_dir = main.LocalArchiver.ARCHIVE_DIR
            try:
                main.LocalArchiver.ARCHIVE_DIR = Path(tmp) / "archives"
                bookmark = Bookmark(id=1, url="https://example.com/page", title="Example")
                archiver = main.LocalArchiver()
                with patch("bookmark_organizer_pro.services.web_tools.URLUtilities._is_safe_url", return_value=True), \
                        patch("bookmark_organizer_pro.services.web_tools.requests", FakeRequests()):
                    ok, archive_path = archiver.archive_page(bookmark, "mhtml")

                self.assertTrue(ok, archive_path)
                message = email.message_from_bytes(Path(archive_path).read_bytes())
                self.assertEqual(message.get_content_type(), "multipart/related")
                parts = list(message.walk())
                self.assertEqual(sum(part.get_content_type() == "text/html" for part in parts), 1)
                self.assertIn("text/css", [part.get_content_type() for part in parts])
                self.assertIn("image/png", [part.get_content_type() for part in parts])
                self.assertIn("font/woff2", [part.get_content_type() for part in parts])
                html_part = next(part for part in parts if part.get_content_type() == "text/html")
                html_payload = html_part.get_payload(decode=True).decode("utf-8")
                self.assertNotIn("<script", html_payload)
                self.assertIn("cid:resource-", html_payload)
                self.assertTrue(all(response.closed for response in responses.values()))
            finally:
                main.LocalArchiver.ARCHIVE_DIR = original_dir

    def test_ai_summarizer_closes_rejected_responses(self):
        import main

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "application/octet-stream"}
            encoding = "utf-8"

            def __init__(self):
                self.closed = False

            def iter_content(self, chunk_size=8192):
                yield b"not html"

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as tmp:
            response = FakeResponse()
            summarizer = main.AISummarizer(AIConfigManager(filepath=Path(tmp) / "ai.json"))
            bookmark = Bookmark(id=1, url="https://example.com", title="Example")

            class FakeRequests:
                def get(self, *args, **kwargs):
                    return response

            with patch("bookmark_organizer_pro.services.web_tools.URLUtilities._is_safe_url", return_value=True), \
                    patch("bookmark_organizer_pro.services.web_tools.requests", FakeRequests()):
                self.assertIsNone(summarizer.summarize_page(bookmark))

            self.assertTrue(response.closed)

    def test_bookmark_api_rejects_bad_post_bodies_and_duplicates(self):
        import urllib.error
        import urllib.request
        import main

        def post_json(base_url, payload, token=None):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            request = urllib.request.Request(
                f"{base_url}/bookmarks",
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read().decode("utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                base_url = f"http://127.0.0.1:{api.port}"

                from bookmark_organizer_pro.services.api import _TOKEN_FILE, _KEYRING_SERVICE, _KEYRING_KEY
                token = ""
                if _TOKEN_FILE.exists():
                    token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
                if not token:
                    try:
                        import keyring
                        token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY) or ""
                    except Exception:
                        pass

                status, body = post_json(base_url, {"url": "https://unauthorized.example"})
                self.assertEqual(status, 401)
                self.assertIn("Unauthorized", body["error"])

                status, body = post_json(base_url, "not an object", token=token)
                self.assertEqual(status, 400)
                self.assertIn("object", body["error"])

                status, body = post_json(base_url, {"url": "ftp://example.com/file"}, token=token)
                self.assertEqual(status, 400)
                self.assertIn("http", body["error"])

                status, body = post_json(base_url, {
                    "url": "https://example.com/path?utm_source=x",
                    "title": "Example",
                    "category": "Research",
                    "tags": "AI, ai, tools",
                    "notes": "Captured from extension",
                    "read_later": True,
                }, token=token)
                self.assertEqual(status, 201)
                self.assertEqual(body["title"], "Example")
                self.assertEqual(body["category"], "Research")
                self.assertEqual(body["tags"], ["AI", "tools"])
                self.assertEqual(body["notes"], "Captured from extension")
                self.assertTrue(body["read_later"])
                self.assertEqual(body["read_later_position"], 0)
                self.assertEqual(len(manager.bookmarks), 1)
                created = next(iter(manager.bookmarks.values()))
                self.assertTrue(created.read_later)
                self.assertEqual(created.read_later_position, 0)

                status, body = post_json(base_url, {"url": "https://example.com/path"}, token=token)
                self.assertEqual(status, 409)
                self.assertIn("exists", body["error"])
            finally:
                api.stop()

    def test_bookmark_api_serves_opds_catalog(self):
        import urllib.error
        import urllib.request
        import main

        def get_text(url, token=None):
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return response.status, response.read().decode("utf-8"), response.headers
            except urllib.error.HTTPError as error:
                return error.code, error.read().decode("utf-8"), error.headers

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(Bookmark(
                id=1,
                url="https://example.com/book.pdf",
                title="API Book",
                category="Books",
                tags=["OPDS"],
            ), save=False)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                url = f"http://127.0.0.1:{api.port}/opds?tag=OPDS&title=Catalog"
                from bookmark_organizer_pro.services.api import _TOKEN_FILE, _KEYRING_SERVICE, _KEYRING_KEY
                token = ""
                if _TOKEN_FILE.exists():
                    token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
                if not token:
                    try:
                        import keyring
                        token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY) or ""
                    except Exception:
                        pass

                status, body, _ = get_text(url)
                self.assertEqual(status, 401)
                self.assertIn("Unauthorized", body)

                status, body, headers = get_text(url, token)
                self.assertEqual(status, 200)
                content_type = headers.get("Content-Type", "")
                self.assertIn("opds-catalog", content_type)
                self.assertIn("API Book", body)
                self.assertIn("application/pdf", body)
                self.assertIn("http://opds-spec.org/acquisition/open-access", body)

                status, body, _ = get_text(f"http://127.0.0.1:{api.port}/opds2?tag=OPDS", token)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["metadata"]["title"], "Bookmarks")

                status, body, _ = get_text(f"http://127.0.0.1:{api.port}/opds2?tag=OPDS")
                self.assertEqual(status, 401)
                self.assertIn("Unauthorized", body)
            finally:
                api.stop()

    def test_batch_refresh_and_tag_merge_are_defensive(self):

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            bookmark = Bookmark(
                id=1,
                url="https://example.com",
                title="https://example.com",
                tags=["AI", "tools"],
            )
            manager.add_bookmark(bookmark, save=False)

            with patch("bookmark_organizer_pro.managers.bookmarks.fetch_page_metadata", return_value={
                "title": "Example Title",
                "description": "Description",
                "favicon_url": "https://example.com/favicon.ico",
            }):
                updated = manager.batch_refresh_metadata(
                    bookmark_ids=["1", "bad"],
                    max_workers="bad",
                    progress_callback=lambda *_: (_ for _ in ()).throw(RuntimeError("ignore")),
                )

            self.assertEqual(updated, 1)
            self.assertEqual(bookmark.title, "Example Title")
            self.assertEqual(bookmark.description, "Description")

            self.assertEqual(manager.merge_tags(" ai ", "ML"), 1)
            self.assertEqual(bookmark.tags, ["tools", "ML"])
            self.assertEqual(manager.merge_tags("ml", "ML"), 0)

    def test_tag_suggestions_tolerate_empty_query_and_bad_limit(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = main.TagManager(filepath=Path(tmp) / "tags.json")
            manager.add_tag("Alpha")
            manager.add_tag("Beta")

            self.assertEqual(manager.get_tag_suggestions(None, limit="bad"), ["Alpha", "Beta"])

    def test_command_stack_add_undo_preserves_existing_id_collisions(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            existing = Bookmark(id=7, url="https://existing.example", title="Existing")
            incoming = Bookmark(id=7, url="https://incoming.example", title="Incoming")
            manager.add_bookmark(existing, save=False)

            stack = main.CommandStack(max_history="bad")
            stack.execute(main.AddBookmarksCommand(manager, [incoming]))

            self.assertEqual(len(manager.bookmarks), 2)
            self.assertIn(7, manager.bookmarks)
            self.assertNotEqual(incoming.id, 7)

            stack.undo()

            self.assertEqual(list(manager.bookmarks), [7])
            self.assertEqual(manager.bookmarks[7].url, "https://existing.example")

    def test_tag_command_normalizes_ids_and_tags_for_undo(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            bookmark = Bookmark(id=1, url="https://example.com", title="Example", tags=["AI", "tools"])
            manager.add_bookmark(bookmark, save=False)

            command = main.TagBookmarksCommand(
                manager,
                bookmark_ids=["1", "bad", "1"],
                add_tags=[" ml ", "ML", ""],
                remove_tags=["ai"],
            )
            command.execute()

            self.assertEqual(bookmark.tags, ["tools", "ml"])

            command.undo()

            self.assertEqual(bookmark.tags, ["AI", "tools"])

    def test_backup_cleanup_ignores_unreadable_entries(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            scheduler = main.BackupScheduler(manager)
            scheduler.config["backup_location"] = tmp
            scheduler.config["max_backups"] = 1
            newest = Path(tmp) / "bookmark_backup_new.json"
            oldest = Path(tmp) / "bookmark_backup_old.json"
            newest.write_text("{}", encoding="utf-8")
            oldest.write_text("{}", encoding="utf-8")
            os.utime(oldest, (1, 1))
            os.utime(newest, (2, 2))

            original_glob = Path.glob

            class VanishingPath:
                name = "bookmark_backup_missing.json"

                def stat(self):
                    raise OSError("gone")

                def __str__(self):
                    return self.name

            def fake_glob(self, pattern):
                if self == Path(tmp) and pattern == "bookmark_backup_*.json":
                    return iter([newest, VanishingPath(), oldest])
                return original_glob(self, pattern)

            with patch.object(Path, "glob", fake_glob):
                scheduler._cleanup_old_backups()

            remaining = sorted(path.name for path in Path(tmp).glob("bookmark_backup_*.json"))
            self.assertEqual(remaining, ["bookmark_backup_new.json"])

    def test_csv_safe_cell_prefixes_spreadsheet_formulas(self):
        import main

        self.assertEqual(main._csv_safe_cell("=IMPORTXML('http://x')"), "'=IMPORTXML('http://x')")
        self.assertEqual(main._csv_safe_cell("@SUM(1,2)"), "'@SUM(1,2)")
        self.assertEqual(main._csv_safe_cell("plain title"), "plain title")

    def test_open_external_url_blocks_invalid_schemes_before_browser(self):
        import main

        with patch("main.webbrowser.open") as open_mock:
            self.assertFalse(main._open_external_url("javascript:alert(1)"))
            open_mock.assert_not_called()

    def test_bookmark_manager_id_and_query_helpers_are_defensive(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            bookmark = Bookmark(id=12, url="https://example.com", title="Example", tags=["AI"])
            manager.add_bookmark(bookmark, save=False)

            self.assertIs(manager.get_bookmark("12"), bookmark)
            self.assertIsNone(manager.get_bookmark(["bad"]))
            self.assertEqual(manager.get_bookmarks_by_tag(None), [])
            self.assertEqual(manager.get_recent_bookmarks(days="bad"), [bookmark])
            self.assertEqual(manager.get_frequently_visited(limit="bad"), [])
            self.assertFalse(manager.delete_bookmark(["bad"]))

    def test_ai_cost_tracker_sanitizes_corrupt_usage_file(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            old_file = main.AICostTracker.COST_FILE
            main.AICostTracker.COST_FILE = Path(tmp) / "ai_costs.json"
            try:
                main.AICostTracker.COST_FILE.write_text(
                    json.dumps({
                        "2026-04": {
                            "openai/gpt-4": {
                                "input_tokens": "10",
                                "output_tokens": -5,
                                "calls": "bad",
                                "cost": "0.2",
                            },
                            "bad": ["shape"],
                        },
                        "not-a-month": {"x": {"calls": 1}},
                    }),
                    encoding="utf-8",
                )
                tracker = main.AICostTracker()
                summary = tracker.get_monthly_summary("2026-04")
                self.assertEqual(summary["total_input_tokens"], 10)
                self.assertEqual(summary["total_output_tokens"], 0)
                self.assertEqual(summary["total_calls"], 0)
                self.assertEqual(summary["total_cost"], 0.2)

                tracker.record_usage("openai", "gpt-4", "1000", "-10")
                reloaded = json.loads(main.AICostTracker.COST_FILE.read_text(encoding="utf-8"))
                from datetime import datetime
                current_month = datetime.now().strftime("%Y-%m")
                self.assertEqual(reloaded[current_month]["openai/gpt-4"]["calls"], 1)
            finally:
                main.AICostTracker.COST_FILE = old_file

    def test_semantic_duplicate_detector_and_ai_batch_are_defensive(self):
        import main

        detector = main.SemanticDuplicateDetector(ai_config=None)
        self.assertEqual(detector.find_similar(None, threshold="bad"), [])
        self.assertEqual(detector._title_similarity(None, "Example"), 0.0)

        class FakeConfig:
            def get_batch_size(self): return 5
            def get_rate_limit(self): return 30

        class FakeClient:
            def complete(self, prompt, system="", max_tokens=400, temperature=0.3):
                return '{"category": "Research", "confidence": 0.8, "tags": ["AI", "Tools"], "summary": "Summary"}'

        bookmark = Bookmark(id=1, url="https://example.com", title="Example", tags=["AI"])
        events = []
        processor = main.AIBatchProcessor(
            FakeConfig(),
            on_progress=lambda *_: (_ for _ in ()).throw(RuntimeError("progress failed")),
            on_complete=lambda ok, message: events.append((ok, message)),
        )
        processor.add_to_queue([bookmark, object()])

        with patch("bookmark_organizer_pro.services.ai_tools.create_ai_client", return_value=FakeClient()):
            processor.start()
            deadline = time.time() + 5
            while processor.is_running and time.time() < deadline:
                processor._thread.join(timeout=0.1)

        self.assertFalse(processor.is_running)
        self.assertEqual(events, [(True, "Processed 1 bookmarks")])
        self.assertEqual(bookmark.category, "Research")
        self.assertEqual(bookmark.tags, ["AI", "Tools"])
        self.assertEqual(processor.errors, [])


class TestRESTAPIEndpoints(unittest.TestCase):
    """Test REST API endpoints that were previously untested."""

    def _make_manager(self, tmp):
        import main
        return main.BookmarkManager(
            filepath=Path(tmp) / "master_bookmarks.json",
            category_manager=main.CategoryManager(filepath=Path(tmp) / "categories.json"),
            tag_manager=main.TagManager(filepath=Path(tmp) / "tags.json"),
        )

    def _get_json(self, base_url, path, token=None):
        import urllib.request
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(f"{base_url}{path}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def _get_token(self):
        from bookmark_organizer_pro.services.api import _TOKEN_FILE, _KEYRING_SERVICE, _KEYRING_KEY
        token = ""
        if _TOKEN_FILE.exists():
            token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if not token:
            try:
                import keyring
                token = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY) or ""
            except Exception:
                pass
        return token

    def test_api_stats_endpoint(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(Bookmark(id=1, url="https://example.com", title="Test"), save=False)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._get_token()
                status, body = self._get_json(f"http://127.0.0.1:{api.port}", "/stats", token)
                self.assertEqual(status, 200)
                self.assertEqual(body["total_bookmarks"], 1)
            finally:
                api.stop()

    def test_api_categories_endpoint(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(Bookmark(id=1, url="https://example.com", title="Test", category="Dev"), save=False)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._get_token()
                status, body = self._get_json(f"http://127.0.0.1:{api.port}", "/categories", token)
                self.assertEqual(status, 200)
                self.assertIn("categories", body)
            finally:
                api.stop()

    def test_api_tags_endpoint(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(Bookmark(id=1, url="https://example.com", title="Test", tags=["python"]), save=False)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._get_token()
                status, body = self._get_json(f"http://127.0.0.1:{api.port}", "/tags", token)
                self.assertEqual(status, 200)
                self.assertIn("tags", body)
            finally:
                api.stop()

    def test_api_search_endpoint(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(Bookmark(id=1, url="https://python.org", title="Python Docs"), save=False)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._get_token()
                status, body = self._get_json(f"http://127.0.0.1:{api.port}", "/search?q=Python", token)
                self.assertEqual(status, 200)
                self.assertIn("results", body)
                self.assertGreaterEqual(len(body["results"]), 1)
            finally:
                api.stop()

    def test_api_get_single_bookmark(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(Bookmark(id=42, url="https://example.com", title="By ID"), save=False)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._get_token()
                status, body = self._get_json(f"http://127.0.0.1:{api.port}", "/bookmarks/42", token)
                self.assertEqual(status, 200)
                self.assertEqual(body["title"], "By ID")
            finally:
                api.stop()

    def test_api_bookmarks_supports_pagination_and_filter_parity(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            fixtures = [
                Bookmark(
                    id=1,
                    url="https://example.com/old",
                    title="Old",
                    category="Research",
                    tags=["python"],
                    created_at="2024-01-01T00:00:00",
                    read_later=True,
                    read_later_position=2,
                ),
                Bookmark(
                    id=2,
                    url="https://example.com/new-pinned",
                    title="New Pinned",
                    category="Research",
                    tags=["python", "api"],
                    created_at="2024-01-03T00:00:00",
                    read_later=True,
                    read_later_position=1,
                    is_pinned=True,
                ),
                Bookmark(
                    id=3,
                    url="https://example.com/other",
                    title="Other",
                    category="Development",
                    tags=["api"],
                    created_at="2024-01-02T00:00:00",
                ),
            ]
            for bookmark in fixtures:
                manager.add_bookmark(bookmark, save=False)

            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._get_token()
                base = f"http://127.0.0.1:{api.port}"

                status, body = self._get_json(base, "/bookmarks?limit=1&offset=0", token)
                self.assertEqual(status, 200)
                self.assertEqual(body["count"], 3)
                self.assertEqual(body["returned"], 1)
                self.assertEqual(body["next_offset"], 1)
                self.assertTrue(body["has_more"])
                self.assertEqual(body["bookmarks"][0]["title"], "New Pinned")

                status, body = self._get_json(base, "/bookmarks?limit=1&offset=1", token)
                self.assertEqual(status, 200)
                self.assertEqual(body["returned"], 1)
                self.assertEqual(body["next_offset"], 2)
                self.assertEqual(body["bookmarks"][0]["title"], "Other")

                status, body = self._get_json(base, "/bookmarks?tag=python&read_later_only=true", token)
                self.assertEqual(status, 200)
                self.assertEqual(body["count"], 2)
                self.assertEqual([bm["title"] for bm in body["bookmarks"]], ["New Pinned", "Old"])

                status, body = self._get_json(base, "/bookmarks?pinned_only=true", token)
                self.assertEqual(status, 200)
                self.assertEqual(body["count"], 1)
                self.assertFalse(body["has_more"])
                self.assertIsNone(body["next_offset"])
                self.assertEqual(body["bookmarks"][0]["title"], "New Pinned")
            finally:
                api.stop()

    def test_api_digest_endpoint(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            manager.add_bookmark(Bookmark(id=1, url="https://example.com", title="Old One",
                                          created_at="2024-01-01T12:00:00"), save=False)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._get_token()
                status, body = self._get_json(f"http://127.0.0.1:{api.port}", "/digest?count=3", token)
                self.assertEqual(status, 200)
                self.assertIn("sections", body)
                self.assertIn("generated_at", body)
            finally:
                api.stop()

    def test_api_options_returns_cors_headers(self):
        import urllib.request
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                request = urllib.request.Request(
                    f"http://127.0.0.1:{api.port}/bookmarks",
                    method="OPTIONS",
                )
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 204)
                    self.assertIn("Access-Control-Allow-Origin", response.headers)
                    self.assertIn("Access-Control-Allow-Methods", response.headers)
                    self.assertIn("Access-Control-Allow-Headers", response.headers)
            finally:
                api.stop()


class TestUIFoundation(unittest.TestCase):
    """Test toolkit-independent UI formatting and view-model builders."""

    def test_compact_count_and_middle_truncation(self):
        self.assertEqual(format_compact_count(999), "999")
        self.assertEqual(format_compact_count(1200), "1.2K")
        self.assertEqual(format_compact_count(12_345), "12K")
        shortened = truncate_middle("https://example.com/a/very/long/path", 20)
        self.assertTrue(shortened.startswith("https://"))
        self.assertTrue(shortened.endswith("long/path"))
        self.assertIn("…", shortened)

    def test_readable_text_on_picks_contrast(self):
        self.assertEqual(readable_text_on("#07090b"), "#ffffff")
        self.assertEqual(readable_text_on("#2dd4bf"), "#07100f")

    def test_builtin_theme_muted_copy_meets_wcag_aa(self):
        from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES

        failures = {
            name: contrast_ratio(theme.colors.bg_primary, theme.colors.text_muted)
            for name, theme in BUILT_IN_THEMES.items()
            if contrast_ratio(theme.colors.bg_primary, theme.colors.text_muted) < 4.5
        }
        self.assertEqual(failures, {})

    def test_builtin_themes_define_semantic_secondary_accents(self):
        from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES

        for name, theme in BUILT_IN_THEMES.items():
            self.assertTrue(theme.colors.accent_secondary.startswith("#"), name)
            self.assertNotEqual(theme.colors.accent_secondary, ThemeColors().accent_secondary, name)

    def test_filter_counts_view_model(self):
        now = datetime(2026, 4, 19)
        bookmarks = [
            Bookmark(id=1, url="https://a.com", title="A", is_pinned=True,
                     created_at="2026-04-18T00:00:00", tags=["x"]),
            Bookmark(id=2, url="https://b.com", title="B", is_valid=False,
                     created_at="2026-01-01T00:00:00"),
            Bookmark(id=3, url="https://c.com", title="C", ai_tags=["ai"],
                     created_at="2026-01-01T00:00:00"),
        ]
        counts = build_filter_counts(bookmarks, now=now)
        self.assertEqual(counts.as_dict(), {
            "All": 3,
            "Pinned": 1,
            "Recent": 1,
            "Broken": 1,
            "Untagged": 1,
        })

    def test_collection_summary_view_model(self):
        bookmarks = [
            Bookmark(id=1, url="https://a.com", title="A", is_pinned=True),
            Bookmark(id=2, url="https://b.com", title="B", is_valid=False),
        ]
        summary = build_collection_summary(
            visible_count=1,
            total_count=2,
            stats={"pinned": 1, "broken": 1, "total_categories": 4},
            all_bookmarks=bookmarks,
            query="domain:example.com/very/long/search/value",
        )
        self.assertEqual(summary.title, "Search Results")
        self.assertEqual(summary.metrics["visible"], 1)
        self.assertEqual(summary.metrics["pinned"], 1)
        self.assertEqual(summary.metrics["broken"], 1)
        self.assertIn("Showing 1 bookmark", summary.detail)

    def test_collection_summary_tolerates_corrupt_counts(self):
        summary = build_collection_summary(
            visible_count="bad",
            total_count="also-bad",
            stats={"pinned": "nope", "broken": None, "category_counts": {"A": "bad"}},
            all_bookmarks=None,
        )
        self.assertEqual(summary.metrics["visible"], 0)
        self.assertEqual(summary.metrics["pinned"], 0)
        self.assertEqual(summary.metrics["broken"], 0)

    def test_dashboard_statistics_view_model_is_complete_and_defensive(self):
        stats = build_dashboard_statistics({
            "total_bookmarks": "12",
            "pinned": "bad",
            "category_counts": {"Research": "3", "Broken": None},
            "top_domains": [["example.com", "4"], ["", 2], ["invalid"]],
        })

        self.assertEqual(stats.total_bookmarks, 12)
        self.assertEqual(stats.pinned, 0)
        self.assertEqual(stats.duplicate_bookmarks, 0)
        self.assertEqual(stats.category_counts, {"Research": 3, "Broken": 0})
        self.assertEqual(stats.top_domains, (("example.com", 4),))
        self.assertFalse(stats.is_degraded)

    def test_dashboard_statistics_exception_returns_visible_degraded_state(self):
        from bookmark_organizer_pro.ui.widget_dashboard_panel import DashboardPanel

        class FailingManager:
            def get_statistics(self):
                raise RuntimeError("database unavailable")

        panel = object.__new__(DashboardPanel)
        panel.manager = FailingManager()
        stats = panel._load_statistics()

        self.assertTrue(stats.is_degraded)
        self.assertIn("temporarily unavailable", stats.degraded_message)
        self.assertEqual(stats.total_bookmarks, 0)
        self.assertEqual(stats.total_categories, 0)
        self.assertEqual(stats.total_tags, 0)
        self.assertEqual(stats.category_counts, {})
        self.assertEqual(stats.top_domains, ())

    def test_collection_pulse_prioritizes_recoverable_work(self):
        bookmarks = [
            Bookmark(id=1, url="https://a.com", title="A", category="Research", tags=["x"]),
            Bookmark(id=2, url="https://b.com", title="B", is_valid=False),
            Bookmark(id=3, url="https://c.com", title="C", category="", tags=[]),
        ]
        pulse = build_collection_pulse(
            stats={
                "total_bookmarks": 3,
                "with_tags": 1,
                "broken": 1,
                "category_counts": {"Research": 1},
            },
            all_bookmarks=bookmarks,
            health_score=62,
        )
        self.assertEqual((pulse.healthy, pulse.needs_review, pulse.issues), (1, 1, 1))
        self.assertEqual(pulse.action_key, "broken")
        self.assertEqual(pulse.metrics["collections"], 1)

    def test_collection_pulse_empty_state_is_import_first(self):
        pulse = build_collection_pulse(stats={}, all_bookmarks=[], health_score=100)
        self.assertEqual(pulse.health_score, 0)
        self.assertEqual(pulse.health_label, "Ready")
        self.assertEqual(pulse.action_key, "import")


class TestUITheme(unittest.TestCase):
    """Test toolkit-independent theme models and persistence."""

    def _built_in_themes(self):
        return {
            "base": ThemeInfo(
                name="base",
                display_name="Base",
                colors=ThemeColors(accent_primary="#123456"),
            ),
            "light": ThemeInfo(
                name="light",
                display_name="Light",
                is_dark=False,
                colors=ThemeColors(bg_primary="#ffffff", text_primary="#111111"),
            ),
        }

    def test_theme_colors_round_trip_ignores_unknown_fields(self):
        colors = ThemeColors.from_dict({
            "bg_primary": "#010203",
            "accent_primary": "#abcdef",
            "future_field": "#ffffff",
        })
        self.assertEqual(colors.bg_primary, "#010203")
        self.assertEqual(colors.accent_primary, "#abcdef")
        self.assertNotIn("future_field", colors.to_dict())

    def test_custom_theme_honors_explicit_light_dark_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = ThemeManager(
                self._built_in_themes(),
                settings_file=root / "settings.json",
                themes_dir=root / "themes",
                default_theme="base",
            )
            theme = manager.create_custom_theme(
                "light_custom", "Light Custom", base_theme="base", is_dark=False
            )
            self.assertFalse(theme.is_dark)

    def test_custom_and_imported_themes_enforce_wcag_contrast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = ThemeManager(
                self._built_in_themes(),
                settings_file=root / "settings.json",
                themes_dir=root / "themes",
                default_theme="base",
            )
            with self.assertRaisesRegex(ValueError, "Primary text"):
                manager.create_custom_theme(
                    "unreadable", "Unreadable", base_theme="light",
                    color_overrides={"text_primary": "#ffffff", "bg_primary": "#ffffff"},
                )

            imported = root / "unsafe.json"
            imported.write_text(json.dumps({
                "name": "unsafe",
                "display_name": "Unsafe",
                "colors": {"text_primary": "#ffffff", "bg_primary": "#ffffff"},
            }), encoding="utf-8")
            self.assertIsNone(manager.import_theme(imported))
            self.assertNotIn("unsafe", manager.custom_themes)

    def test_theme_colors_reject_css_injection_values(self):
        colors = ThemeColors.from_dict({
            "bg_primary": "#010203",
            "text_primary": "red;}</style><script>alert(1)</script>",
        })
        self.assertEqual(colors.bg_primary, "#010203")
        self.assertEqual(colors.text_primary, ThemeColors().text_primary)

    def test_sv_ttk_mode_tracks_theme_background_luminance(self):
        from bookmark_organizer_pro.ui.style_manager import _sv_ttk_mode_for_colors

        self.assertEqual(_sv_ttk_mode_for_colors(ThemeColors(bg_primary="#ffffff")), "light")
        self.assertEqual(_sv_ttk_mode_for_colors(ThemeColors(bg_primary="#0d1117")), "dark")
        self.assertEqual(_sv_ttk_mode_for_colors(ThemeColors(bg_primary="#abc")), "light")

    def test_style_manager_preserves_native_theme_error_after_fallback(self):
        from bookmark_organizer_pro.ui.style_manager import StyleManager

        class FakeStyle:
            def theme_use(self, _name):
                return None

        manager = StyleManager()
        original_style = manager.style
        original_name = manager._base_theme_name
        original_error = manager._base_theme_error
        try:
            manager.style = FakeStyle()
            manager._base_theme_error = "sv-ttk failed"
            manager._apply_fallback_base_theme(clear_error=False)
            self.assertEqual(manager.native_theme_status["error"], "sv-ttk failed")
        finally:
            manager.style = original_style
            manager._base_theme_name = original_name
            manager._base_theme_error = original_error

    def test_reader_view_dialog_is_exported(self):
        from bookmark_organizer_pro.ui import GraphViewDialog, ReaderViewDialog, text_index_offset

        self.assertTrue(callable(GraphViewDialog))
        self.assertTrue(callable(ReaderViewDialog))
        self.assertTrue(callable(text_index_offset))

    def test_theme_info_coerces_serialized_boolean(self):
        theme = ThemeInfo.from_dict({"name": "lightish", "display_name": "Lightish", "is_dark": "false"})
        self.assertFalse(theme.is_dark)

    def test_theme_manager_persists_selection_and_notifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            settings_file = base / "settings.json"
            themes_dir = base / "themes"
            manager = ThemeManager(
                self._built_in_themes(),
                settings_file=settings_file,
                themes_dir=themes_dir,
                default_theme="base",
            )
            events = []
            manager.add_theme_change_callback(lambda theme: events.append(theme.name))

            self.assertTrue(manager.set_theme("light"))
            self.assertEqual(events, ["light"])
            self.assertEqual(json.loads(settings_file.read_text(encoding="utf-8"))["theme"], "light")

            reloaded = ThemeManager(
                self._built_in_themes(),
                settings_file=settings_file,
                themes_dir=themes_dir,
                default_theme="base",
            )
            self.assertEqual(reloaded.current_theme.name, "light")

    def test_custom_theme_names_are_sanitized_and_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manager = ThemeManager(
                self._built_in_themes(),
                settings_file=base / "settings.json",
                themes_dir=base / "themes",
                default_theme="base",
            )

            first = manager.create_custom_theme("../base", "Imported")
            second = manager.create_custom_theme("../base", "Imported Again")

            self.assertEqual(first.name, "base_1")
            self.assertEqual(second.name, "base_2")
            self.assertTrue((base / "themes" / "base_1.json").exists())
            self.assertTrue((base / "themes" / "base_2.json").exists())
            self.assertFalse((base / "base_1.json").exists())


class TestUIPreferences(unittest.TestCase):
    """Test toolkit-independent UI preference helpers."""

    def test_density_manager_persists_and_notifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            settings_file.write_text(json.dumps({"theme": "github_dark"}), encoding="utf-8")
            manager = DensityManager(settings_file=settings_file)
            events = []
            manager.add_callback(lambda density: events.append(density))

            manager.density = "spacious"

            self.assertEqual(manager.density, DisplayDensity.SPACIOUS)
            self.assertEqual(events, [DisplayDensity.SPACIOUS])
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertEqual(data["theme"], "github_dark")
            self.assertEqual(data["display_density"], "spacious")
            self.assertEqual(manager.get_setting("icon_size"), 20)

    def test_density_manager_falls_back_on_invalid_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            settings_file.write_text(json.dumps({"display_density": "microscopic"}), encoding="utf-8")
            manager = DensityManager(settings_file=settings_file)
            self.assertEqual(manager.density, DisplayDensity.COMFORTABLE)

    def test_system_theme_detector_monitor_callback(self):
        class FakeRoot:
            def __init__(self):
                self.callbacks = []

            def after(self, delay, callback):
                self.callbacks.append((delay, callback))

        detector = SystemThemeDetector(check_interval_ms=50)
        observed = []
        detector.on_theme_change = observed.append
        states = iter([True, False])
        detector.get_system_theme_is_dark = lambda: next(states)
        root = FakeRoot()

        detector.start_monitoring(root)
        self.assertEqual(len(root.callbacks), 1)
        root.callbacks.pop()[1]()

        self.assertEqual(observed, [False])
        detector.stop_monitoring()


class TestUIReports(unittest.TestCase):
    """Test report generation safety and output."""

    class FakeBookmarkManager:
        def get_statistics(self):
            return {
                "total_bookmarks": 2,
                "total_categories": 1,
                "total_tags": 0,
                "duplicate_bookmarks": 0,
                "broken": 0,
                "uncategorized": 0,
                "category_counts": {"<script>alert(1)</script>": 2},
                "top_domains": [("example.com\"><script>alert(2)</script>", 2)],
                "age_distribution": {"<1 week": 2},
            }

    def test_html_report_escapes_imported_user_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.html"
            generator = ReportGenerator(
                self.FakeBookmarkManager(),
                theme_provider=ThemeColors,
                app_name="Test App",
                app_version="v0",
            )

            generator.generate_html_report(str(report_path))
            output = report_path.read_text(encoding="utf-8")

            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", output)
            self.assertIn("example.com&quot;&gt;&lt;script&gt;alert(2)&lt;/script&gt;", output)
            self.assertNotIn("<script>alert", output)

    def test_reports_tolerate_corrupt_count_values(self):
        class CorruptStatsManager:
            def get_statistics(self):
                return {
                    "total_bookmarks": "bad",
                    "total_categories": None,
                    "total_tags": -5,
                    "duplicate_bookmarks": "1",
                    "category_counts": {"Research": "bad"},
                    "top_domains": [("example.com", "also-bad")],
                    "age_distribution": {"Recent": object()},
                }

        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "nested" / "report.html"
            text_path = Path(tmp) / "nested" / "report.txt"
            generator = ReportGenerator(CorruptStatsManager(), theme_provider=ThemeColors)

            generator.generate_html_report(str(html_path))
            generator.generate_text_report(str(text_path))

            self.assertTrue(html_path.exists())
            self.assertTrue(text_path.exists())


class TestQuickAddForm(unittest.TestCase):
    """Test quick-add form normalization independent of Tk widgets."""

    def test_quick_add_adds_scheme_and_preserves_title_prefix(self):
        payload, error = prepare_quick_add_payload(
            url="example.com/article",
            title="Titleist fitting guide",
            category="Golf",
            categories=["Golf"],
        )

        self.assertEqual(error, "")
        self.assertEqual(payload.url, "https://example.com/article")
        self.assertEqual(payload.title, "Titleist fitting guide")
        self.assertEqual(payload.category, "Golf")

    def test_quick_add_ignores_active_placeholders(self):
        payload, error = prepare_quick_add_payload(
            url="https://example.com",
            title="Title (optional)",
            category="",
            categories=[],
            favicon_input="Favicon URL or local image path",
            title_placeholder_active=True,
            favicon_placeholder_active=True,
        )

        self.assertEqual(error, "")
        self.assertEqual(payload.title, "https://example.com")
        self.assertEqual(payload.favicon_input, "")
        self.assertEqual(payload.category, "Uncategorized / Needs Review")

    def test_quick_add_rejects_malformed_url(self):
        payload, error = prepare_quick_add_payload(url="exa mple.com", categories=[])
        self.assertIsNone(payload)
        self.assertIn("whitespace", error)

    def test_pick_default_category_prefers_needs_review(self):
        self.assertEqual(
            pick_default_category(["Inbox", "Uncategorized / Needs Review"]),
            "Uncategorized / Needs Review",
        )
        self.assertEqual(pick_default_category(["Inbox"]), "Inbox")


class TestImportCenterGuidance(unittest.TestCase):
    """Test import-center source guidance without constructing Tk widgets."""

    def test_import_center_covers_required_migration_paths(self):
        from bookmark_organizer_pro.ui.import_center import build_import_sources

        sources = {source.key: source for source in build_import_sources(["chrome", "firefox", "edge"])}

        required = {
            "browser-chrome",
            "browser-firefox",
            "browser-edge",
            "browser-safari",
            "pocket",
            "arc",
            "raindrop",
            "readwise",
            "chrome-reading-list",
        }
        self.assertTrue(required.issubset(sources))

        for key in required:
            source = sources[key]
            self.assertTrue(source.accepted_formats, key)
            self.assertTrue(source.privacy_note, key)
            self.assertTrue(source.duplicate_policy, key)
            self.assertTrue(source.import_summary, key)
            self.assertTrue(source.next_action, key)
            self.assertTrue(source.action_label, key)

    def test_detected_browser_cards_use_direct_profiles_when_supported(self):
        from bookmark_organizer_pro.ui.import_center import build_import_sources

        sources = {source.key: source for source in build_import_sources(["chrome", "firefox", "edge"])}

        self.assertEqual(sources["browser-chrome"].action_kind, "browser_profile")
        self.assertEqual(sources["browser-firefox"].action_kind, "browser_profile")
        self.assertEqual(sources["browser-edge"].action_kind, "browser_profile")
        self.assertEqual(sources["browser-safari"].action_kind, "file")
        self.assertIn(".html", sources["browser-safari"].accepted_formats)

    def test_service_and_reading_list_cards_route_to_existing_paths(self):
        from bookmark_organizer_pro.ui.import_center import build_import_sources

        sources = {source.key: source for source in build_import_sources([])}

        self.assertEqual(sources["pocket"].action_arg, "pocket")
        self.assertEqual(sources["arc"].action_arg, "arc")
        self.assertEqual(sources["raindrop"].action_arg, "raindrop")
        self.assertEqual(sources["readwise"].action_arg, "readwise")
        self.assertEqual(sources["chrome-reading-list"].action_kind, "reading_list_help")
        self.assertIn("side panel", sources["chrome-reading-list"].next_action.lower())


class TestFaviconServices(unittest.TestCase):
    """Test favicon services extracted from main.py."""

    def test_favicon_services_are_reexported_from_main(self):
        import main
        from bookmark_organizer_pro.services.favicons import (
            FaviconWrapperGenerator,
            HighSpeedFaviconManager,
        )

        self.assertIs(main.FaviconWrapperGenerator, FaviconWrapperGenerator)
        self.assertIs(main.HighSpeedFaviconManager, HighSpeedFaviconManager)

    def test_favicon_manager_normalizes_domains_and_persists_failed_state(self):
        from bookmark_organizer_pro.services.favicons import HighSpeedFaviconManager

        old_cache_dir = HighSpeedFaviconManager.CACHE_DIR
        old_failed_file = HighSpeedFaviconManager.FAILED_FILE

        with tempfile.TemporaryDirectory() as tmp:
            HighSpeedFaviconManager.CACHE_DIR = Path(tmp) / "favicons"
            HighSpeedFaviconManager.FAILED_FILE = Path(tmp) / "failed.json"
            manager = None
            try:
                manager = HighSpeedFaviconManager(max_workers="invalid")

                self.assertEqual(manager._normalize_domain("https://Example.com/path"), "example.com")
                self.assertEqual(manager._normalize_domain("bad host"), "")

                manager._failed_domains.add("example.com")
                manager.clear_failed_domains()

                data = json.loads(HighSpeedFaviconManager.FAILED_FILE.read_text(encoding="utf-8"))
                self.assertEqual(data, {"failed_domains": []})
            finally:
                if manager is not None:
                    manager.shutdown()
                HighSpeedFaviconManager.CACHE_DIR = old_cache_dir
                HighSpeedFaviconManager.FAILED_FILE = old_failed_file

    def test_favicon_wrapper_escapes_content_and_uses_safe_filename(self):
        from bookmark_organizer_pro.services.favicons import FaviconWrapperGenerator

        old_wrapper_dir = FaviconWrapperGenerator.WRAPPER_DIR

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            favicon_path = tmp_path / "icon.ico"
            favicon_path.write_bytes(b"fake-icon")
            FaviconWrapperGenerator.WRAPPER_DIR = tmp_path / "wrappers"

            bookmark = Bookmark(
                id=7,
                url='not-a-url"><script>alert(1)</script>',
                title="<script>",
            )

            try:
                wrapper = FaviconWrapperGenerator.generate_wrapper(bookmark, str(favicon_path))
            finally:
                FaviconWrapperGenerator.WRAPPER_DIR = old_wrapper_dir

            self.assertIsNotNone(wrapper)
            wrapper_path = Path(wrapper)
            self.assertEqual(wrapper_path.name, "script_7.html")

            html = wrapper_path.read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("not-a-url&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertNotIn("<script>alert", html)


class TestNavigationHelpers(unittest.TestCase):
    """Test reusable UI interaction helpers extracted from main.py."""

    def test_search_highlighter_escapes_html_around_matches(self):
        output = SearchHighlighter().get_highlighted_html("<b>needle</b>", "needle")

        self.assertIn("&lt;b&gt;", output)
        self.assertIn("&lt;/b&gt;", output)
        self.assertIn("<mark", output)
        self.assertIn(">needle</mark>", output)
        self.assertNotIn("<b>", output)

    def test_task_runner_delivers_background_errors_to_ui_callback(self):
        class FakeRoot:
            def after(self, delay, callback):
                callback()

        errors = []
        runner = NonBlockingTaskRunner(FakeRoot())
        try:
            future = runner.run_task(
                "boom",
                lambda: (_ for _ in ()).throw(RuntimeError("failed")),
                on_error=errors.append,
            )
            future.result(timeout=5)
        finally:
            runner.shutdown()

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(str(errors[0]), "failed")


class TestLevenshtein(unittest.TestCase):
    """Test Levenshtein distance and fuzzy matching."""

    def test_identical_strings(self):
        self.assertEqual(levenshtein_distance("hello", "hello"), 0)

    def test_empty_string(self):
        self.assertEqual(levenshtein_distance("hello", ""), 5)

    def test_single_edit(self):
        self.assertEqual(levenshtein_distance("cat", "car"), 1)

    def test_fuzzy_match_exact(self):
        matches, score = fuzzy_match("python", "learning python programming")
        self.assertTrue(matches)
        self.assertEqual(score, 1.0)

    def test_fuzzy_match_close(self):
        matches, score = fuzzy_match("pythn", "python programming")
        self.assertTrue(matches)
        self.assertGreater(score, 0.5)

    def test_fuzzy_no_match(self):
        matches, score = fuzzy_match("xyz", "abc def ghi")
        self.assertFalse(matches)


if __name__ == "__main__":
    unittest.main()
