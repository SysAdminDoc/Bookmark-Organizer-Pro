"""Tests for the robustness/security hardening pass.

Covers: XML control-char stripping, SSRF IP classification (mapped/NAT64),
CSV formula-injection guard, MCP constant-time token validation + scopes, and
CLI exit codes.
"""

from __future__ import annotations

import ipaddress
import tempfile
import unittest
from pathlib import Path


class TestXmlSafeText(unittest.TestCase):
    def test_strips_illegal_control_chars_keeps_valid(self):
        from bookmark_organizer_pro.utils.runtime import xml_safe_text

        # NUL and ESC are illegal in XML 1.0; tab/newline are legal.
        self.assertEqual(xml_safe_text("a\x00b\x1bc\tok\n"), "abc\tok\n")
        self.assertEqual(xml_safe_text("plain <title> & co"), "plain <title> & co")
        self.assertEqual(xml_safe_text("emoji \U0001F600 ok"), "emoji \U0001F600 ok")
        self.assertEqual(xml_safe_text(None), "")
        self.assertEqual(xml_safe_text(12345), "12345")

    def test_exporter_escapers_clean_control_chars(self):
        from bookmark_organizer_pro.io_formats.xbel import _escape_xml
        from bookmark_organizer_pro.services.feed_export import _esc

        self.assertNotIn("\x00", _escape_xml("bad\x00title"))
        self.assertNotIn("\x1b", _esc("bad\x1btitle"))
        # Still escapes XML metacharacters.
        self.assertIn("&lt;", _escape_xml("<tag>"))
        self.assertIn("&amp;", _esc("a & b"))


class TestSsrfIpClassification(unittest.TestCase):
    def setUp(self):
        from bookmark_organizer_pro.url_utils import URLUtilities
        self.U = URLUtilities

    def test_blocks_private_and_special_ranges(self):
        for addr in [
            "127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1",
            "169.254.169.254",          # cloud metadata / link-local
            "0.0.0.0", "::1",
            "::ffff:169.254.169.254",   # IPv4-mapped metadata
            "::ffff:127.0.0.1",         # IPv4-mapped loopback
        ]:
            self.assertTrue(self.U._ip_is_blocked(ipaddress.ip_address(addr)),
                            f"{addr} should be blocked")

    def test_allows_public_addresses(self):
        for addr in ["8.8.8.8", "1.1.1.1", "93.184.216.34"]:
            self.assertFalse(self.U._ip_is_blocked(ipaddress.ip_address(addr)),
                             f"{addr} should be allowed")

    def test_rejects_non_http_schemes(self):
        self.assertFalse(self.U._is_safe_url("file:///etc/passwd"))
        self.assertFalse(self.U._is_safe_url("ftp://example.com"))
        self.assertFalse(self.U._is_safe_url("javascript:alert(1)"))
        self.assertFalse(self.U._is_safe_url("http://localhost/"))


class TestCsvSafeCell(unittest.TestCase):
    def test_guards_formula_and_dde_prefixes(self):
        from bookmark_organizer_pro.utils.runtime import csv_safe_cell

        for danger in ("=1+1", "+1", "-1", "@SUM", "|cmd", "\tx", "\rx"):
            self.assertTrue(csv_safe_cell(danger).startswith("'"), danger)
        self.assertEqual(csv_safe_cell("normal"), "normal")
        self.assertEqual(csv_safe_cell(None), "")


class TestMcpTokenAuth(unittest.TestCase):
    def _manager(self):
        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager
        tmp = Path(tempfile.mkdtemp()) / "mcp_tokens.json"
        return MCPTokenManager(filepath=tmp)

    def test_validate_and_scopes(self):
        mgr = self._manager()
        rw = mgr.create_token("rw", scope="read-write")
        ro = mgr.create_token("ro", scope="read-only")

        # read-write may call a mutation; read-only may not.
        self.assertTrue(mgr.validate(rw, "delete_bookmark"))
        self.assertTrue(mgr.validate(ro, "list_bookmarks"))
        self.assertTrue(mgr.validate(ro, "list_reader_highlights"))
        self.assertTrue(mgr.validate(ro, "list_due_reader_reviews"))
        self.assertTrue(mgr.validate(ro, "export_reader_highlights"))
        self.assertFalse(mgr.validate(ro, "delete_bookmark"))
        self.assertFalse(mgr.validate(ro, "record_reader_review"))
        self.assertFalse(mgr.validate(ro, "update_reader_highlight_note"))

        # Unknown / empty tokens are rejected.
        self.assertFalse(mgr.validate("not-a-real-token", "list_bookmarks"))
        self.assertFalse(mgr.validate("", "list_bookmarks"))

        # Scope lookup.
        self.assertEqual(mgr.get_scope(rw), "read-write")
        self.assertEqual(mgr.get_scope(ro), "read-only")
        self.assertIsNone(mgr.get_scope("nope"))

    def test_revoked_token_is_rejected(self):
        mgr = self._manager()
        tok = mgr.create_token("temp", scope="read-write")
        self.assertTrue(mgr.validate(tok, "list_bookmarks"))
        self.assertTrue(mgr.revoke_token(tok))
        self.assertFalse(mgr.validate(tok, "list_bookmarks"))


class TestCliExitCodes(unittest.TestCase):
    def test_version_and_unknown_command_codes(self):
        from bookmark_organizer_pro.cli import main

        self.assertEqual(main(["--version"]), 0)
        self.assertEqual(main(["definitely-not-a-command"]), 2)


if __name__ == "__main__":
    unittest.main()
