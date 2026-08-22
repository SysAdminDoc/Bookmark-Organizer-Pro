"""Omnivore export import: zip, unpacked directory, and single metadata file."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path

from bookmark_organizer_pro.importers_extra import OmnivoreImporter

_BATCH_ONE = [
    {
        "id": "1",
        "url": "https://omnivore.test/first",
        "title": "First article",
        "description": "Intro",
        "labels": [{"name": "reading"}, {"name": "research"}],
        "savedAt": "2025-03-01T10:00:00.000Z",
        "state": "SUCCEEDED",
    },
    {
        "id": "2",
        "url": "https://omnivore.test/archived",
        "title": "Archived article",
        "labels": ["done"],
        "savedAt": "2025-03-02T10:00:00.000Z",
        "state": "ARCHIVED",
    },
]

_BATCH_TWO = [
    {
        "id": "3",
        "url": "https://omnivore.test/second",
        "title": "Second article",
        "labels": [],
        "savedAt": "2025-04-01T10:00:00.000Z",
        "state": "SUCCEEDED",
    },
    {"id": "4", "url": "not-a-url", "title": "Broken", "labels": []},
]


class TestOmnivoreImporter(unittest.TestCase):
    def _unpacked(self, root: Path) -> Path:
        export = root / "omnivore-export"
        export.mkdir()
        (export / "metadata_0_to_1.json").write_text(json.dumps(_BATCH_ONE), encoding="utf-8")
        (export / "metadata_2_to_3.json").write_text(json.dumps(_BATCH_TWO), encoding="utf-8")
        (export / "content").mkdir()
        (export / "content" / "1.html").write_text("<html></html>", encoding="utf-8")
        return export

    def test_unpacked_directory_merges_every_metadata_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = self._unpacked(Path(tmp))
            importer = OmnivoreImporter()
            entries = list(importer.from_path(str(export)))

        urls = [b.url for b in entries]
        self.assertEqual(len(entries), 3)
        self.assertIn("https://omnivore.test/first", urls)
        self.assertIn("https://omnivore.test/second", urls)
        self.assertNotIn("not-a-url", urls)
        self.assertEqual(importer.stats.skipped, 1)

        first = next(b for b in entries if b.url.endswith("/first"))
        self.assertEqual(first.title, "First article")
        self.assertEqual(sorted(first.tags), ["reading", "research"])
        self.assertTrue(first.read_later)

        archived = next(b for b in entries if b.url.endswith("/archived"))
        self.assertFalse(archived.read_later)
        self.assertTrue(archived.is_archived, "archived state must be distinguishable")
        self.assertEqual(archived.tags, ["done"])

    def test_unparseable_and_bom_members_are_reported_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp) / "export"
            export.mkdir()
            (export / "metadata_0.json").write_text(json.dumps(_BATCH_ONE), encoding="utf-8")
            (export / "metadata_1.json").write_text('[{"url": "https://x.test/1"', encoding="utf-8")
            # A BOM-prefixed member must still parse rather than vanish.
            (export / "metadata_2.json").write_text(
                json.dumps([{"url": "https://bom.test/1", "title": "BOM", "labels": []}]),
                encoding="utf-8-sig",
            )
            importer = OmnivoreImporter()
            entries = list(importer.from_path(str(export)))

        urls = {b.url for b in entries}
        self.assertIn("https://bom.test/1", urls)
        self.assertEqual(importer.stats.skipped, 1)
        self.assertTrue(
            any("could not be parsed" in cause for cause in importer.stats.causes),
            importer.stats.causes,
        )

    def test_zip_export_is_read_without_unpacking(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "omnivore.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("metadata_0_to_1.json", json.dumps(_BATCH_ONE))
                zf.writestr("metadata_2_to_3.json", json.dumps(_BATCH_TWO))
                zf.writestr("content/1.html", "<html></html>")
            entries = list(OmnivoreImporter().from_path(str(archive)))

        self.assertEqual(len(entries), 3)

    def test_single_metadata_file_and_explicit_file_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = self._unpacked(Path(tmp))
            single = export / "metadata_0_to_1.json"

            self.assertEqual(len(list(OmnivoreImporter().from_path(str(single)))), 2)

            files = OmnivoreImporter.metadata_files(str(export))
            self.assertEqual(len(files), 2)
            self.assertEqual(len(list(OmnivoreImporter().from_paths(files))), 3)

    def test_duplicate_urls_across_batches_are_collapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp) / "export"
            export.mkdir()
            (export / "metadata_0.json").write_text(json.dumps(_BATCH_ONE), encoding="utf-8")
            (export / "metadata_1.json").write_text(json.dumps(_BATCH_ONE), encoding="utf-8")
            entries = list(OmnivoreImporter().from_path(str(export)))

        self.assertEqual(len(entries), 2)

    def test_missing_source_yields_nothing(self):
        self.assertEqual(list(OmnivoreImporter().from_path("does-not-exist.json")), [])

    def test_an_oversized_archive_member_is_reported_rather_than_read(self):
        """A zip declares each member's uncompressed size, so a small archive
        can hold a highly compressible multi-gigabyte member."""
        from bookmark_organizer_pro import importers_extra

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "export.zip"
            payload = json.dumps([{"url": "https://example.com/a", "title": "A"}])
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("metadata_0.json", "[" + " " * 200_000 + "]")
                archive.writestr("metadata_1.json", payload)

            with unittest.mock.patch.object(
                importers_extra, "MAX_ARCHIVE_MEMBER_BYTES", 1_000,
            ):
                importer = OmnivoreImporter()
                bookmarks = list(importer.from_path(str(archive_path)))

        self.assertEqual([bm.url for bm in bookmarks], ["https://example.com/a"])
        self.assertTrue(
            any("over the" in cause for cause in importer.stats.causes),
            f"the oversized member must be reported, got {importer.stats.causes}",
        )


if __name__ == "__main__":
    unittest.main()
