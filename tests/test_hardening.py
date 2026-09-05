"""Tests for the robustness/security hardening pass.

Covers: XML control-char stripping, SSRF IP classification (mapped/NAT64),
CSV formula-injection guard, MCP constant-time token validation + scopes, and
CLI exit codes.
"""

from __future__ import annotations

import faulthandler
import ipaddress
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_default_scope_is_least_privilege_and_invalid_scope_fails(self):
        mgr = self._manager()
        token = mgr.create_token("default")
        self.assertTrue(mgr.validate(token, "list_bookmarks"))
        self.assertFalse(mgr.validate(token, "delete_bookmark"))
        with self.assertRaises(ValueError):
            mgr.create_token("invalid", scope="admin")

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
        self.assertEqual(persisted["version"], 2)
        self.assertNotIn(token, persisted_text)
        self.assertEqual(len(persisted["document"]["credentials"]), 1)
        record = next(iter(persisted["document"]["credentials"].values()))
        self.assertEqual(len(bytes.fromhex(record["salt"])), 16)
        self.assertEqual(len(record["verifier"]), 64)
        self.assertNotIn("token", record)
        self.assertEqual(record["audience"], "mcp")
        self.assertEqual(record["scopes"], ["mcp:read"])
        self.assertEqual(len(record["fingerprint"]), 12)
        self.assertTrue(persisted["document"]["audit"])

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

    def test_schema_v1_verifiers_migrate_without_privilege_expansion(self):
        from bookmark_organizer_pro.services.atomic_document_store import (
            AtomicDocumentStore,
        )
        from bookmark_organizer_pro.services.mcp_auth import (
            MCP_READ_SCOPE,
            MCP_WRITE_SCOPE,
            MCPTokenManager,
        )

        path = Path(tempfile.mkdtemp()) / "mcp_tokens.json"
        read_token = "schema-v1-reader"
        write_token = "schema-v1-writer"
        read_id, read_record = MCPTokenManager._legacy_record(
            read_token,
            {"name": "reader", "scope": "read-only"},
        )
        write_id, write_record = MCPTokenManager._legacy_record(
            write_token,
            {"name": "writer", "scope": "read-write"},
        )
        AtomicDocumentStore(
            path,
            schema="mcp-token-verifiers",
            current_version=1,
        ).save({
            read_id: read_record,
            write_id: write_record,
        })

        migrated = MCPTokenManager(path)
        by_name = {
            item["name"]: item
            for item in migrated.list_credentials(audience="mcp")
        }
        self.assertEqual(by_name["reader"]["scopes"], [MCP_READ_SCOPE])
        self.assertEqual(
            by_name["writer"]["scopes"],
            [MCP_READ_SCOPE, MCP_WRITE_SCOPE],
        )
        self.assertFalse(migrated.validate(read_token, "delete_bookmark"))
        self.assertTrue(migrated.validate(write_token, "delete_bookmark"))
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["version"],
            2,
        )

    def test_named_rest_credential_tracks_scope_expiry_and_usage_without_secret(self):
        from bookmark_organizer_pro.services.mcp_auth import (
            REST_READ_SCOPE,
            REST_WRITE_SCOPE,
        )

        mgr = self._manager()
        created = mgr.create_credential(
            "Read-only dashboard",
            audience="rest",
            scopes=[REST_READ_SCOPE],
            expires_in_seconds=3600,
        )
        allowed = mgr.authorize(
            created.token,
            REST_READ_SCOPE,
            operation="GET /bookmarks",
            audience="rest",
        )
        denied = mgr.authorize(
            created.token,
            REST_WRITE_SCOPE,
            operation="POST /bookmarks",
            audience="rest",
        )

        self.assertTrue(allowed.allowed)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "insufficient_scope")
        listed = mgr.list_credentials(audience="rest")[0]
        self.assertEqual(listed["id"], created.identifier)
        self.assertEqual(listed["name"], "Read-only dashboard")
        self.assertEqual(listed["scopes"], [REST_READ_SCOPE])
        self.assertEqual(listed["fingerprint"], created.fingerprint)
        self.assertEqual(listed["successful_uses"], 1)
        self.assertEqual(listed["failed_uses"], 1)
        self.assertTrue(listed["created_at"])
        self.assertTrue(listed["last_used_at"])
        self.assertTrue(listed["last_failed_at"])
        self.assertTrue(listed["expires_at"])
        serialized = json.dumps(mgr.list_credentials()) + json.dumps(mgr.list_audit())
        self.assertNotIn(created.token, serialized)

    def test_expired_credential_fails_closed_and_is_audited(self):
        from bookmark_organizer_pro.services import mcp_auth

        mgr = self._manager()
        start = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        with mock.patch.object(mcp_auth, "_utc_now", return_value=start):
            token = mgr.create_token(
                "Temporary reader",
                expires_in_seconds=60,
            )
        with mock.patch.object(
            mcp_auth,
            "_utc_now",
            return_value=start + timedelta(seconds=61),
        ):
            self.assertFalse(mgr.validate(token, "list_bookmarks"))
            listed = mgr.list_credentials(audience="mcp")[0]
        self.assertEqual(listed["status"], "expired")
        self.assertEqual(listed["failed_uses"], 1)
        self.assertEqual(mgr.list_audit(limit=1)[0]["reason"], "credential_expired")

    def test_rotate_and_revoke_by_identifier_are_immediate(self):
        from bookmark_organizer_pro.services.mcp_auth import MCP_READ_SCOPE

        mgr = self._manager()
        original = mgr.create_credential(
            "Desktop client",
            audience="mcp",
            scopes=[MCP_READ_SCOPE],
        )
        rotated = mgr.rotate_credential(original.identifier)
        self.assertEqual(rotated.identifier, original.identifier)
        self.assertNotEqual(rotated.fingerprint, original.fingerprint)
        self.assertFalse(mgr.validate(original.token, "list_bookmarks"))
        self.assertTrue(mgr.validate(rotated.token, "list_bookmarks"))
        self.assertTrue(mgr.revoke_credential(rotated.identifier))
        self.assertFalse(mgr.validate(rotated.token, "list_bookmarks"))
        listed = mgr.list_credentials(audience="mcp")[0]
        self.assertEqual(listed["status"], "revoked")
        self.assertEqual(listed["rotation_count"], 1)
        self.assertTrue(mgr.has_credentials("mcp"))

    def test_invalid_attempt_audit_never_persists_attempted_secret(self):
        from bookmark_organizer_pro.services.mcp_auth import MCP_READ_SCOPE

        mgr = self._manager()
        attempted = "not-a-real-secret-value"
        result = mgr.authorize(
            attempted,
            MCP_READ_SCOPE,
            operation="mcp:list_bookmarks",
            audience="mcp",
        )
        self.assertFalse(result.allowed)
        event = mgr.list_audit(limit=1)[0]
        self.assertEqual(event["reason"], "invalid_credential")
        persisted = mgr.filepath.read_text(encoding="utf-8")
        self.assertNotIn(attempted, persisted)

    def test_legacy_rest_token_import_is_idempotent_and_preserves_privileges(self):
        from bookmark_organizer_pro.services.mcp_auth import (
            REST_EXTENSION_SCOPE,
            REST_READ_SCOPE,
            REST_WRITE_SCOPE,
        )

        mgr = self._manager()
        peer = type(mgr)(filepath=mgr.filepath)
        token = "legacy-rest-bearer"
        identifier = mgr.import_legacy_rest_token(token)
        self.assertEqual(identifier, peer.import_legacy_rest_token(token))
        credentials = mgr.list_credentials(audience="rest")
        self.assertEqual(len(credentials), 1)
        self.assertEqual(
            set(credentials[0]["scopes"]),
            {REST_READ_SCOPE, REST_WRITE_SCOPE, REST_EXTENSION_SCOPE},
        )
        self.assertTrue(
            mgr.authorize(
                token,
                REST_WRITE_SCOPE,
                operation="POST /bookmarks",
                audience="rest",
            ).allowed
        )
        rotated = mgr.rotate_credential(identifier)
        self.assertEqual(identifier, mgr.import_legacy_rest_token(token))
        self.assertFalse(
            mgr.authorize(
                token,
                REST_READ_SCOPE,
                operation="GET /bookmarks",
                audience="rest",
            ).allowed
        )
        self.assertTrue(
            mgr.authorize(
                rotated.token,
                REST_READ_SCOPE,
                operation="GET /bookmarks",
                audience="rest",
            ).allowed
        )
        self.assertTrue(mgr.revoke_credential(identifier))
        self.assertEqual(identifier, mgr.import_legacy_rest_token(token))
        self.assertFalse(
            mgr.authorize(
                rotated.token,
                REST_READ_SCOPE,
                operation="GET /bookmarks",
                audience="rest",
            ).allowed
        )

    def test_credential_audit_limit_validation_is_bounded(self):
        mgr = self._manager()
        token = mgr.create_token("Audit reader")
        mgr.validate(token, "list_bookmarks")
        self.assertEqual(len(mgr.list_audit(limit=10_000)), 2)
        with self.assertRaisesRegex(ValueError, "integer"):
            mgr.list_audit(limit=True)
        with self.assertRaisesRegex(ValueError, "integer"):
            mgr.list_audit(limit="many")

    def test_diagnostics_are_aggregate_and_content_free(self):
        mgr = self._manager()
        secret_name = "Private workstation name"
        token = mgr.create_token(secret_name)
        mgr.validate(token, "list_bookmarks")
        diagnostic_text = json.dumps(mgr.diagnostics())
        self.assertNotIn(secret_name, diagnostic_text)
        self.assertNotIn(token, diagnostic_text)
        self.assertEqual(mgr.diagnostics()["active"], 1)
        self.assertEqual(mgr.diagnostics()["successful_uses"], 1)

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
            self.assertEqual(
                len(json.loads(prior)["document"]["credentials"]),
                1,
            )
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])


class TestCliExitCodes(unittest.TestCase):
    def test_version_and_unknown_command_codes(self):
        from bookmark_organizer_pro.cli import main

        self.assertEqual(main(["--version"]), 0)
        self.assertEqual(main(["definitely-not-a-command"]), 2)


if __name__ == "__main__":
    unittest.main()


class TestCrashCapture(unittest.TestCase):
    """R-182: a crash after the UI starts must leave something readable."""

    def setUp(self):
        from bookmark_organizer_pro import logging_config

        self.logging_config = logging_config
        self._tmp = tempfile.mkdtemp(prefix="bop_crash_test_")
        self._log_file = Path(self._tmp) / "logs" / "bookmark_organizer.log"
        patcher = mock.patch.object(logging_config, "LOG_FILE", self._log_file)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    def _boom(self):
        try:
            raise ValueError("planted crash")
        except ValueError:
            return sys.exc_info()

    def test_a_crash_report_names_the_build_thread_and_traceback(self):
        exc_type, exc_value, exc_tb = self._boom()

        path = self.logging_config.write_crash_report(
            exc_type, exc_value, exc_tb, origin="tk-callback", thread_name="MainThread"
        )

        self.assertIsNotNone(path)
        report = path.read_text(encoding="utf-8")
        self.assertIn("planted crash", report)
        self.assertIn("ValueError", report)
        self.assertIn("origin: tk-callback", report)
        self.assertIn("thread: MainThread", report)
        self.assertIn("Traceback", report)

    def test_two_crashes_in_the_same_second_do_not_overwrite_each_other(self):
        exc_type, exc_value, exc_tb = self._boom()

        first = self.logging_config.write_crash_report(
            exc_type, exc_value, exc_tb, origin="main", thread_name="MainThread"
        )
        second = self.logging_config.write_crash_report(
            exc_type, exc_value, exc_tb, origin="main", thread_name="MainThread"
        )

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())

    def test_a_worker_thread_crash_is_recorded(self):
        """threading.excepthook, exercised for real rather than asserted about."""
        previous_sys, previous_thread = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", previous_sys)
        self.addCleanup(setattr, threading, "excepthook", previous_thread)
        self.logging_config.install_crash_handlers()

        def explode():
            raise RuntimeError("worker exploded")

        worker = threading.Thread(target=explode, name="planted-worker")
        worker.start()
        worker.join(timeout=10)

        reports = self.logging_config.latest_crash_reports()
        self.assertTrue(reports, "a worker-thread crash left no report")
        report = reports[0].read_text(encoding="utf-8")
        self.assertIn("worker exploded", report)
        self.assertIn("thread: planted-worker", report)
        self.assertIn("origin: thread", report)

    def test_a_tk_callback_crash_is_recorded_and_keeps_running(self):
        """The Tk reporter is called directly: constructing a root maps a window."""
        notified = []
        report_callback = self.logging_config.tk_exception_reporter(notify=notified.append)
        exc_type, exc_value, exc_tb = self._boom()

        result = report_callback(exc_type, exc_value, exc_tb)

        self.assertIsNone(result, "the reporter must return, not re-raise")
        reports = self.logging_config.latest_crash_reports()
        self.assertTrue(reports)
        self.assertIn("origin: tk-callback", reports[0].read_text(encoding="utf-8"))
        self.assertEqual([reports[0]], notified)

    def test_a_notifier_that_raises_does_not_replace_the_crash(self):
        def hostile(_path):
            raise RuntimeError("notifier exploded")

        report_callback = self.logging_config.tk_exception_reporter(notify=hostile)
        exc_type, exc_value, exc_tb = self._boom()

        report_callback(exc_type, exc_value, exc_tb)

        self.assertTrue(self.logging_config.latest_crash_reports())

    def test_keyboard_interrupt_is_not_a_crash(self):
        report_callback = self.logging_config.tk_exception_reporter()

        report_callback(KeyboardInterrupt, KeyboardInterrupt(), None)

        self.assertEqual([], self.logging_config.latest_crash_reports())

    def test_crash_reports_are_not_rotated_away_by_ordinary_logging(self):
        exc_type, exc_value, exc_tb = self._boom()
        path = self.logging_config.write_crash_report(
            exc_type, exc_value, exc_tb, origin="main", thread_name="MainThread"
        )

        # The rotating handler owns bookmark_organizer.log and its .1/.2/.3
        # backups. A crash file is not one of them.
        self.assertNotIn(path.name, {self._log_file.name} | {
            f"{self._log_file.name}.{index}" for index in range(1, 5)
        })
        self.assertTrue(path.name.startswith(self.logging_config.CRASH_FILE_PREFIX))

    def test_the_launcher_installs_every_hook(self):
        launcher = (
            Path(__file__).resolve().parents[1]
            / "bookmark_organizer_pro" / "launcher.py"
        ).read_text(encoding="utf-8")

        self.assertIn("install_crash_handlers()", launcher)
        # Once a window exists the handlers are replaced with notifying ones,
        # so a crash after startup reaches the user and not only the disk.
        self.assertIn("install_crash_handlers(notify=notify_crash)", launcher)
        self.assertIn(
            "root.report_callback_exception = tk_exception_reporter(notify=notify_crash)",
            launcher,
        )

    def test_the_launcher_wires_a_working_reporter_onto_the_real_root(self):
        """Driven, not grepped: renaming the local would pass a text search.

        A real ``tk.Tk()`` maps a window, so the root is a stand-in. What is
        under test is that the launcher assigns something onto
        ``report_callback_exception`` that records a crash when Tk calls it.
        """
        from bookmark_organizer_pro import launcher

        class FakeRoot:
            def __init__(self):
                self.report_callback_exception = None
                self.scheduled = []

            def withdraw(self):
                pass

            def after(self, _delay, callback):
                self.scheduled.append(callback)

            def winfo_fpixels(self, _spec):
                return 96.0

            def destroy(self):
                self.destroyed = True

        root = FakeRoot()
        # main() leaves through its own "dependencies are missing" path rather
        # than an exception: its exception handler calls messagebox.showerror,
        # and a test must not put a dialog on someone's screen.
        with mock.patch.object(launcher.tk, "Tk", lambda: root), \
             mock.patch.object(launcher, "_configure_tk_scaling", lambda _root: None), \
             mock.patch.object(launcher, "ensure_directories", lambda: None), \
             mock.patch.object(launcher, "setup_locale", lambda _value: None), \
             mock.patch.object(launcher, "setup_dpi_awareness", lambda: None), \
             mock.patch.object(launcher, "set_widget_window_chrome_provider", lambda _p: None), \
             mock.patch.object(launcher.style_manager, "initialize", lambda _root: None), \
             mock.patch.object(launcher, "check_and_install_dependencies", lambda _root: False), \
             mock.patch.object(launcher.messagebox, "showerror") as showerror, \
             mock.patch.object(launcher, "install_crash_handlers") as install:
            launcher.main([])

        showerror.assert_not_called()

        self.assertTrue(callable(root.report_callback_exception))
        install.assert_called_with(notify=mock.ANY)

        # The thing that was wired actually records a crash.
        with tempfile.TemporaryDirectory(prefix="bop_wired_") as tmp:
            from bookmark_organizer_pro import logging_config

            log_file = Path(tmp) / "logs" / "bookmark_organizer.log"
            with mock.patch.object(logging_config, "LOG_FILE", log_file):
                try:
                    raise ValueError("planted through the wired reporter")
                except ValueError:
                    root.report_callback_exception(*sys.exc_info())
                reports = logging_config.latest_crash_reports(directory=log_file.parent)

            self.assertTrue(reports, "the wired reporter recorded nothing")
            self.assertIn(
                "planted through the wired reporter",
                reports[0].read_text(encoding="utf-8"),
            )

    def test_the_crash_notice_is_marshalled_onto_the_tk_thread(self):
        """A worker-thread crash must not touch Tk from that thread."""
        from bookmark_organizer_pro import launcher

        scheduled = []

        class FakeRoot:
            def after(self, delay, callback):
                scheduled.append((delay, callback))

        launcher.crash_notifier(FakeRoot())(Path("crash-20260905-000000-1.log"))

        self.assertEqual(1, len(scheduled))
        self.assertEqual(0, scheduled[0][0])

    def test_a_dead_root_does_not_turn_a_crash_into_a_second_crash(self):
        from bookmark_organizer_pro import launcher

        class DeadRoot:
            def after(self, delay, callback):
                raise RuntimeError("main thread is not in main loop")

        launcher.crash_notifier(DeadRoot())(Path("crash-20260905-000000-1.log"))

    def test_install_wires_both_interpreter_hooks_and_faulthandler(self):
        previous_sys, previous_thread = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", previous_sys)
        self.addCleanup(setattr, threading, "excepthook", previous_thread)

        self.logging_config.install_crash_handlers()

        self.assertIsNot(sys.excepthook, previous_sys)
        self.assertIsNot(threading.excepthook, previous_thread)
        self.assertTrue(faulthandler.is_enabled())


class TestCrashReportsReachTheSupportBundle(unittest.TestCase):
    """A crash must survive into the bundle whole, not sampled like the log."""

    def test_the_bundle_includes_redacted_crash_reports(self):
        """The real lookup is used: a crash beside the log reaches the bundle."""
        from bookmark_organizer_pro.services import local_state

        with tempfile.TemporaryDirectory(prefix="bop_bundle_crash_") as tmp:
            log_file = Path(tmp) / "bookmark_organizer.log"
            log_file.write_text("2026-09-05 | INFO | BookmarkOrganizer | up\n", encoding="utf-8")
            crash = Path(tmp) / "crash-20260905-010203-1.log"
            crash.write_text(
                "app: Bookmark Organizer Pro 6.16.0\n"
                "origin: tk-callback\n"
                "thread: MainThread\n"
                "\n"
                "Traceback (most recent call last):\n"
                '  File "C:\\Users\\Alice\\app.py", line 7\n'
                "ValueError: owner=alice@example.test\n"
                "origin: alice@example.test\n",
                encoding="utf-8",
            )
            with mock.patch.object(local_state, "LOG_FILE", log_file):
                preview = local_state.build_support_bundle_preview()

        content = dict(preview.files)["crash_reports_redacted.txt"]
        self.assertIn(crash.name, content)
        # Whole, not tail-sampled: the header this build wrote survives intact.
        self.assertIn("origin: tk-callback", content)
        self.assertIn("app: Bookmark Organizer Pro 6.16.0", content)
        self.assertIn("exception_type=ValueError", content)
        # Redacted on the same terms as the log, and a header-shaped line below
        # the header cannot smuggle content past the redactor.
        self.assertNotIn("alice@example.test", content)
        self.assertNotIn(r"C:\Users\Alice", content)
        self.assertNotIn('File "', content)

    def test_no_crash_reports_still_produces_the_allowlisted_file(self):
        from bookmark_organizer_pro.services import local_state

        with tempfile.TemporaryDirectory(prefix="bop_bundle_nocrash_") as tmp:
            log_file = Path(tmp) / "bookmark_organizer.log"
            log_file.write_text("2026-09-05 | INFO | BookmarkOrganizer | up\n", encoding="utf-8")
            with mock.patch.object(local_state, "LOG_FILE", log_file):
                preview = local_state.build_support_bundle_preview()

        content = dict(preview.files)["crash_reports_redacted.txt"]
        self.assertEqual("No crash reports were recorded.", content)


class TestAForgedCrashFileCannotSmuggleContent(unittest.TestCase):
    """The reader finds crash files by glob, so the file is untrusted input."""

    def _bundle_text(self, tmp: str, name: str, body: str) -> str:
        from bookmark_organizer_pro.services import local_state

        log_file = Path(tmp) / "bookmark_organizer.log"
        log_file.write_text("2026-09-05 | INFO | BookmarkOrganizer | up\n", encoding="utf-8")
        (Path(tmp) / name).write_text(body, encoding="utf-8")
        with mock.patch.object(local_state, "LOG_FILE", log_file):
            preview = local_state.build_support_bundle_preview()
        return dict(preview.files)["crash_reports_redacted.txt"]

    def test_a_header_shaped_line_with_a_foreign_value_is_redacted(self):
        with tempfile.TemporaryDirectory(prefix="bop_forged_") as tmp:
            content = self._bundle_text(
                tmp,
                "crash-20260905-999999-1.log",
                "thread: password=hunter2 owner=alice@example.test\n"
                "origin: https://internal.corp/secret?token=abc\n"
                r"app: C:\Users\Alice\Documents\ssn-123-45-6789.txt" + "\n",
            )

        self.assertNotIn("hunter2", content)
        self.assertNotIn("alice@example.test", content)
        self.assertNotIn("internal.corp", content)
        self.assertNotIn("ssn-123-45-6789", content)
        self.assertNotIn(r"C:\Users\Alice", content)

    def test_a_genuine_header_still_passes_through(self):
        with tempfile.TemporaryDirectory(prefix="bop_genuine_") as tmp:
            content = self._bundle_text(
                tmp,
                "crash-20260905-010203-1.log",
                "app: Bookmark Organizer Pro 6.16.0\n"
                "when: 2026-09-05T01:02:03\n"
                "origin: tk-callback\n"
                "thread: MainThread\n"
                "python: 3.12.10 CPython\n"
                "platform: win32\n"
                "frozen: False\n",
            )

        self.assertIn("origin: tk-callback", content)
        self.assertIn("app: Bookmark Organizer Pro 6.16.0", content)
        self.assertIn("platform: win32", content)

    def test_a_hostile_filename_does_not_reach_the_bundle(self):
        with tempfile.TemporaryDirectory(prefix="bop_name_") as tmp:
            content = self._bundle_text(
                tmp,
                "crash-owner=alice@example.test.log",
                "origin: main\n",
            )

        self.assertNotIn("alice@example.test", content)
