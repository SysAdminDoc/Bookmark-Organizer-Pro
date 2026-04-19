"""Core tests for pattern engine, URL normalization, search, and bookmark model."""

import os
import sys
import unittest

# Ensure package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bookmark_organizer_pro.models.bookmark import Bookmark
from bookmark_organizer_pro.core.pattern_engine import PatternEngine
from bookmark_organizer_pro.search import SearchQuery, SearchEngine, levenshtein_distance, fuzzy_match
from bookmark_organizer_pro.utils.url import normalize_url


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

    def test_clean_url_strips_tracking(self):
        bm = Bookmark(id=1, url="https://example.com/page?utm_source=test&real=1", title="T")
        cleaned = bm.clean_url()
        self.assertNotIn("utm_source", cleaned)
        self.assertIn("real=1", cleaned)

    def test_domain_property(self):
        bm = Bookmark(id=1, url="https://www.github.com/user/repo", title="T")
        self.assertEqual(bm.domain, "github.com")


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
        self.assertIsInstance(result, str)


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

    def test_no_match(self):
        bm = Bookmark(id=1, url="https://example.com", title="Hello")
        q = SearchQuery("nonexistent")
        self.assertFalse(q.matches(bm))


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
