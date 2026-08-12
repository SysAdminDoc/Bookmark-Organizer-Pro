"""Tests for AI client resilience: retry/backoff, friendly errors, the shared
OpenAI-compatible base, failover routing, and the default-categories asset."""

from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


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

    def test_operation_cancellation_stops_retry_and_is_recorded(self):
        from bookmark_organizer_pro import ai
        from bookmark_organizer_pro.services.ai_operation import (
            AICancellationToken,
            AIOperation,
            AIOperationCancelled,
        )
        from bookmark_organizer_pro.services.job_ledger import JobLedger

        token = AICancellationToken()
        token.cancel("stop from test")
        calls = {"count": 0}

        with tempfile.TemporaryDirectory() as tmp:
            ledger = JobLedger(Path(tmp) / "jobs.json")
            operation = AIOperation(
                "retry_cancel",
                token=token,
                job_ledger=ledger,
            )
            with self.assertRaises(AIOperationCancelled):
                with operation:
                    ai._retry(
                        lambda: calls.__setitem__("count", calls["count"] + 1),
                        operation=operation,
                    )

            self.assertEqual(calls["count"], 0)
            records = ledger.list_records(job_type="ai_retry_cancel")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].outcome, "cancelled")
            self.assertEqual(records[0].retryable, False)

    def test_stream_closes_and_records_output_budget_failure(self):
        from bookmark_organizer_pro.ai import OpenAIClient
        from bookmark_organizer_pro.services.ai_operation import (
            AIBudget,
            AIBudgetExceeded,
            AIOperation,
        )
        from bookmark_organizer_pro.services.job_ledger import JobLedger

        class Stream:
            def __init__(self):
                self.closed = False

            def __iter__(self):
                for text in ("abcd", "e"):
                    yield SimpleNamespace(
                        choices=[SimpleNamespace(
                            delta=SimpleNamespace(content=text),
                        )]
                    )

            def close(self):
                self.closed = True

        stream = Stream()

        class Completions:
            def create(self, **_kwargs):
                return stream

        client = OpenAIClient("key", "gpt-4o-mini")
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))

        with tempfile.TemporaryDirectory() as tmp:
            ledger = JobLedger(Path(tmp) / "jobs.json")
            operation = AIOperation(
                "stream_budget",
                budget=AIBudget(
                    max_output_chars=4,
                    max_output_tokens=100,
                ),
                job_ledger=ledger,
            )
            with self.assertRaises(AIBudgetExceeded):
                with operation:
                    list(client.stream_complete("hello", operation=operation))

            self.assertTrue(stream.closed)
            record = ledger.list_records(job_type="ai_stream_budget")[0]
            self.assertEqual(record.outcome, "failure")
            self.assertEqual(record.retryable, False)
            self.assertEqual(record.limit_reason, "output characters")
            self.assertEqual(record.output_chars, 4)

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


class _InstallResponse:
    def __init__(self, url, chunks=(), *, status_code=200, headers=None):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, _chunk_size):
        yield from self._chunks

    def close(self):
        self.closed = True


class TestOllamaInstallerProvenance(unittest.TestCase):
    def _download(self, asset, response, destination, cancel_event=None):
        from bookmark_organizer_pro.services import ollama_manager

        requests = SimpleNamespace(get=MagicMock(return_value=response))
        manager = ollama_manager.OllamaManager()
        with patch.object(
            ollama_manager.importlib,
            "import_module",
            return_value=requests,
        ):
            manager._download_verified_asset(
                asset,
                destination,
                cancel_event or threading.Event(),
            )
        return requests

    def test_install_requires_explicit_confirmation(self):
        from bookmark_organizer_pro.services import ollama_manager

        results = []
        manager = ollama_manager.OllamaManager()
        with patch.object(ollama_manager.threading.Thread, "start") as start:
            manager.install(on_done=lambda ok, message: results.append((ok, message)))

        start.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0][0])
        self.assertIn("explicit confirmation", results[0][1])

    def test_verified_download_is_atomically_promoted(self):
        from bookmark_organizer_pro.services.ollama_manager import OllamaInstallAsset

        payload = b"verified installer bytes"
        asset = OllamaInstallAsset(
            name="installer.exe",
            url="https://github.com/ollama/ollama/releases/download/v1/installer.exe",
            sha256=hashlib.sha256(payload).hexdigest(),
            max_bytes=1024,
        )
        response = _InstallResponse(
            asset.url,
            [payload[:8], payload[8:]],
            headers={"Content-Length": str(len(payload))},
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / asset.name
            requests = self._download(asset, response, destination)

            self.assertEqual(destination.read_bytes(), payload)
            self.assertFalse(destination.with_name("installer.exe.part").exists())
            self.assertTrue(response.closed)
            self.assertFalse(requests.get.call_args.kwargs["allow_redirects"])

    def test_digest_mismatch_discards_partial_and_final_files(self):
        from bookmark_organizer_pro.services.ollama_manager import OllamaInstallAsset

        asset = OllamaInstallAsset(
            name="installer.exe",
            url="https://github.com/ollama/ollama/releases/download/v1/installer.exe",
            sha256="0" * 64,
            max_bytes=1024,
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / asset.name
            response = _InstallResponse(asset.url, [b"tampered"])
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self._download(asset, response, destination)

            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name("installer.exe.part").exists())

    def test_declared_or_streamed_oversize_is_rejected(self):
        from bookmark_organizer_pro.services.ollama_manager import OllamaInstallAsset

        asset = OllamaInstallAsset(
            name="installer.exe",
            url="https://github.com/ollama/ollama/releases/download/v1/installer.exe",
            sha256=hashlib.sha256(b"small").hexdigest(),
            max_bytes=5,
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / asset.name
            declared = _InstallResponse(
                asset.url,
                [b"small"],
                headers={"Content-Length": "6"},
            )
            with self.assertRaisesRegex(ValueError, "byte limit"):
                self._download(asset, declared, destination)

            streamed = _InstallResponse(asset.url, [b"larger"])
            with self.assertRaisesRegex(ValueError, "byte limit"):
                self._download(asset, streamed, destination)
            self.assertFalse(destination.exists())

    def test_redirect_to_unapproved_host_is_rejected_before_request(self):
        from bookmark_organizer_pro.services import ollama_manager

        asset = ollama_manager.OllamaInstallAsset(
            name="installer.exe",
            url="https://github.com/ollama/ollama/releases/download/v1/installer.exe",
            sha256="0" * 64,
            max_bytes=1024,
        )
        redirect = _InstallResponse(
            asset.url,
            status_code=302,
            headers={"Location": "https://downloads.example.test/installer.exe"},
        )
        requests = SimpleNamespace(get=MagicMock(return_value=redirect))
        manager = ollama_manager.OllamaManager()
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            ollama_manager.importlib,
            "import_module",
            return_value=requests,
        ):
            with self.assertRaisesRegex(ValueError, "approved HTTPS sources"):
                manager._download_verified_asset(
                    asset,
                    Path(tmp) / asset.name,
                    threading.Event(),
                )

        self.assertEqual(requests.get.call_count, 1)
        self.assertTrue(redirect.closed)

    def test_cancellation_removes_partial_download_and_work_directory(self):
        from bookmark_organizer_pro.services import ollama_manager

        cancel_event = threading.Event()
        cancel_event.set()
        asset = ollama_manager.OllamaInstallAsset(
            name="installer.exe",
            url="https://github.com/ollama/ollama/releases/download/v1/installer.exe",
            sha256=hashlib.sha256(b"unused").hexdigest(),
            max_bytes=1024,
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / asset.name
            response = _InstallResponse(asset.url, [b"unused"])
            with self.assertRaises(ollama_manager.OllamaInstallCancelled):
                self._download(asset, response, destination, cancel_event)
            self.assertFalse(destination.exists())

            work_dir = Path(tmp) / "install-work"
            work_dir.mkdir()
            with patch.object(
                ollama_manager.tempfile,
                "mkdtemp",
                return_value=str(work_dir),
            ), patch.object(
                ollama_manager.OllamaManager,
                "_download_verified_asset",
                side_effect=ollama_manager.OllamaInstallCancelled("cancelled"),
            ):
                ok, message = ollama_manager.OllamaManager()._install_windows(
                    None,
                    cancel_event,
                )
            self.assertFalse(ok)
            self.assertIn("cancelled", message)
            self.assertFalse(work_dir.exists())

    def test_manual_linux_guidance_is_pinned_and_never_pipes_to_shell(self):
        from bookmark_organizer_pro.services import ollama_manager

        with patch.object(ollama_manager.platform, "machine", return_value="x86_64"):
            instructions = ollama_manager.OllamaManager.manual_install_instructions(
                "Linux"
            )

        self.assertIn(ollama_manager.OLLAMA_INSTALL_VERSION, instructions)
        self.assertIn(ollama_manager.OLLAMA_LINUX_AMD64.sha256, instructions)
        self.assertIn("sha256sum --check", instructions)
        self.assertNotIn("| sh", instructions)
        self.assertLess(
            ollama_manager.OLLAMA_WINDOWS_INSTALLER.max_bytes,
            2_000_000_000,
        )


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
