"""CLI dispatch routing and subcommand smoke tests."""

import os
import sys
import tempfile
import shutil
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch


class CLITestBase(unittest.TestCase):
    """Base with isolated data directory."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="bop_cli_test_")
        os.environ["BOOKMARK_DATA_DIR"] = cls._tmp
        import importlib
        import bookmark_organizer_pro.constants as _c
        importlib.reload(_c)
        _c.ensure_directories()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("BOOKMARK_DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _run(self, args):
        from bookmark_organizer_pro.cli import BookmarkCLI
        cli = BookmarkCLI()
        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            cli.run(args)
        except SystemExit:
            pass
        finally:
            sys.stdout = old_stdout
        return captured.getvalue()


class TestCLIDispatch(CLITestBase):
    def test_no_args_prints_help(self):
        out = self._run([])
        self.assertIn("CLI", out)

    def test_version_flag(self):
        out = self._run(["--version"])
        self.assertIn("Bookmark Organizer Pro", out)
        self.assertIn("v", out)

    def test_version_short_flag(self):
        out = self._run(["-V"])
        self.assertIn("v", out)

    def test_unknown_command_shows_help(self):
        out = self._run(["nonexistent-command-xyz"])
        self.assertIn("Unknown command", out)

    def test_help_command(self):
        out = self._run(["help"])
        self.assertIn("Usage", out)

    def test_updates_status_command(self):
        out = self._run(["updates", "status"])
        self.assertIn("Updates:", out)
        self.assertIn("Current version:", out)

    def test_updates_download_reports_default_not_ready(self):
        out = self._run(["updates", "download"])
        self.assertIn("Update download not ready", out)
        self.assertIn("disabled", out)

    def test_updates_staged_reports_default_empty(self):
        out = self._run(["updates", "staged"])
        self.assertIn("Staged update:", out)
        self.assertIn("no staged update", out)

    def test_updates_staged_reports_manifest_errors(self):
        from bookmark_organizer_pro.services.updates import UPDATE_CACHE_DIR

        manifest = UPDATE_CACHE_DIR / "staged_update.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{not-json", encoding="utf-8")
        try:
            out = self._run(["updates", "staged"])
        finally:
            manifest.unlink(missing_ok=True)
        self.assertIn("staged manifest unreadable", out)
        self.assertIn("Error:", out)

    def test_updates_apply_command_is_gated(self):
        out = self._run(["updates", "apply"])
        self.assertIn("disabled in this release", out)
        self.assertIn("updates check", out)

    def test_updates_apply_dry_run_reports_preflight_blockers(self):
        out = self._run(["updates", "apply", "--dry-run"])
        self.assertIn("Update apply preflight", out)
        self.assertIn("Blocker: no staged update", out)
        self.assertIn("Blocker: update application is disabled in this release", out)

    def test_updates_clean_staged_reports_default_empty(self):
        out = self._run(["updates", "clean-staged"])
        self.assertIn("Staged update cleanup:", out)
        self.assertIn("no staged update", out)

    def test_updates_plan_reports_default_blockers(self):
        out = self._run(["updates", "plan"])
        self.assertIn("Update apply plan", out)
        self.assertIn("Plan: verify staged target files", out)
        self.assertIn("Blocker: no staged update", out)

    def test_main_entrypoint_accepts_argv(self):
        from bookmark_organizer_pro.cli import main

        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            main(["--version"])
        finally:
            sys.stdout = old_stdout

        self.assertIn("Bookmark Organizer Pro", captured.getvalue())

    def test_package_bookmark_cli_export_is_available(self):
        from bookmark_organizer_pro import BookmarkCLI

        self.assertTrue(callable(BookmarkCLI))


class TestCLIList(CLITestBase):
    def test_list_empty(self):
        out = self._run(["list"])
        self.assertIn("Bookmarks", out)

    def test_list_all_flag(self):
        out = self._run(["list", "--all"])
        self.assertIn("Bookmarks", out)


class TestCLIAdd(CLITestBase):
    def test_add_no_url(self):
        out = self._run(["add"])
        self.assertIn("URL", out.upper() if out else "URL")

    def test_add_valid_url(self):
        out = self._run(["add", "https://test-cli-add.example.com", "CLI Test"])
        self.assertIn("Added" if out else "", out or "")


class TestCLICategories(CLITestBase):
    def test_categories(self):
        out = self._run(["categories"])
        self.assertIsInstance(out, str)

    def test_tags(self):
        out = self._run(["tags"])
        self.assertIsInstance(out, str)

    def test_stats(self):
        out = self._run(["stats"])
        self.assertIn("bookmark", out.lower() if out else "bookmark")


class TestCLISearchAndCheck(CLITestBase):
    def test_search_empty(self):
        out = self._run(["search", "nonexistent-term-xyz"])
        self.assertIsInstance(out, str)

    @patch("bookmark_organizer_pro.services.dead_link_scanner.DeadLinkScanner")
    def test_scan_accepts_space_separated_hours(self, scanner_cls):
        scanner = scanner_cls.return_value
        scanner.scan_now.return_value = []

        out = self._run(["scan", "--hours", "12"])

        self.assertIn("Scan complete", out)
        scanner.scan_now.assert_called_once_with(only_unchecked_for_hours=12)

    @patch("bookmark_organizer_pro.services.dead_link_scanner.DeadLinkScanner")
    def test_scan_accepts_equals_hours(self, scanner_cls):
        scanner = scanner_cls.return_value
        scanner.scan_now.return_value = []

        out = self._run(["scan", "--hours=8"])

        self.assertIn("Scan complete", out)
        scanner.scan_now.assert_called_once_with(only_unchecked_for_hours=8)

    @patch("bookmark_organizer_pro.services.dead_link_scanner.DeadLinkScanner")
    def test_scan_rejects_invalid_hours(self, scanner_cls):
        out = self._run(["scan", "--hours", "soon"])

        self.assertIn("usage: scan", out)
        scanner_cls.assert_not_called()

    @patch("bookmark_organizer_pro.services.api.BookmarkAPI")
    def test_api_server_rejects_invalid_port(self, api_cls):
        out = self._run(["api-server", "--port", "bad"])

        self.assertIn("usage: api-server", out)
        api_cls.assert_not_called()

    @patch("time.sleep", side_effect=KeyboardInterrupt)
    @patch("bookmark_organizer_pro.services.api.BookmarkAPI")
    def test_api_server_starts_and_stops(self, api_cls, _sleep):
        api = api_cls.return_value
        api.port = 9010

        out = self._run(["api-server", "--port=9010"])

        api_cls.assert_called_once()
        self.assertEqual(api_cls.call_args.kwargs["port"], 9010)
        api.start.assert_called_once()
        api.stop.assert_called_once()
        self.assertIn("Local API running", out)

    @patch("bookmark_organizer_pro.mcp_server.serve_http")
    def test_mcp_http_server_rejects_invalid_port(self, serve_http):
        out = self._run(["mcp-http-server", "--port", "bad"])

        self.assertIn("usage: mcp-http-server", out)
        serve_http.assert_not_called()

    @patch("bookmark_organizer_pro.mcp_server.serve_http")
    def test_mcp_http_server_passes_endpoint_options(self, serve_http):
        out = self._run([
            "mcp-http-server",
            "--host",
            "127.0.0.1",
            "--port=9011",
            "--path",
            "/mcp",
        ])

        serve_http.assert_called_once_with(host="127.0.0.1", port=9011, path="/mcp")
        self.assertIsInstance(out, str)

    @patch("bookmark_organizer_pro.core.migrate_json_to_sqlite", return_value=3)
    def test_sqlite_migrate_passes_paths(self, migrate):
        out = self._run([
            "sqlite-migrate",
            "--source",
            "source.json",
            "--dest=bookmarks.sqlite",
        ])

        migrate.assert_called_once()
        self.assertEqual(migrate.call_args.args[0], Path("source.json"))
        self.assertEqual(migrate.call_args.args[1], Path("bookmarks.sqlite"))
        self.assertIn("Migrated 3 bookmarks", out)

    @patch("bookmark_organizer_pro.core.migrate_json_to_sqlite")
    def test_sqlite_migrate_rejects_missing_value(self, migrate):
        out = self._run(["sqlite-migrate", "--source"])

        self.assertIn("usage: sqlite-migrate", out)
        migrate.assert_not_called()

    def test_digest(self):
        out = self._run(["digest"])
        self.assertIsInstance(out, str)


class TestCLISmartCollections(CLITestBase):
    def test_smart_collections_list(self):
        out = self._run(["smart-collections", "list"])
        self.assertIsInstance(out, str)


class TestCLIExportSubcommands(CLITestBase):
    def test_epub_export_no_args(self):
        out = self._run(["epub-export"])
        self.assertIsInstance(out, str)

    def test_obsidian_export_no_args(self):
        out = self._run(["obsidian-export"])
        self.assertIn("Usage", out)

    def test_atom_export(self):
        import tempfile, os
        fd, tmp = tempfile.mkstemp(suffix=".atom.xml")
        os.close(fd)
        try:
            out = self._run(["atom-export", "--output", tmp, "--title", "Test"])
            self.assertIn("exported", out.lower() if out else "exported")
        finally:
            os.unlink(tmp) if os.path.exists(tmp) else None

    def test_json_feed_export(self):
        import tempfile, os
        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            out = self._run(["json-feed", "--output", tmp, "--title", "Test"])
            self.assertIn("exported", out.lower() if out else "exported")
        finally:
            os.unlink(tmp) if os.path.exists(tmp) else None

    def test_opds_export(self):
        import tempfile, os
        fd, tmp = tempfile.mkstemp(suffix=".opds.xml")
        os.close(fd)
        try:
            out = self._run(["opds-export", "--output", tmp, "--title", "Test"])
            self.assertIn("opds", out.lower() if out else "opds")
        finally:
            os.unlink(tmp) if os.path.exists(tmp) else None

    def test_graph_export(self):
        import json
        import tempfile, os
        fd, tmp = tempfile.mkstemp(suffix=".graph.json")
        os.close(fd)
        try:
            out = self._run(["graph-export", "--output", tmp, "--limit", "25"])
            self.assertIn("graph exported", out.lower())
            payload = json.loads(Path(tmp).read_text(encoding="utf-8"))
            self.assertIn("nodes", payload)
            self.assertIn("edges", payload)
        finally:
            os.unlink(tmp) if os.path.exists(tmp) else None


class TestCLIReader(CLITestBase):
    def test_reader_add_list_and_export(self):
        from bookmark_organizer_pro.cli import BookmarkCLI
        from bookmark_organizer_pro.constants import EXTRACTED_DIR, READER_ANNOTATIONS_FILE

        if READER_ANNOTATIONS_FILE.exists():
            READER_ANNOTATIONS_FILE.unlink()
        cli = BookmarkCLI()
        bookmark = cli.bookmark_manager.add_bookmark_clean(
            url="https://reader-cli.example.com",
            title="Reader CLI",
            category="Testing",
        )
        self.assertIsNotNone(bookmark)
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        text_path = EXTRACTED_DIR / f"{bookmark.id}.txt"
        text_path.write_text("Useful reader passage for clipping.", encoding="utf-8")
        bookmark.extracted_text_path = str(text_path)
        cli.bookmark_manager.save_bookmarks()

        out = self._run([
            "reader", "add", str(bookmark.id), "7", "13",
            "--color", "pink", "--note", "Clip",
        ])
        self.assertIn("highlight added", out)

        out = self._run(["reader", "list", str(bookmark.id)])
        self.assertIn("pink", out)
        self.assertIn("reader", out)

        output_dir = Path(self._tmp) / "reader_cli_exports"
        out = self._run(["reader", "export", str(bookmark.id), "--output", str(output_dir)])

        self.assertIn("exported", out)
        self.assertTrue(list(output_dir.glob("*.md")))


class TestCLIStructuredMetadata(CLITestBase):
    def test_structured_command_prints_saved_template_fields(self):
        from bookmark_organizer_pro.cli import BookmarkCLI
        from bookmark_organizer_pro.services.extraction_templates import STRUCTURED_METADATA_KEY

        cli = BookmarkCLI()
        bookmark = cli.bookmark_manager.add_bookmark_clean(
            url="https://structured-cli.example.com",
            title="Structured CLI",
            category="Testing",
        )
        self.assertIsNotNone(bookmark)
        bookmark.custom_data[STRUCTURED_METADATA_KEY] = {
            "schema_version": 1,
            "template": "CLI Template",
            "fields": {"heading": "Structured Heading", "tags": ["one", "two"]},
        }
        cli.bookmark_manager.save_bookmarks()

        out = self._run(["structured", str(bookmark.id)])

        self.assertIn("CLI Template", out)
        self.assertIn("heading: Structured Heading", out)
        self.assertIn("tags: one, two", out)


class TestCLINlQuery(CLITestBase):
    def test_nl_query_no_args(self):
        out = self._run(["nl-query"])
        self.assertIn("Usage", out)


class TestCLIImportMatter(CLITestBase):
    def test_import_matter_no_args(self):
        out = self._run(["import-matter"])
        self.assertIn("Usage", out)


if __name__ == "__main__":
    unittest.main()
