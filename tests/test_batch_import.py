"""Batch folder import: digest dedupe, format detection, cross-file merge."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bookmark_organizer_pro.services.batch_import import (
    BatchDirectoryImporter,
    detect_format,
)


def _netscape(entries) -> str:
    rows = "\n".join(
        f'    <DT><A HREF="{url}" ADD_DATE="{add_date}">{title}</A>'
        for url, title, add_date in entries
    )
    return (
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<TITLE>Bookmarks</TITLE>\n"
        f"<H1>Bookmarks</H1>\n<DL><p>\n{rows}\n</DL><p>\n"
    )


def _json_export(entries) -> str:
    return json.dumps({
        "version": "1",
        "data": [
            {"url": url, "title": title, "add_date": add_date}
            for url, title, add_date in entries
        ],
    })


class TestBatchDirectoryImport(unittest.TestCase):
    def test_folder_of_exports_dedupes_files_and_merges_urls(self):
        """Acceptance: 6 files, 3 byte-identical duplicates, 2 formats."""
        html = _netscape([
            ("https://example.com/alpha", "Alpha", "1700000000"),
            ("https://www.example.com/beta/", "Beta", "1700000001"),
        ])
        # Same two URLs in a different format, plus one that is new. The beta
        # entry differs only by www/trailing slash, so it must merge.
        export = _json_export([
            ("https://example.com/alpha", "Alpha, the longer title", "1700000500"),
            ("https://example.com/beta", "Beta", "1700000001"),
            ("https://example.com/gamma", "Gamma", "1700000002"),
        ])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bookmarks.html").write_text(html, encoding="utf-8")
            (root / "bookmarks - Copy.html").write_text(html, encoding="utf-8")
            (root / "bookmarks (2).html").write_text(html, encoding="utf-8")
            (root / "library.json").write_text(export, encoding="utf-8")
            (root / "library (1).json").write_text(export, encoding="utf-8")
            (root / "notes.rtf").write_text("not a bookmark file", encoding="utf-8")

            plan = BatchDirectoryImporter().plan(root)

        # .rtf is not a candidate at all, so five files are considered.
        self.assertEqual(len(plan.files), 5)
        self.assertEqual(len(plan.unique_files), 2)
        self.assertEqual(len(plan.duplicate_files), 3)
        self.assertEqual({f.format for f in plan.unique_files}, {"netscape-html", "json-export"})

        # 2 HTML entries + 3 JSON entries parsed, collapsing to 3 unique URLs.
        self.assertEqual(plan.parsed_entries, 5)
        self.assertEqual(plan.unique_urls, 3)
        self.assertEqual(plan.merged, 2)

        by_url = {b.url: b for b in plan.bookmarks}
        self.assertEqual(len(by_url), 3)
        alpha = next(b for b in plan.bookmarks if "alpha" in b.url)
        # Longest title and newest date win across files.
        self.assertEqual(alpha.title, "Alpha, the longer title")
        self.assertEqual(alpha.add_date, "1700000500")
        self.assertTrue(any(c.field == "title" for c in plan.conflicts))

    def test_duplicate_detection_is_by_content_not_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.html").write_text(_netscape([("https://a.test/1", "One", "1")]), encoding="utf-8")
            (root / "b.html").write_text(_netscape([("https://b.test/2", "Two", "2")]), encoding="utf-8")

            plan = BatchDirectoryImporter().plan(root)

        self.assertEqual(len(plan.unique_files), 2)
        self.assertEqual(plan.duplicate_files, ())
        self.assertEqual(plan.unique_urls, 2)

    def test_unreadable_source_does_not_abort_the_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.html").write_text(_netscape([("https://ok.test/", "OK", "1")]), encoding="utf-8")
            (root / "broken.json").write_text("{not valid json", encoding="utf-8")

            plan = BatchDirectoryImporter().plan(root)

        self.assertEqual(plan.unique_urls, 1)
        self.assertEqual(len(plan.unreadable_files), 1)
        self.assertTrue(plan.stats.skipped >= 1)
        self.assertEqual(plan.summary()["unreadable_files"], 1)

    def test_format_detection_sniffs_json_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            firefox = root / "backup.json"
            firefox.write_text(json.dumps({
                "guid": "root________", "title": "", "typeCode": 2, "type": "text/x-moz-place-container",
                "children": [{"guid": "a", "title": "Site", "typeCode": 1,
                              "type": "text/x-moz-place", "uri": "https://firefox.test/"}],
            }), encoding="utf-8")
            records = root / "export.json"
            records.write_text(_json_export([("https://records.test/", "R", "1")]), encoding="utf-8")
            plain = root / "urls.txt"
            plain.write_text("https://text.test/one\n", encoding="utf-8")

            self.assertEqual(detect_format(firefox), "firefox-backup")
            self.assertEqual(detect_format(records), "json-export")
            self.assertEqual(detect_format(plain), "text-urls")
            self.assertEqual(detect_format(root / "nope.rtf"), "")

            plan = BatchDirectoryImporter().plan(root)

        self.assertEqual(plan.unique_urls, 3)
        self.assertEqual(
            {f.format for f in plan.unique_files},
            {"firefox-backup", "json-export", "text-urls"},
        )

    def test_explicit_file_list_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "one.html"
            first.write_text(_netscape([("https://one.test/", "One", "1")]), encoding="utf-8")
            second = root / "two.html"
            second.write_text(_netscape([("https://two.test/", "Two", "2")]), encoding="utf-8")

            importer = BatchDirectoryImporter()
            bookmarks = importer.from_paths([str(first), str(second)])

        self.assertEqual(len(bookmarks), 2)
        self.assertEqual(importer.last_plan.unique_urls, 2)

    def test_csv_export_maps_two_level_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "export.csv").write_text(
                "Title,URL,Main Category,Sub Category,Added At\n"
                "Docs,https://csv.test/docs,Reference,Manuals,2026-01-02\n",
                encoding="utf-8",
            )
            plan = BatchDirectoryImporter().plan(root)

        self.assertEqual(plan.unique_urls, 1)
        entry = plan.bookmarks[0]
        self.assertEqual(entry.parent_category, "Reference")
        self.assertEqual(entry.category, "Manuals")
        self.assertEqual(entry.add_date, "2026-01-02")


class TestMappedCSVImporter(unittest.TestCase):
    def _write(self, root: Path, name: str, text: str) -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_markwise_columns_map_without_configuration(self):
        from bookmark_organizer_pro.importers_extra import MappedCSVImporter

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp), "markwise.csv",
                "Title,URL,Main Category,Sub Category,Added At\n"
                "Docs,https://csv.test/docs,Reference,Manuals,2026-01-02\n",
            )
            entries = list(MappedCSVImporter().from_path(str(path)))

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Docs")
        self.assertEqual(entries[0].parent_category, "Reference")
        self.assertEqual(entries[0].category, "Manuals")
        self.assertEqual(entries[0].add_date, "2026-01-02")

    def test_explicit_mapping_handles_unknown_headers(self):
        from bookmark_organizer_pro.importers_extra import MappedCSVImporter

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp), "odd.csv", "Name,Address,Group\nThing,https://odd.test/1,Stuff\n")
            importer = MappedCSVImporter({"url": "Address", "title": "Name", "category": "Group"})
            entries = list(importer.from_path(str(path)))

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].url, "https://odd.test/1")
        self.assertEqual(entries[0].title, "Thing")
        self.assertEqual(entries[0].category, "Stuff")

    def test_rows_without_a_url_are_reported_as_losses(self):
        from bookmark_organizer_pro.importers_extra import MappedCSVImporter

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp), "gaps.csv",
                "Title,URL\nKept,https://kept.test/\nDropped,\n",
            )
            importer = MappedCSVImporter()
            entries = list(importer.from_path(str(path)))

        self.assertEqual(len(entries), 1)
        self.assertEqual(importer.stats.skipped, 1)
        self.assertIn("row has no URL column value", importer.stats.causes)

    def test_header_inspection_suggests_a_mapping(self):
        from bookmark_organizer_pro.importers_extra import MappedCSVImporter

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), "h.csv", "Title,URL,Tags\nA,https://a.test/,x;y\n")
            headers = MappedCSVImporter.headers(str(path))
            mapping = MappedCSVImporter.suggest_mapping(headers)

        self.assertEqual(headers, ["Title", "URL", "Tags"])
        self.assertEqual(mapping["url"], "URL")
        self.assertEqual(mapping["tags"], "Tags")
        self.assertNotIn("category", mapping)


if __name__ == "__main__":
    unittest.main()
