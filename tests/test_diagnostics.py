"""Diagnostics and support bundle tests."""

from __future__ import annotations

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
            self.assertIn("[REDACTED]", combined)
            self.assertIn('"bookmark_contents_included": false', combined)


if __name__ == "__main__":
    unittest.main()
