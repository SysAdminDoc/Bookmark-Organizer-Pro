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


    def test_anthropic_stream_complete_yields_text_stream_deltas(self):
        from bookmark_organizer_pro.ai import AnthropicClient

        class FakeTextStream:
            """Simulates anthropic stream.text_stream iterable."""
            def __iter__(self):
                yield "hello"
                yield ""
                yield " world"

        class FakeStream:
            """Context manager that exposes a text_stream attribute."""
            def __enter__(self):
                self.text_stream = FakeTextStream()
                return self
            def __exit__(self, *args):
                pass

        class FakeMessages:
            def __init__(self):
                self.kwargs = None
            def stream(self, **kwargs):
                self.kwargs = kwargs
                return FakeStream()

        messages = FakeMessages()
        client = AnthropicClient("test-key", "claude-test")
        client._client = SimpleNamespace(messages=messages)

        chunks = list(client.stream_complete(
            "prompt", system="system", max_tokens=12, temperature=0.4
        ))

        self.assertTrue(client.supports_native_streaming)
        self.assertEqual(chunks, ["hello", " world"])
        self.assertEqual(messages.kwargs["model"], "claude-test")
        self.assertEqual(messages.kwargs["max_tokens"], 12)
        self.assertEqual(messages.kwargs["temperature"], 0.4)
        self.assertEqual(messages.kwargs["system"], "system")
        self.assertEqual(messages.kwargs["messages"][0]["role"], "user")

    def test_google_stream_complete_yields_chunk_text(self):
        from bookmark_organizer_pro.ai import GoogleClient

        class FakeStreamResponse:
            """Iterable of chunks with .text attributes."""
            def __iter__(self):
                yield SimpleNamespace(text="gemini")
                yield SimpleNamespace(text="")
                yield SimpleNamespace(text=" response")
                yield SimpleNamespace(text=None)

        class FakeGenerativeModel:
            def __init__(self):
                self.kwargs = None
            def generate_content(self, content, *, stream=False, **kwargs):
                self.kwargs = {"content": content, "stream": stream, **kwargs}
                if stream:
                    return FakeStreamResponse()
                return SimpleNamespace(text="non-streamed")

        model = FakeGenerativeModel()
        client = GoogleClient("test-key", "gemini-test")
        client._client = model

        chunks = list(client.stream_complete(
            "prompt", system="system", max_tokens=15, temperature=0.3
        ))

        self.assertTrue(client.supports_native_streaming)
        self.assertEqual(chunks, ["gemini", " response"])
        self.assertTrue(model.kwargs["stream"])
        gen_config = model.kwargs.get("generation_config", {})
        self.assertEqual(gen_config["max_output_tokens"], 15)
        self.assertEqual(gen_config["temperature"], 0.3)


if __name__ == "__main__":
    unittest.main()
