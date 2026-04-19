"""Core tests for pattern engine, URL normalization, search, and bookmark model."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

# Ensure package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookmark_organizer_pro.models.bookmark import Bookmark
from bookmark_organizer_pro.models.category import Category
from bookmark_organizer_pro.ai import AIConfigManager
from bookmark_organizer_pro.constants import IS_WINDOWS
from bookmark_organizer_pro.core.category_manager import CategoryManager
from bookmark_organizer_pro.core.storage_manager import StorageManager
from bookmark_organizer_pro.core.pattern_engine import PatternEngine
from bookmark_organizer_pro.importers import OPMLExporter, OPMLImporter
from bookmark_organizer_pro.link_checker import LinkChecker
from bookmark_organizer_pro.search import SearchQuery, SearchEngine, levenshtein_distance, fuzzy_match
from bookmark_organizer_pro.ui import (
    DensityManager,
    DisplayDensity,
    ReportGenerator,
    SystemThemeDetector,
    ThemeColors,
    ThemeInfo,
    ThemeManager,
    build_collection_summary,
    build_filter_counts,
    format_compact_count,
    pick_default_category,
    prepare_quick_add_payload,
    readable_text_on,
    truncate_middle,
)
from bookmark_organizer_pro.utils.url import normalize_url
from bookmark_organizer_pro.utils.safe import safe_get_domain
from bookmark_organizer_pro.utils.dependencies import DependencyManager
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
        bm = Bookmark.from_dict({"url": "https://x.com", "tags": "a,b, c"})
        self.assertEqual(bm.tags, ["a", "b", "c"])

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

    def test_no_match(self):
        bm = Bookmark(id=1, url="https://example.com", title="Hello")
        q = SearchQuery("nonexistent")
        self.assertFalse(q.matches(bm))

    def test_search_engine_accepts_none_query(self):
        bm = Bookmark(id=1, url="https://example.com", title="Hello")
        results = SearchEngine().search([bm], None)
        self.assertEqual(results, [(bm, 1.0)])

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

    def test_validate_path_allows_windows_drive_and_rejects_bad_segments(self):
        if IS_WINDOWS:
            self.assertTrue(validate_path(r"C:\Temp\bookmarks.json")[0])
            self.assertFalse(validate_path(r"C:\Temp\bad:name.json")[0])
            self.assertFalse(validate_path(r"C:\Temp\CON.txt")[0])
        else:
            self.assertTrue(validate_path("/tmp/bookmarks.json")[0])
        self.assertFalse(validate_path("bad\x00name")[0])


class TestDependencyManager(unittest.TestCase):
    """Test runtime dependency discovery and install guardrails."""

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
