"""Diagnostics and support bundle tests."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bookmark_organizer_pro.services import local_state


class TestDiagnosticsSupportBundle(unittest.TestCase):
    def test_redact_text_removes_common_secret_shapes(self):
        raw = "\n".join([
            "Authorization: Bearer abc.def.ghi",
            "api_key=sk-live-secret",
            '"token": "plain-token"',
            "url=https://example.com?token=query-secret",
        ])

        redacted = local_state.redact_text(raw)

        self.assertNotIn("abc.def.ghi", redacted)
        self.assertNotIn("sk-live-secret", redacted)
        self.assertNotIn("plain-token", redacted)
        self.assertNotIn("query-secret", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_redact_text_pseudonymizes_encoded_content_urls_users_and_paths(self):
        encoded_title = base64.b64encode(b"Private bookmark title").decode("ascii")
        raw = "\n".join([
            "title='Private bookmark title'",
            'content: "Confidential page fragment"',
            r"C:\Users\Alice\Documents\bookmarks.json",
            "/home/bob/private/library.json",
            "owner=alice@example.test",
            "https://alice:password@example.com/private/path?token=query#fragment",
            "password:\n hunter2",
            r"token=\u0073\u0065\u0063\u0072\u0065\u0074",
            f"encoded={encoded_title}",
        ])

        redacted = local_state.redact_text(
            raw,
            pseudonym_key=b"test-key",
        )

        for forbidden in (
            "Private bookmark title",
            "Confidential page fragment",
            "Alice",
            "/home/bob",
            "alice@example.test",
            "/private/path",
            "query",
            "fragment",
            "hunter2",
            "secret",
            encoded_title,
        ):
            self.assertNotIn(forbidden, redacted)
        self.assertIn("[CONTENT:", redacted)
        self.assertIn("[LOCAL_PATH:", redacted)
        self.assertIn("[EMAIL:", redacted)
        self.assertIn("[URL:", redacted)
        self.assertIn("[ENCODED_VALUE]", redacted)

    def test_support_bundle_excludes_bookmark_content_and_redacts_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_file = root / "logs" / "bookmark_organizer.log"
            log_file.parent.mkdir(parents=True)
            log_file.write_text(
                "2026-06-27 | ERROR | BookmarkOrganizer | Authorization: Bearer secret-token\n"
                "2026-06-27 | INFO | BookmarkOrganizer | api_key=secret-key\n",
                encoding="utf-8",
            )
            bookmarks = root / "master_bookmarks.json"
            bookmarks.write_text(json.dumps([{"title": "Private bookmark title"}]), encoding="utf-8")
            settings = root / "settings.json"
            settings.write_text(json.dumps({"apiToken": "secret-settings-token"}), encoding="utf-8")
            bundle = root / "support.zip"

            with patch.object(local_state, "LOG_FILE", log_file), \
                    patch.object(local_state, "MASTER_BOOKMARKS_FILE", bookmarks), \
                    patch.object(local_state, "SETTINGS_FILE", settings), \
                    patch.object(local_state, "SUPPORT_BUNDLES_DIR", root):
                bundle_path = local_state.export_redacted_support_bundle(bundle)
                summary = local_state.format_diagnostics(local_state.build_diagnostics_snapshot())

            self.assertEqual(bundle, bundle_path)
            self.assertNotIn("Private bookmark title", summary)
            self.assertNotIn("secret-token", summary)
            self.assertIn("bookmark contents excluded", summary)

            with zipfile.ZipFile(bundle_path) as archive:
                names = set(archive.namelist())
                self.assertEqual(
                    {"diagnostics.json", "diagnostics.txt", "recent_log_redacted.txt", "README.txt"},
                    names,
                )
                combined = "\n".join(archive.read(name).decode("utf-8") for name in sorted(names))

            self.assertNotIn("Private bookmark title", combined)
            self.assertNotIn("secret-token", combined)
            self.assertNotIn("secret-key", combined)
            self.assertNotIn("secret-settings-token", combined)
            self.assertIn("[REDACTED:", combined)
            self.assertIn('"bookmark_contents_included": false', combined)
            self.assertIn('"free_form_log_messages_included": false', combined)

    def test_preview_is_exact_allowlisted_payload_and_host_retention_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_file = root / "bookmark_organizer.log"
            private_title = "Quarterly acquisition target"
            encoded = base64.b64encode(b"encoded-secret-fragment").decode("ascii")
            log_file.write_text(
                "2026-07-29 18:03:04 | ERROR | BookmarkOrganizer | "
                f"title={private_title} owner=alice@example.test "
                "GET https://user:pw@docs.example.test/private/report?"
                f"token=secret#fragment file=C:\\Users\\Alice\\report.txt {encoded} "
                "ValueError\n"
                "Traceback (most recent call last):\n"
                "  File \"C:\\Users\\Alice\\app.py\", line 7\n",
                encoding="utf-8",
            )
            destination = root / "support.zip"
            with patch.object(local_state, "LOG_FILE", log_file), \
                    patch.object(local_state, "MASTER_BOOKMARKS_FILE", root / "bookmarks.json"), \
                    patch.object(local_state, "SETTINGS_FILE", root / "settings.json"), \
                    patch(
                        "bookmark_organizer_pro.services.job_ledger.JobLedger.health",
                        return_value={},
                    ):
                private_preview = local_state.build_support_bundle_preview()
                host_preview = local_state.build_support_bundle_preview(
                    retain_url_hosts=True
                )
                exported = local_state.export_redacted_support_bundle(
                    destination,
                    preview=host_preview,
                )

            private_text = private_preview.render()
            host_text = host_preview.render()
            for text in (private_text, host_text):
                for forbidden in (
                    private_title,
                    "alice@example.test",
                    "/private/report",
                    "token=secret",
                    "#fragment",
                    "encoded-secret-fragment",
                    r"C:\Users\Alice",
                    encoded,
                ):
                    self.assertNotIn(forbidden, text)
                self.assertIn("[REDACTED:", text)
                self.assertNotIn("File \"", text)

            self.assertNotIn("docs.example.test", private_text)
            self.assertIn("url_hosts=docs.example.test", host_text)
            self.assertEqual(
                tuple(name for name, _content in host_preview.files),
                (
                    "diagnostics.json",
                    "diagnostics.txt",
                    "recent_log_redacted.txt",
                    "README.txt",
                ),
            )

            with zipfile.ZipFile(exported) as archive:
                archived = {
                    name: archive.read(name).decode("utf-8")
                    for name in archive.namelist()
                }
            self.assertEqual(archived, host_preview.as_dict())

    def test_diagnostics_schema_contains_only_allowlisted_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(local_state, "LOG_FILE", root / "missing.log"), \
                    patch.object(local_state, "MASTER_BOOKMARKS_FILE", root / "bookmarks.json"), \
                    patch.object(local_state, "SETTINGS_FILE", root / "settings.json"):
                snapshot = local_state.build_diagnostics_snapshot()

        self.assertEqual(
            set(snapshot),
            {
                "schema",
                "schema_version",
                "generated_at",
                "application",
                "dependencies",
                "data_files",
                "recent_errors",
                "job_health",
                "processing_health",
                "credential_health",
                "privacy",
            },
        )
        self.assertEqual(
            set(snapshot["application"]),
            {"name", "version", "python", "platform", "architecture"},
        )
        self.assertEqual(
            set(snapshot["data_files"]),
            {"bookmarks", "settings", "log"},
        )
        for metadata in snapshot["data_files"].values():
            self.assertEqual(
                set(metadata),
                {"exists", "size_bytes", "modified"},
            )
        self.assertEqual(
            set(snapshot["privacy"]),
            {
                "bookmark_contents_included",
                "free_form_log_messages_included",
                "secrets_redacted",
                "url_hosts_included",
                "recent_log_lines",
            },
        )


if __name__ == "__main__":
    unittest.main()
