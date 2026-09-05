"""Durable import session behavior."""

from __future__ import annotations

from dataclasses import dataclass
import contextlib
import json
import urllib.request
from unittest.mock import patch

import pytest

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.importers import GenericFileSessionImporter
from bookmark_organizer_pro.services.import_sessions import ImportSessionManager


class _Storage:
    def __init__(self):
        self.revision = 0

    def current_revision(self):
        return self.revision


class _Manager:
    def __init__(self):
        self.bookmarks = {}
        self.storage = _Storage()
        self.snapshots = {}
        self.fail_once = set()

    def get_all_bookmarks(self):
        return list(self.bookmarks.values())

    def create_safepoint(self, label):
        name = f"safepoints/{label}.json"
        self.snapshots[name] = (dict(self.bookmarks), self.storage.revision)
        return name

    def add_bookmark(self, bookmark):
        if bookmark.url in self.fail_once:
            self.fail_once.remove(bookmark.url)
            raise OSError("transient row write failure")
        bookmark.id = bookmark.id or len(self.bookmarks) + 1
        self.bookmarks[bookmark.id] = bookmark
        self.storage.revision += 1
        return bookmark

    def restore_backup(self, name):
        snapshot = self.snapshots.get(name)
        if snapshot is None:
            return False
        self.bookmarks, self.storage.revision = dict(snapshot[0]), snapshot[1]
        return True


@dataclass
class _Stats:
    skipped: int = 0


class _Importer:
    def __init__(self, bookmarks, skipped=0):
        self.bookmarks = bookmarks
        self.stats = _Stats(skipped)

    def from_path(self, _path):
        return iter(self.bookmarks)


def _bookmark(url):
    return Bookmark(id=None, url=url, title=url)


def test_first_import_into_an_unwritten_library_creates_a_real_safepoint(tmp_path):
    """A never-saved library has no file to snapshot; that is the normal
    first-run migration case and must not refuse the import."""

    library = tmp_path / "library" / "master_bookmarks.json"

    class _FreshManager(_Manager):
        def __init__(self):
            super().__init__()
            self.storage.filepath = library
            self.saved = False

        def create_safepoint(self, label):
            # StorageManager returns None while the library file is absent.
            if not library.exists():
                return None
            return super().create_safepoint(label)

        def save_bookmarks(self):
            library.parent.mkdir(parents=True, exist_ok=True)
            library.write_text("[]", encoding="utf-8")
            self.saved = True

    source = tmp_path / "source.json"
    source.write_text("source-v1", encoding="utf-8")
    importer = _Importer([_bookmark("https://fresh.example")])
    manager = _FreshManager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    report = sessions.run(manager, importer, source, source="fixture")

    assert manager.saved, "an unwritten library should be persisted before the safepoint"
    assert report.added == 1
    assert report.safepoint, "the session must record a restorable safepoint"
    assert manager.restore_backup(report.safepoint) is True


def test_import_refuses_without_writing_when_an_existing_library_cannot_be_snapshotted(tmp_path):
    """A snapshot failure on a library that DOES exist (unwritable backup dir,
    full disk) must refuse the import and leave the library untouched."""
    library = tmp_path / "master_bookmarks.json"
    library.write_text("[]", encoding="utf-8")
    saves = []

    class _UnsnapshottableManager(_Manager):
        def __init__(self):
            super().__init__()
            self.storage.filepath = library

        def create_safepoint(self, label):
            return None  # e.g. shutil.copy2 raised

        def save_bookmarks(self):
            saves.append(True)

    source = tmp_path / "source.json"
    source.write_text("source-v1", encoding="utf-8")
    importer = _Importer([_bookmark("https://guarded.example")])
    manager = _UnsnapshottableManager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    with pytest.raises(RuntimeError, match="rollback safepoint"):
        sessions.run(manager, importer, source, source="fixture")
    assert manager.bookmarks == {}
    assert saves == [], "a refused import must not rewrite an existing library"


def test_import_writes_the_library_once_for_the_whole_batch(tmp_path):
    writes = []

    class _CountingManager(_Manager):
        def __init__(self):
            super().__init__()
            self._batch_depth = 0

        @contextlib.contextmanager
        def batch(self):
            self._batch_depth += 1
            try:
                yield self
            finally:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    writes.append(len(self.bookmarks))

        def add_bookmark(self, bookmark):
            result = super().add_bookmark(bookmark)
            if self._batch_depth == 0:
                writes.append(len(self.bookmarks))
            return result

    source = tmp_path / "source.json"
    source.write_text("source-v1", encoding="utf-8")
    importer = _Importer([_bookmark(f"https://row{n}.example") for n in range(5)])
    manager = _CountingManager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    report = sessions.run(manager, importer, source, source="fixture")

    assert report.added == 5
    assert writes == [5], f"expected one batched write, got {writes}"


def test_cancelled_import_resumes_without_duplicate_rows(tmp_path):
    source = tmp_path / "source.json"
    source.write_text("source-v1", encoding="utf-8")
    importer = _Importer([_bookmark("https://one.example"), _bookmark("https://two.example")])
    manager = _Manager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")
    checks = 0

    def cancel_after_first():
        nonlocal checks
        checks += 1
        return checks > 1

    cancelled = sessions.run(
        manager, importer, source, source="fixture", cancel_requested=cancel_after_first
    )
    assert cancelled.status == "cancelled"
    assert (cancelled.added, cancelled.pending) == (1, 1)

    restarted = ImportSessionManager(tmp_path / "sessions.json")
    completed = restarted.run(manager, importer, source, source="fixture")
    replay = restarted.run(manager, importer, source, source="fixture")

    assert completed.status == "completed"
    assert (completed.added, completed.pending, len(manager.bookmarks)) == (2, 0, 2)
    assert replay.session_id == completed.session_id
    assert len(manager.bookmarks) == 2


def test_failed_row_retry_preserves_causes_and_loss_count(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("source-v1", encoding="utf-8")
    failing_url = "https://retry.example"
    importer = _Importer([_bookmark(failing_url), _bookmark("https://ok.example")], skipped=3)
    manager = _Manager()
    manager.fail_once.add(failing_url)
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    first = sessions.run(manager, importer, source, source="fixture")
    assert (first.failed, first.added, first.losses) == (1, 1, 3)
    assert first.causes == {"transient row write failure": 1}

    retried = sessions.run(manager, importer, source, source="fixture", retry_failed=True)
    assert (retried.failed, retried.added, retried.losses) == (0, 2, 3)
    assert retried.causes == {}
    assert len(manager.bookmarks) == 2


def test_generic_multi_file_import_uses_one_session_and_one_safepoint(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("https://one.example\n", encoding="utf-8")
    second.write_text("https://two.example\n", encoding="utf-8")
    manager = _Manager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")
    importer = GenericFileSessionImporter()

    preflight = sessions.preflight(
        importer, [first, second], source="generic-files"
    )
    report = sessions.run(
        manager,
        importer,
        [first, second],
        source="generic-files",
        prepared=preflight,
    )
    replay = ImportSessionManager(tmp_path / "sessions.json").resume(
        manager, report.session_id
    )

    record = sessions.get(report.session_id)
    assert preflight.total == 2
    assert report.status == "completed"
    assert len(manager.snapshots) == 1
    assert record["source_paths"] == [str(first.resolve()), str(second.resolve())]
    assert replay.session_id == report.session_id
    assert len(manager.bookmarks) == 2


def test_preflight_rejects_zero_rows_without_creating_session_or_safepoint(tmp_path):
    source = tmp_path / "empty.txt"
    source.write_text("not a URL", encoding="utf-8")
    manager = _Manager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    try:
        sessions.run(
            manager,
            GenericFileSessionImporter(),
            source,
            source="generic-files",
        )
    except ValueError as exc:
        assert "0 valid bookmarks" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("empty import unexpectedly succeeded")

    assert sessions.list() == []
    assert manager.snapshots == {}


def test_preflight_reports_field_coverage_and_partial_file_loss(tmp_path):
    valid = tmp_path / "valid.json"
    invalid = tmp_path / "invalid.txt"
    valid.write_text(
        json.dumps([{"url": "https://example.com", "title": "Example", "tags": ["saved"]}]),
        encoding="utf-8",
    )
    invalid.write_text("no bookmark URLs here", encoding="utf-8")
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    preflight = sessions.preflight(
        GenericFileSessionImporter(), [valid, invalid], source="generic-files"
    )

    assert preflight.total == 1
    assert preflight.losses == 1
    assert preflight.field_coverage["tags"] == 1
    assert preflight.causes == {"invalid.txt: no supported bookmark rows found": 1}


def test_browser_import_requires_profile_picker_instead_of_first_profile(tmp_path):
    from bookmark_organizer_pro.app_mixins.import_export import ImportExportMixin

    profiles = [("Default", tmp_path / "Default"), ("Profile 2", tmp_path / "Profile 2")]
    seen = []
    app = ImportExportMixin()
    app._show_toast = lambda *_args: None
    app._show_browser_profile_picker = lambda browser, choices: seen.append((browser, choices))

    with patch(
        "bookmark_organizer_pro.app_mixins.import_export.BrowserProfileImporter.get_profiles",
        return_value=profiles,
    ):
        app._import_from_browser("chrome")

    assert seen == [("chrome", profiles)]


def test_rollback_refuses_newer_edits_then_restores_exact_safepoint(tmp_path):
    source = tmp_path / "source.html"
    source.write_text("source-v1", encoding="utf-8")
    importer = _Importer([_bookmark("https://one.example")])
    manager = _Manager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")
    report = sessions.run(manager, importer, source, source="fixture")

    manager.storage.revision += 1
    try:
        sessions.rollback(manager, report.session_id)
    except RuntimeError as exc:
        assert "newer edits" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsafe rollback unexpectedly succeeded")

    manager.storage.revision -= 1
    rolled_back = sessions.rollback(manager, report.session_id)
    assert rolled_back.status == "rolled_back"
    assert manager.bookmarks == {}


def test_authenticated_api_surfaces_session_rows_and_rollback(tmp_path):
    from bookmark_organizer_pro.services.api import BookmarkAPI

    source = tmp_path / "source.json"
    source.write_text("source-v1", encoding="utf-8")
    session_path = tmp_path / "sessions.json"
    manager = _Manager()
    with patch(
        "bookmark_organizer_pro.services.import_sessions.IMPORT_SESSIONS_FILE",
        session_path,
    ), patch(
        "bookmark_organizer_pro.services.api._load_or_create_token",
        return_value="test-token",
    ):
        report = ImportSessionManager().run(
            manager, _Importer([_bookmark("https://one.example")]), source, source="fixture"
        )
        api = BookmarkAPI(manager, port=0)
        try:
            api.start()
            headers = {"Authorization": "Bearer test-token"}
            base = f"http://127.0.0.1:{api.port}"
            request = urllib.request.Request(f"{base}/imports/{report.session_id}", headers=headers)
            with urllib.request.urlopen(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            assert payload["session_id"] == report.session_id
            assert payload["rows"][0]["state"] == "completed"

            rollback = urllib.request.Request(
                f"{base}/imports/{report.session_id}/rollback",
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(rollback, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            assert payload["status"] == "rolled_back"
            assert manager.bookmarks == {}
        finally:
            api.stop()


def test_the_reconciliation_accounts_for_every_record_the_source_held(tmp_path):
    """The question a large import leaves: did all of it arrive?"""
    source = tmp_path / "source.csv"
    source.write_text("source-v1", encoding="utf-8")
    failing = "https://fails.example"
    importer = _Importer(
        [_bookmark(failing), _bookmark("https://ok.example"), _bookmark("https://ok.example")],
        skipped=2,
    )
    manager = _Manager()
    manager.fail_once.add(failing)
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    report = sessions.run(manager, importer, source, source="fixture")

    # Three rows parsed plus two the parser could not use is what the file held.
    assert report.found == 5
    assert (report.added, report.duplicates, report.failed, report.losses) == (1, 1, 1, 2)
    assert report.balances
    assert report.unaccounted == 0
    payload = report.to_dict()
    assert payload["found"] == 5
    assert payload["balances"] is True


def test_a_row_in_an_unrecognized_state_is_reported_not_counted_as_success(tmp_path):
    """A state no counter covers is how a partial import reads as complete."""
    source = tmp_path / "source.csv"
    source.write_text("source-v1", encoding="utf-8")
    importer = _Importer([_bookmark("https://one.example"), _bookmark("https://two.example")])
    manager = _Manager()
    sessions = ImportSessionManager(tmp_path / "sessions.json")
    report = sessions.run(manager, importer, source, source="fixture")
    assert report.status == "completed" and report.balances

    def corrupt(document):
        document["sessions"][0]["rows"][0]["state"] = "quietly-dropped"
        document["sessions"][0]["status"] = "pending"
        return document

    sessions._store.update(corrupt)
    damaged = sessions.report(report.session_id)

    assert not damaged.balances
    assert damaged.unaccounted == 1
    assert damaged.to_dict()["unaccounted"] == 1


def test_rejected_rows_name_the_records_that_did_not_land(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("source-v1", encoding="utf-8")
    failing = "https://fails.example"
    importer = _Importer([_bookmark(failing), _bookmark("https://ok.example")])
    manager = _Manager()
    manager.fail_once.add(failing)
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    report = sessions.run(manager, importer, source, source="fixture")
    rejected = sessions.rejected_rows(report.session_id)

    assert len(rejected) == 1
    assert rejected[0]["url"] == failing
    assert rejected[0]["state"] == "failed"
    assert rejected[0]["reason"] == "transient row write failure"
    assert rejected[0]["position"] == 1


def test_the_rejected_list_is_written_where_a_user_can_open_it(tmp_path):
    import csv as _csv

    source = tmp_path / "source.csv"
    source.write_text("source-v1", encoding="utf-8")
    # A URL a spreadsheet would execute if it were written through unguarded.
    hostile = "=cmd|'/c calc'!A0"
    importer = _Importer([_bookmark(hostile), _bookmark("https://ok.example")])
    manager = _Manager()
    manager.fail_once.add(hostile)
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    report = sessions.run(manager, importer, source, source="fixture")
    destination = tmp_path / "review" / "rejected.csv"
    written = sessions.write_rejected_rows(report.session_id, destination)

    assert written == destination and destination.is_file()
    rows = list(_csv.DictReader(destination.open(encoding="utf-8", newline="")))
    assert [row["position"] for row in rows] == ["1"]
    assert not rows[0]["url"].startswith("=")
    assert hostile in rows[0]["url"]


def test_an_import_with_nothing_rejected_writes_an_empty_review_list(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("source-v1", encoding="utf-8")
    importer = _Importer([_bookmark("https://ok.example")])
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    report = sessions.run(_Manager(), importer, source, source="fixture")

    assert sessions.rejected_rows(report.session_id) == []
    written = sessions.write_rejected_rows(report.session_id, tmp_path / "none.csv")
    assert written.read_text(encoding="utf-8").strip() == "position,url,state,reason"


def test_a_truncated_export_is_reported_instead_of_imported_quietly(tmp_path):
    """The file parses into fewer bookmarks with no error raised anywhere."""
    whole = (
        '<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>'
        + "".join(f'<DT><A HREF="https://e{index}.example">E{index}</A>' for index in range(20))
        + '</DL><p>'
    )
    source = tmp_path / "truncated.html"
    source.write_text(whole[: len(whole) // 2], encoding="utf-8")
    sessions = ImportSessionManager(tmp_path / "sessions.json")
    importer = GenericFileSessionImporter()

    report = sessions.run(_Manager(), importer, source, source="generic-files")

    assert report.malformed_source
    assert "truncated" in report.malformed_source
    # Every record it could read landed, and it still must not say completed.
    assert report.failed == 0
    assert report.status == "attention"
    assert report.to_dict()["malformed_source"]


def test_a_whole_export_reports_no_damage(tmp_path):
    """The truncation check must not fire on a well-formed file."""
    source = tmp_path / "whole.html"
    source.write_text(
        '<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>'
        '<DT><H3>Work</H3><DL><p><DT><A HREF="https://one.example">One</A></DL><p>'
        '<DT><A HREF="https://two.example">Two</A></DL><p>',
        encoding="utf-8",
    )
    sessions = ImportSessionManager(tmp_path / "sessions.json")

    report = sessions.run(_Manager(), GenericFileSessionImporter(), source, source="generic-files")

    assert report.malformed_source == ""
    assert report.status == "completed"
    assert report.found == 2 and report.added == 2 and report.balances
