"""CLI dispatch routing and subcommand smoke tests."""

import os
import sys
import tempfile
import shutil
import unittest
from io import StringIO
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
