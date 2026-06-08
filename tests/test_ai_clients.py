"""Tests for AI client resilience: retry/backoff, friendly errors, the shared
OpenAI-compatible base, failover routing, and the default-categories asset."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch


def _json_response(content: str):
    """Build a fake OpenAI-style chat completion response."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class TestRetryHelpers(unittest.TestCase):
    def test_is_retryable_classifies_transient_errors(self):
        from bookmark_organizer_pro.ai import _is_retryable

        for msg in ["Rate limit exceeded", "HTTP 503", "Connection reset by peer",
                    "Request timed out", "model overloaded"]:
            self.assertTrue(_is_retryable(Exception(msg)), msg)

        for msg in ["Invalid API key", "401 Unauthorized", "bad request"]:
            self.assertFalse(_is_retryable(Exception(msg)), msg)

    def test_retry_recovers_after_transient_failure(self):
        from bookmark_organizer_pro import ai

        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("rate limit, try again")
            return "ok"

        with patch.object(ai.time, "sleep") as sleep:
            result = ai._retry(flaky, attempts=3, base_delay=0.01, label="test")

        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleep.call_count, 2)  # backoff between the 3 attempts

    def test_retry_does_not_retry_permanent_errors(self):
        from bookmark_organizer_pro import ai

        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise ValueError("invalid api key")

        with patch.object(ai.time, "sleep") as sleep:
            with self.assertRaises(ValueError):
                ai._retry(boom, attempts=4, base_delay=0.01)

        self.assertEqual(calls["n"], 1)        # failed fast, no retries
        self.assertEqual(sleep.call_count, 0)

    def test_retry_exhausts_attempts_then_raises(self):
        from bookmark_organizer_pro import ai

        def always_busy():
            raise RuntimeError("503 service unavailable")

        with patch.object(ai.time, "sleep"):
            with self.assertRaises(RuntimeError):
                ai._retry(always_busy, attempts=3, base_delay=0.01)

    def test_friendly_model_error_points_to_settings(self):
        from bookmark_organizer_pro.ai import _friendly_model_error

        msg = _friendly_model_error(
            Exception("The model `gpt-4.1` does not exist"), "OpenAI", "gpt-4.1")
        self.assertIn("gpt-4.1", msg)
        self.assertIn("AI settings", msg)

        generic = _friendly_model_error(Exception("network blip"), "OpenAI", "gpt-4o-mini")
        self.assertTrue(generic.startswith("Error:"))


class TestOpenAICompatibleClients(unittest.TestCase):
    def _client_with_completions(self, client, completions):
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        return client

    def test_categorize_retries_then_parses(self):
        from bookmark_organizer_pro import ai
        from bookmark_organizer_pro.ai import OpenAIClient

        class FlakyCompletions:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("rate limit reached")
                return _json_response(
                    '{"results": [{"url": "https://a.com", "category": "News", "confidence": 0.91}]}')

        completions = FlakyCompletions()
        client = self._client_with_completions(OpenAIClient("k", "gpt-4o-mini"), completions)

        with patch.object(ai.time, "sleep"):
            results = client.categorize_bookmarks([{"url": "https://a.com", "title": "A"}], ["News"])

        self.assertEqual(completions.calls, 2)
        self.assertEqual(results[0]["url"], "https://a.com")
        self.assertEqual(results[0]["category"], "News")

    def test_subclasses_share_base_behavior(self):
        from bookmark_organizer_pro.ai import (
            DeepSeekClient, GroqClient, OpenAICompatibleClient)

        for cls, label, hint in [
            (GroqClient, "Groq", "console.groq.com/keys"),
            (DeepSeekClient, "DeepSeek", "platform.deepseek.com/api_keys"),
        ]:
            self.assertTrue(issubclass(cls, OpenAICompatibleClient))
            inst = cls("key", "model-x")
            self.assertEqual(inst.provider_label, label)
            self.assertEqual(inst.api_key_hint, hint)
            self.assertTrue(inst.supports_native_streaming)

    def test_missing_api_key_raises_with_provider_name(self):
        from bookmark_organizer_pro.ai import GroqClient

        client = GroqClient("", "model")
        with self.assertRaises(ValueError) as ctx:
            _ = client.client
        self.assertIn("Groq", str(ctx.exception))

    def test_complete_returns_message_content(self):
        from bookmark_organizer_pro.ai import DeepSeekClient

        class Completions:
            def create(self, **kwargs):
                return _json_response("hello world")

        client = DeepSeekClient("k", "deepseek-chat")
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
        self.assertEqual(client.complete("hi"), "hello world")


class _FakeConfig:
    def __init__(self):
        self.provider = "openai"
        self.model = "gpt-4o-mini"
        self.fo_provider = "anthropic"
        self.fo_model = "claude-3-5-haiku-20241022"
        self.threshold = 0.6

    def get_failover_confidence_threshold(self):
        return self.threshold

    def get_provider(self):
        return self.provider

    def get_model(self):
        return self.model

    def get_failover_provider(self):
        return self.fo_provider

    def get_failover_model(self):
        return self.fo_model


class _StubClient:
    def __init__(self, results=None, complete_value="", raises=None):
        self._results = results or []
        self._complete_value = complete_value
        self._raises = raises

    def categorize_bookmarks(self, bookmarks, categories, allow_new=True, suggest_tags=True):
        return [dict(r) for r in self._results]

    def complete(self, prompt, system="", max_tokens=800, temperature=0.2):
        if self._raises:
            raise self._raises
        return self._complete_value

    def test_connection(self):
        return True, "ok"


class TestFailoverClient(unittest.TestCase):
    def test_low_confidence_results_retry_on_secondary(self):
        from bookmark_organizer_pro.ai import FailoverAIClient

        primary = _StubClient(results=[{"url": "u", "category": "Misc", "confidence": 0.2}])
        secondary = _StubClient(results=[{"url": "u", "category": "News", "confidence": 0.95}])
        client = FailoverAIClient(primary, secondary, _FakeConfig())

        out = client.categorize_bookmarks([{"url": "u", "title": "t"}], ["News"])

        self.assertEqual(out[0]["category"], "News")
        self.assertTrue(out[0].get("_failover"))
        self.assertEqual(out[0].get("_failover_provider"), "anthropic")
        self.assertEqual(client.failover_count, 1)

    def test_high_confidence_skips_secondary(self):
        from bookmark_organizer_pro.ai import FailoverAIClient

        primary = _StubClient(results=[{"url": "u", "category": "News", "confidence": 0.97}])
        secondary = _StubClient(results=[{"url": "u", "category": "Wrong", "confidence": 0.99}])
        client = FailoverAIClient(primary, secondary, _FakeConfig())

        out = client.categorize_bookmarks([{"url": "u", "title": "t"}], ["News"])

        self.assertEqual(out[0]["category"], "News")
        self.assertFalse(out[0].get("_failover", False))
        self.assertEqual(client.failover_count, 0)

    def test_no_secondary_returns_primary_unchanged(self):
        from bookmark_organizer_pro.ai import FailoverAIClient

        primary = _StubClient(results=[{"url": "u", "category": "Misc", "confidence": 0.1}])
        client = FailoverAIClient(primary, None, _FakeConfig())

        out = client.categorize_bookmarks([{"url": "u", "title": "t"}], ["News"])
        self.assertEqual(out[0]["category"], "Misc")

    def test_complete_falls_back_to_secondary_on_primary_error(self):
        from bookmark_organizer_pro.ai import FailoverAIClient

        primary = _StubClient(raises=RuntimeError("primary down"))
        secondary = _StubClient(complete_value="from-secondary")
        client = FailoverAIClient(primary, secondary, _FakeConfig())

        self.assertEqual(client.complete("hi"), "from-secondary")
        self.assertEqual(client.last_provider, "anthropic")


class TestDefaultCategoriesAsset(unittest.TestCase):
    def test_default_categories_load_from_json(self):
        from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES

        self.assertIsInstance(DEFAULT_CATEGORIES, dict)
        self.assertGreaterEqual(len(DEFAULT_CATEGORIES), 40)
        # Every value is a list of string patterns.
        for name, patterns in DEFAULT_CATEGORIES.items():
            self.assertIsInstance(name, str)
            self.assertIsInstance(patterns, list)
            self.assertTrue(all(isinstance(p, str) for p in patterns))

    def test_curated_categories_present_and_route(self):
        from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES
        from bookmark_organizer_pro.core.category_manager import get_category_icon

        expected = {
            "Music & Audio": "spotify.com",
            "Communication": "slack.com",
            "Cryptocurrency": "coinbase.com",
            "Maps & Navigation": "maps.google.com",
            "Books & Literature": "goodreads.com",
        }
        dom2cat = {p[7:]: cat for cat, pats in DEFAULT_CATEGORIES.items()
                   for p in pats if p.startswith("domain:")}
        for cat, sample in expected.items():
            self.assertIn(cat, DEFAULT_CATEGORIES, f"missing category {cat}")
            self.assertGreaterEqual(len(DEFAULT_CATEGORIES[cat]), 10)
            self.assertEqual(dom2cat.get(sample), cat, f"{sample} should route to {cat}")
            # A real (non-generic) icon is assigned.
            self.assertNotEqual(get_category_icon(cat), "\U0001F4C2", f"{cat} has no icon")

    def test_no_domain_rule_in_two_categories(self):
        """A domain must live in exactly one category — duplicates cause
        ambiguous matches whose winner depends on dict iteration order."""
        from collections import Counter
        from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES

        counts = Counter(
            p for pats in DEFAULT_CATEGORIES.values() for p in pats if p.startswith("domain:")
        )
        dups = [p for p, n in counts.items() if n > 1]
        self.assertEqual(dups, [], f"domain rules in multiple categories: {dups[:10]}")


if __name__ == "__main__":
    unittest.main()
