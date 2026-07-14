"""Durable import session behavior."""

from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.request
from unittest.mock import patch

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
