"""Integration tests for MCP server tool functions.

Tests the pure tool implementations in mcp_server.py without requiring
the MCP protocol layer — exercises the data path end-to-end using
real managers and services.
"""

import os
import asyncio
import json
import re
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class MCPToolTestBase(unittest.TestCase):
    """Base with isolated data directory so tests don't touch real bookmarks."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="bop_mcp_test_")
        os.environ["BOOKMARK_DATA_DIR"] = cls._tmp

        import importlib
        import bookmark_organizer_pro.constants as _c
        importlib.reload(_c)
        _c.ensure_directories()

        import bookmark_organizer_pro.mcp_server as _ms
        importlib.reload(_ms)
        cls.ms = _ms

        cls.ms.SERVICES = None

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("BOOKMARK_DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def setUp(self):
        self.ms.SERVICES = None


class TestListBookmarks(MCPToolTestBase):
    def test_list_returns_list(self):
        result = self.ms.t_list_bookmarks()
        self.assertIsInstance(result, list)

    def test_add_and_list(self):
        added = self.ms.t_add_bookmark(url="https://example.com/mcp-test", title="MCP Test")
        self.assertIsNotNone(added)
        self.assertIn("id", added)

        result = self.ms.t_list_bookmarks(limit=10)
        self.assertGreaterEqual(len(result), 1)
        urls = [b["url"] for b in result]
        self.assertTrue(any("example.com" in u for u in urls))


class TestGetBookmark(MCPToolTestBase):
    def test_not_found(self):
        result = self.ms.t_get_bookmark(bookmark_id=999999999)
        self.assertIsNone(result)

    def test_found(self):
        added = self.ms.t_add_bookmark(url="https://get-test.example.com", title="Get Test")
        self.assertIsNotNone(added)
        bm_id = added["id"]

        result = self.ms.t_get_bookmark(bookmark_id=bm_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], bm_id)
        self.assertIn("get-test.example.com", result["url"])


class TestSearch(MCPToolTestBase):
    def test_keyword_search(self):
        self.ms.t_add_bookmark(url="https://searchtest.example.com", title="Unique SearchMarker Title")
        result = self.ms.t_search(query="SearchMarker", limit=5)
        self.assertIsInstance(result, list)

    def test_empty_query(self):
        result = self.ms.t_search(query="", limit=5)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)


class TestAddBookmark(MCPToolTestBase):
    def test_add_new(self):
        import uuid
        unique_url = f"https://new-bm-{uuid.uuid4().hex[:8]}.example.com"
        result = self.ms.t_add_bookmark(url=unique_url, title="New BM")
        self.assertIsNotNone(result)
        self.assertFalse(result.get("already_exists", False))

    def test_duplicate_returns_existing(self):
        self.ms.t_add_bookmark(url="https://dup.example.com", title="Dup")
        result = self.ms.t_add_bookmark(url="https://dup.example.com", title="Dup Again")
        self.assertIsNotNone(result)
        self.assertTrue(result.get("already_exists", False))


class TestTags(MCPToolTestBase):
    def test_list_tags(self):
        result = self.ms.t_list_tags(limit=10)
        self.assertIsInstance(result, list)


class TestCategories(MCPToolTestBase):
    def test_list_categories(self):
        result = self.ms.t_list_categories()
        self.assertIsInstance(result, list)


class TestFlows(MCPToolTestBase):
    def test_create_and_list(self):
        flow = self.ms.t_create_flow(name="Test Flow", description="A test")
        self.assertIn("id", flow)
        self.assertEqual(flow["name"], "Test Flow")

        flows = self.ms.t_list_flows()
        self.assertGreaterEqual(len(flows), 1)
        names = [f["name"] for f in flows]
        self.assertIn("Test Flow", names)

    def test_append_to_flow(self):
        flow = self.ms.t_create_flow(name="Append Test")
        bm = self.ms.t_add_bookmark(url="https://flow-bm.example.com", title="Flow BM")
        self.assertIsNotNone(bm)

        result = self.ms.t_append_to_flow(flow_id=flow["id"], bookmark_id=bm["id"], note="Step note")
        self.assertNotIn("error", result)
        self.assertGreaterEqual(len(result.get("steps", [])), 1)

    def test_get_flow(self):
        flow = self.ms.t_create_flow(name="Get Flow Test")
        result = self.ms.t_get_flow(flow_id=flow["id"])
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Get Flow Test")

    def test_get_nonexistent_flow(self):
        result = self.ms.t_get_flow(flow_id="nonexistent")
        self.assertIsNone(result)


class TestDigest(MCPToolTestBase):
    def test_daily_digest(self):
        result = self.ms.t_daily_digest()
        self.assertIn("sections", result)
        self.assertIn("generated_at", result)


class TestChatStreaming(MCPToolTestBase):
    def _fake_services(self, bookmarks=None, provider_streaming=False):
        from types import SimpleNamespace
        from bookmark_organizer_pro.services.rag_chat import (
            ChatStreamResult,
            ChatTurn,
            build_chat_stream_events,
        )

        class FakeChat:
            def __init__(self):
                self.calls = []

            def stream_answer(self, question, restrict_ids=None, chunk_chars=160, use_cache=True):
                self.calls.append({
                    "question": question,
                    "restrict_ids": restrict_ids,
                    "chunk_chars": chunk_chars,
                    "use_cache": use_cache,
                })
                turn = ChatTurn(
                    answer=(
                        "Alpha beta gamma delta epsilon zeta eta theta iota kappa "
                        "lambda mu nu xi omicron."
                    ),
                    sources=[{"bookmark_id": 7, "score": 0.9}],
                    used_chunks=1,
                    chunk_provenance=[{"citation_id": "c0", "bookmark_id": 7}],
                )
                return ChatStreamResult(
                    turn,
                    build_chat_stream_events(turn, chunk_chars),
                    provider_streaming=provider_streaming,
                )

        class FakeBookmarkManager:
            def get_all_bookmarks(self):
                return bookmarks or []

        return SimpleNamespace(chat=FakeChat(), bookmark_manager=FakeBookmarkManager())

    def test_chat_stream_returns_ordered_response_events(self):
        services = self._fake_services()
        self.ms.SERVICES = services

        result = self.ms.t_chat_stream("What matters?", chunk_chars=10)

        self.assertEqual(result["mode"], "chunked_response_events")
        self.assertFalse(result["provider_streaming"])
        self.assertTrue(result["done"])
        self.assertEqual(result["chunk_chars"], 40)
        chunks = [event for event in result["events"] if event["type"] == "chunk"]
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(event["text"] for event in chunks), result["answer"])
        self.assertEqual(result["events"][-1]["type"], "complete")
        self.assertEqual(result["events"][-1]["sources"], result["sources"])
        self.assertEqual(result["events"][-1]["chunk_provenance"], result["chunk_provenance"])
        self.assertEqual(services.chat.calls[0]["restrict_ids"], None)

    def test_chat_stream_surfaces_provider_streaming_mode(self):
        services = self._fake_services(provider_streaming=True)
        self.ms.SERVICES = services

        result = self.ms.t_chat_stream("What matters?", chunk_chars=80)

        self.assertEqual(result["mode"], "provider_stream_events")
        self.assertTrue(result["provider_streaming"])

    def test_chat_stream_uses_same_tag_category_scope_as_chat(self):
        from types import SimpleNamespace

        bookmarks = [
            SimpleNamespace(id=1, tags=["Research"], category="Docs"),
            SimpleNamespace(id=2, tags=["research"], category="Inbox"),
            SimpleNamespace(id=3, tags=["Other"], category="Docs"),
        ]
        services = self._fake_services(bookmarks=bookmarks)
        self.ms.SERVICES = services

        result = self.ms.t_chat_stream(
            "Scoped?",
            restrict_ids=[1, 2, 3],
            restrict_tag="research",
            restrict_category="docs",
            chunk_chars=120,
        )

        self.assertTrue(result["done"])
        self.assertEqual(services.chat.calls[0]["restrict_ids"], [1])


class TestDeadLinks(MCPToolTestBase):
    def test_list_dead_links(self):
        result = self.ms.t_dead_links()
        self.assertIsInstance(result, list)


class TestListSnapshots(MCPToolTestBase):
    def test_empty(self):
        result = self.ms.t_list_snapshots()
        self.assertIsInstance(result, list)


class TestExportZip(MCPToolTestBase):
    def test_not_found(self):
        result = self.ms.t_export_zip(bookmark_id=999999999)
        self.assertIn("error", result)


class TestToolsSchema(MCPToolTestBase):
    def test_all_tools_have_four_fields(self):
        for entry in self.ms.TOOLS:
            self.assertEqual(len(entry), 4, f"Tool entry missing fields: {entry[0]}")
            name, fn, desc, schema = entry
            self.assertIsInstance(name, str)
            self.assertTrue(callable(fn))
            self.assertIsInstance(desc, str)
            self.assertIsInstance(schema, dict)
            self.assertEqual(schema.get("type"), "object")

    def test_no_duplicate_tool_names(self):
        names = [t[0] for t in self.ms.TOOLS]
        self.assertEqual(len(names), len(set(names)), f"Duplicate tool names: {names}")


class TestMCPRuntimeCompatibility(MCPToolTestBase):
    def test_fastmcp_builder_available_with_declared_dependency(self):
        app = self.ms._build_fastmcp_server()
        self.assertIsNotNone(app)
        self.assertEqual(type(app).__name__, "FastMCP")

    def test_mcp_dependency_floors_are_declared(self):
        pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        requirements_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertRegex(pyproject_text, re.compile(r'"mcp>=1\.24,<2\.0"'))
        self.assertRegex(pyproject_text, re.compile(r'"fastmcp>=3\.4,<4\.0"'))
        self.assertIn("mcp>=1.24,<2", requirements_text)
        self.assertIn("fastmcp>=3.4,<4", requirements_text)

    def test_raw_mcp_tools_result_has_cache_hints_and_annotations(self):
        import mcp.types as types

        result = self.ms._build_mcp_tools_result(types)
        payload = result.model_dump(by_alias=True, exclude_none=True)
        tools = {tool["name"]: tool for tool in payload["tools"]}

        self.assertEqual(payload["ttlMs"], self.ms.MCP_TOOL_LIST_TTL_MS)
        self.assertEqual(payload["cacheScope"], self.ms.MCP_TOOL_LIST_CACHE_SCOPE)
        self.assertTrue(tools["list_bookmarks"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["delete_bookmark"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["delete_bookmark"]["annotations"]["destructiveHint"])
        self.assertTrue(tools["chat_with_collection_stream"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["chat_with_collection_stream"]["annotations"]["openWorldHint"])
        self.assertEqual(
            tools["chat_with_collection_stream"]["_meta"]["io.modelcontextprotocol/name"],
            "chat_with_collection_stream",
        )
        self.assertTrue(tools["list_bookmarks"]["_meta"]["io.modelcontextprotocol/statelessReady"])
        self.assertEqual(tools["list_bookmarks"]["_meta"]["io.modelcontextprotocol/method"], "tools/call")
        self.assertEqual(tools["list_bookmarks"]["_meta"]["io.modelcontextprotocol/name"], "list_bookmarks")

    def test_fastmcp_tools_result_has_cache_hints_and_annotations(self):
        from mcp.types import ListToolsRequest

        async def _payload():
            app = self.ms._build_fastmcp_server()
            handler = app._mcp_server.request_handlers[ListToolsRequest]
            result = await handler(ListToolsRequest(method="tools/list"))
            return result.root.model_dump(by_alias=True, exclude_none=True)

        payload = asyncio.run(_payload())
        tools = {tool["name"]: tool for tool in payload["tools"]}

        self.assertEqual(payload["ttlMs"], self.ms.MCP_TOOL_LIST_TTL_MS)
        self.assertEqual(payload["cacheScope"], self.ms.MCP_TOOL_LIST_CACHE_SCOPE)
        self.assertTrue(tools["list_bookmarks"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["delete_bookmark"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["delete_bookmark"]["annotations"]["destructiveHint"])
        self.assertTrue(tools["chat_with_collection_stream"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["chat_with_collection_stream"]["annotations"]["openWorldHint"])
        self.assertEqual(
            tools["chat_with_collection_stream"]["_meta"]["io.modelcontextprotocol/name"],
            "chat_with_collection_stream",
        )
        self.assertTrue(tools["list_bookmarks"]["_meta"]["io.modelcontextprotocol/statelessReady"])
        self.assertEqual(tools["list_bookmarks"]["_meta"]["io.modelcontextprotocol/method"], "tools/call")
        self.assertEqual(tools["list_bookmarks"]["_meta"]["io.modelcontextprotocol/name"], "list_bookmarks")

    def test_serve_http_requires_fastmcp(self):
        with patch.object(self.ms, "_build_fastmcp_server", return_value=None):
            self.assertEqual(self.ms.serve_http(), 1)

    def test_serve_http_uses_streamable_http_stateless_options(self):
        class FakeApp:
            def __init__(self):
                self.calls = []

            def run(self, **kwargs):
                self.calls.append(kwargs)

        app = FakeApp()
        with patch.object(self.ms, "_build_fastmcp_server", return_value=app):
            self.assertEqual(self.ms.serve_http(host="127.0.0.1", port=9011, path="mcp"), 0)

        self.assertEqual(len(app.calls), 1)
        call = app.calls[0]
        self.assertEqual({
            key: call[key]
            for key in ("transport", "host", "port", "path", "stateless_http")
        }, {
            "transport": "http",
            "host": "127.0.0.1",
            "port": 9011,
            "path": "/mcp",
            "stateless_http": True,
        })
        self.assertEqual(len(call["middleware"]), 1)

    def test_http_header_validation_rejects_mismatched_name(self):
        sent = []

        async def app(scope, receive, send):
            sent.append({"type": "downstream"})

        middleware = self.ms.MCPHTTPHeaderValidationMiddleware(app)
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_bookmarks", "arguments": {}},
        }).encode("utf-8")
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"mcp-method", b"tools/call"), (b"mcp-name", b"wrong")],
        }

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(middleware(scope, receive, send))

        self.assertEqual(sent[0]["status"], 400)
        self.assertNotIn({"type": "downstream"}, sent)

    def test_http_header_validation_replays_valid_body(self):
        seen = {}

        async def app(scope, receive, send):
            message = await receive()
            seen["body"] = message["body"]
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        middleware = self.ms.MCPHTTPHeaderValidationMiddleware(app)
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_bookmarks", "arguments": {}},
        }).encode("utf-8")
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"mcp-method", b"tools/call"), (b"mcp-name", b"list_bookmarks")],
        }
        sent = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(middleware(scope, receive, send))

        self.assertEqual(seen["body"], body)
        self.assertEqual(sent[0]["status"], 200)


if __name__ == "__main__":
    unittest.main()
