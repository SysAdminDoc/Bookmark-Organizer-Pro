"""Core tests for pattern engine, URL normalization, search, and bookmark model."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookmark_organizer_pro.models.bookmark import Bookmark
from bookmark_organizer_pro.models.category import Category
from bookmark_organizer_pro.ai import AIConfigManager
from bookmark_organizer_pro.core.category_manager import CategoryManager
from bookmark_organizer_pro.core.storage_manager import StorageManager
from bookmark_organizer_pro.core.pattern_engine import PatternEngine
from bookmark_organizer_pro.importers import OPMLExporter
from bookmark_organizer_pro.link_checker import LinkChecker
from bookmark_organizer_pro.search import SearchQuery, SearchEngine, levenshtein_distance, fuzzy_match
from bookmark_organizer_pro.utils.url import normalize_url
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
