"""Integration tests for MCP server tool functions.

Tests the pure tool implementations in mcp_server.py without requiring
the MCP protocol layer — exercises the data path end-to-end using
real managers and services.
"""

import os
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch


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
        result = self.ms.t_add_bookmark(url="https://new-bm.example.com", title="New BM")
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


if __name__ == "__main__":
    unittest.main()
