"""Tests for the robustness/security hardening pass.

Covers: XML control-char stripping, SSRF IP classification (mapped/NAT64),
CSV formula-injection guard, MCP constant-time token validation + scopes, and
CLI exit codes.
"""

from __future__ import annotations

import ipaddress
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

    def test_revocation_is_observed_by_an_existing_second_manager(self):
        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager

        owner = self._manager()
        token = owner.create_token("shared", scope="read-write")
        client = MCPTokenManager(filepath=owner.filepath)
        self.assertTrue(client.validate(token, "list_bookmarks"))
        self.assertTrue(owner.revoke_token(token))
        self.assertFalse(client.validate(token, "list_bookmarks"))

    def test_persists_only_salted_verifiers_and_reloads(self):
        mgr = self._manager()
        token = mgr.create_token("desktop client", scope="read-only")

        persisted_text = mgr.filepath.read_text(encoding="utf-8")
        persisted = json.loads(persisted_text)
        self.assertEqual(persisted["schema"], "mcp-token-verifiers")
        self.assertEqual(persisted["version"], 1)
        self.assertNotIn(token, persisted_text)
        self.assertEqual(len(persisted["document"]), 1)
        record = next(iter(persisted["document"].values()))
        self.assertEqual(len(bytes.fromhex(record["salt"])), 16)
        self.assertEqual(len(record["verifier"]), 64)
        self.assertNotIn("token", record)

        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager
        reloaded = MCPTokenManager(filepath=mgr.filepath)
        self.assertTrue(reloaded.validate(token, "list_bookmarks"))
        self.assertFalse(reloaded.validate(token, "delete_bookmark"))

    def test_legacy_raw_tokens_migrate_without_lockout(self):
        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager

        path = Path(tempfile.mkdtemp()) / "mcp_tokens.json"
        legacy_token = "legacy-bearer-secret"
        path.write_text(json.dumps({
            legacy_token: {
                "name": "legacy client",
                "scope": "read-only",
                "created_at": "2026-01-01T00:00:00",
            },
        }), encoding="utf-8")

        mgr = MCPTokenManager(filepath=path)
        self.assertTrue(mgr.validate(legacy_token, "list_bookmarks"))
        self.assertFalse(mgr.validate(legacy_token, "delete_bookmark"))
        self.assertNotIn(legacy_token, path.read_text(encoding="utf-8"))
        self.assertNotIn(legacy_token, Path(f"{path}.bak").read_text(encoding="utf-8"))
        self.assertEqual(mgr.list_tokens()[0]["name"], "legacy client")
        self.assertTrue(mgr.revoke_token(legacy_token))

    def test_failed_legacy_migration_write_keeps_token_usable(self):
        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager

        path = Path(tempfile.mkdtemp()) / "mcp_tokens.json"
        legacy_token = "legacy-token-with-read-write-scope"
        path.write_text(json.dumps({legacy_token: {
            "name": "legacy",
            "scope": "read-write",
        }}), encoding="utf-8")

        with mock.patch(
            "bookmark_organizer_pro.services.atomic_document_store.AtomicDocumentStore._write_locked",
            side_effect=OSError("read only"),
        ):
            mgr = MCPTokenManager(filepath=path)
            self.assertTrue(mgr.validate(legacy_token, "delete_bookmark"))

    @unittest.skipIf(os.name == "nt", "POSIX mode assertion")
    def test_token_file_is_user_only_on_posix(self):
        mgr = self._manager()
        mgr.create_token("permissions")
        self.assertEqual(stat.S_IMODE(mgr.filepath.stat().st_mode), 0o600)

    def test_windows_acl_restricts_inheritance_to_current_user(self):
        from bookmark_organizer_pro.services.private_files import restrict_private_file

        completed = mock.Mock(returncode=0)
        with (
            mock.patch.dict(os.environ, {"USERNAME": "TestUser"}),
            mock.patch(
                "bookmark_organizer_pro.services.private_files._platform_name",
                return_value="nt",
            ),
            mock.patch(
                "bookmark_organizer_pro.services.private_files.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            restrict_private_file(Path("mcp_tokens.tmp"))
        self.assertEqual(
            run.call_args.args[0],
            [
                "icacls", "mcp_tokens.tmp", "/inheritance:r",
                "/grant:r", "TestUser:(F)",
            ],
        )

    def test_corrupt_verifier_store_does_not_enable_open_mode(self):
        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager

        path = Path(tempfile.mkdtemp()) / "mcp_tokens.json"
        path.write_text("{not-json", encoding="utf-8")
        mgr = MCPTokenManager(filepath=path)
        self.assertTrue(mgr.list_tokens())
        self.assertFalse(mgr.validate("anything", "list_bookmarks"))


class TestPrivateCredentialPersistence(unittest.TestCase):
    class _UnavailableKeyring:
        @staticmethod
        def get_password(*_args):
            raise RuntimeError("keyring unavailable")

        @staticmethod
        def set_password(*_args):
            raise RuntimeError("keyring unavailable")

    def _acl_context(self, *results):
        return (
            mock.patch.dict(os.environ, {"USERNAME": "TestUser"}),
            mock.patch(
                "bookmark_organizer_pro.services.private_files._platform_name",
                return_value="nt",
            ),
            mock.patch(
                "bookmark_organizer_pro.services.private_files.subprocess.run",
                side_effect=list(results),
            ),
        )

    def test_missing_icacls_removes_plaintext_temp_and_preserves_prior(self):
        from bookmark_organizer_pro.services.private_files import (
            PrivateFilePermissionError,
            atomic_write_private_text,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential.txt"
            path.write_text("prior-secret", encoding="utf-8")
            environment, platform, runner = self._acl_context(FileNotFoundError("icacls"))
            with environment, platform, runner, self.assertRaises(PrivateFilePermissionError) as raised:
                atomic_write_private_text(path, "new-secret")
            self.assertIn("not published", str(raised.exception))
            self.assertEqual(path.read_text(encoding="utf-8"), "prior-secret")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_api_token_windows_acl_success_and_failure(self):
        import bookmark_organizer_pro.services.api as api
        from bookmark_organizer_pro.services.private_files import PrivateFilePermissionError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_token.txt"
            with (
                mock.patch.object(api, "_TOKEN_FILE", path),
                mock.patch.dict(sys.modules, {"keyring": self._UnavailableKeyring()}),
                mock.patch.object(api.secrets, "token_urlsafe", return_value="generated-api-token"),
            ):
                environment, platform, runner = self._acl_context(mock.Mock(returncode=0))
                with environment, platform, runner:
                    self.assertEqual(api._load_or_create_token(), "generated-api-token")
                self.assertEqual(path.read_text(encoding="utf-8"), "generated-api-token")

                path.write_text("\n", encoding="utf-8")
                environment, platform, runner = self._acl_context(mock.Mock(returncode=5))
                with environment, platform, runner, self.assertRaises(PrivateFilePermissionError):
                    api._load_or_create_token()
                self.assertEqual(path.read_text(encoding="utf-8"), "\n")
                self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_ai_config_windows_acl_success_and_failure(self):
        from bookmark_organizer_pro.ai import AIConfigManager
        from bookmark_organizer_pro.services.private_files import PrivateFilePermissionError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_config.json"
            manager = AIConfigManager(filepath=path)
            manager._config.setdefault("api_keys", {})["google"] = "first-secret"
            environment, platform, runner = self._acl_context(mock.Mock(returncode=0))
            with environment, platform, runner:
                manager.save_config()
            prior = path.read_bytes()

            manager._config["api_keys"]["google"] = "replacement-secret"
            environment, platform, runner = self._acl_context(mock.Mock(returncode=5))
            with environment, platform, runner, self.assertRaises(PrivateFilePermissionError):
                manager.save_config()
            self.assertEqual(path.read_bytes(), prior)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_mcp_verifier_windows_acl_success_and_failure(self):
        from bookmark_organizer_pro.services.mcp_auth import MCPTokenManager
        from bookmark_organizer_pro.services.private_files import PrivateFilePermissionError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp_tokens.json"
            manager = MCPTokenManager(filepath=path)
            environment, platform, runner = self._acl_context(mock.Mock(returncode=0))
            with environment, platform, runner:
                first_token = manager.create_token("first")
            prior = path.read_bytes()
            self.assertNotIn(first_token, prior.decode("utf-8"))

            environment, platform, runner = self._acl_context(
                mock.Mock(returncode=0),
                mock.Mock(returncode=5),
            )
            with environment, platform, runner, self.assertRaises(PrivateFilePermissionError):
                manager.create_token("must-not-publish")
            self.assertEqual(path.read_bytes(), prior)
            self.assertEqual(len(json.loads(prior)["document"]), 1)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])


class TestCliExitCodes(unittest.TestCase):
    def test_version_and_unknown_command_codes(self):
        from bookmark_organizer_pro.cli import main

        self.assertEqual(main(["--version"]), 0)
        self.assertEqual(main(["definitely-not-a-command"]), 2)


if __name__ == "__main__":
    unittest.main()
