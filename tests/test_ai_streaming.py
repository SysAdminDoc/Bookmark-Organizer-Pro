"""Tests for provider streaming adapters."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch


class TestAIStreamingAdapters(unittest.TestCase):
    def test_base_stream_complete_falls_back_to_complete(self):
        from bookmark_organizer_pro.ai import AIClient

        class FakeClient(AIClient):
            def categorize_bookmarks(self, bookmarks, categories, allow_new=True, suggest_tags=True):
                return []

            def test_connection(self):
                return True, "ok"

            def complete(self, prompt, system="", max_tokens=800, temperature=0.2):
                return "completed answer"

        client = FakeClient()

        self.assertFalse(client.supports_native_streaming)
        self.assertEqual(list(client.stream_complete("question")), ["completed answer"])

    def test_openai_compatible_stream_complete_yields_delta_content(self):
        from bookmark_organizer_pro.ai import OpenAIClient

        class FakeCompletions:
            def __init__(self):
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs
                return [
                    SimpleNamespace(choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="hello"))
                    ]),
                    SimpleNamespace(choices=[
                        SimpleNamespace(delta=SimpleNamespace(content=" "))
                    ]),
                    SimpleNamespace(choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="world"))
                    ]),
                    SimpleNamespace(choices=[
                        SimpleNamespace(delta=SimpleNamespace(content=None))
                    ]),
                ]

        completions = FakeCompletions()
        client = OpenAIClient("test-key", "test-model")
        client._client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        chunks = list(client.stream_complete("prompt", system="system", max_tokens=12, temperature=0.4))

        self.assertTrue(client.supports_native_streaming)
        self.assertEqual(chunks, ["hello", " ", "world"])
        self.assertTrue(completions.kwargs["stream"])
        self.assertEqual(completions.kwargs["model"], "test-model")
        self.assertEqual(completions.kwargs["max_tokens"], 12)
        self.assertEqual(completions.kwargs["temperature"], 0.4)
        self.assertEqual(completions.kwargs["messages"][0]["role"], "system")

    def test_ollama_stream_complete_reads_line_delimited_responses(self):
        from bookmark_organizer_pro.ai import OllamaClient

        class FakeResponse:
            def raise_for_status(self):
                return None

            def iter_lines(self, decode_unicode=True):
                yield '{"response": "local"}'
                yield ""
                yield '{"response": " model"}'
                yield '{"done": true}'
                yield "not-json"

        class FakeRequests:
            kwargs = None

            @staticmethod
            def post(*args, **kwargs):
                FakeRequests.kwargs = kwargs
                return FakeResponse()

        with patch("bookmark_organizer_pro.ai.importlib.import_module", return_value=FakeRequests):
            client = OllamaClient("http://localhost:11434", "llama-test")
            chunks = list(client.stream_complete("prompt", system="system", max_tokens=25, temperature=0.1))

        self.assertTrue(client.supports_native_streaming)
        self.assertEqual(chunks, ["local", " model"])
        self.assertTrue(FakeRequests.kwargs["stream"])
        self.assertTrue(FakeRequests.kwargs["json"]["stream"])
        self.assertEqual(FakeRequests.kwargs["json"]["options"]["num_predict"], 25)


if __name__ == "__main__":
    unittest.main()
