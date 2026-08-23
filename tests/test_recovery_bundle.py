"""Integration coverage for checksummed full-library recovery bundles."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import bookmark_organizer_pro.services.recovery_bundle as recovery_bundle_module
from bookmark_organizer_pro.cli import BookmarkCLI
from bookmark_organizer_pro.core import CategoryManager
from bookmark_organizer_pro.core.sqlite_storage import SQLiteStorageManager
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore
from bookmark_organizer_pro.services.reader_progress import ReaderProgressStore
from bookmark_organizer_pro.services.recovery_bundle import (
    INDEX_NAME,
    MANIFEST_NAME,
    ROLLBACK_MANIFEST_NAME,
    create_recovery_bundle,
    restore_recovery_bundle,
    validate_recovery_bundle,
    verify_recovery_bundle_coverage,
)
from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore


def _write_library(root: Path, *, title: str = "Original") -> None:
    (root / "snapshots").mkdir(parents=True)
    (root / "extracted").mkdir()
    snapshot = root / "snapshots" / "1.html"
    history_snapshot = root / "snapshots" / "1" / "history" / "v1.html"
    history_snapshot.parent.mkdir(parents=True)
    extracted = root / "extracted" / "1.txt"
    snapshot.write_text("<html>saved</html>", encoding="utf-8")
    history_snapshot.write_text("<html>older</html>", encoding="utf-8")
    extracted.write_text("saved article", encoding="utf-8")
    bookmark = {
        "id": 1,
        "url": "https://example.com/article",
        "title": title,
        "category": "Research",
        "tags": ["portable"],
        "snapshot_path": str(snapshot.resolve()),
        "extracted_text_path": str(extracted.resolve()),
    }
    (root / "master_bookmarks.json").write_text(
        json.dumps({"version": 4, "metadata": {"count": 1}, "data": [bookmark]}),
        encoding="utf-8",
    )
    fixtures = {
        "categories.json": {"Research": ["example.com"]},
        "tags.json": {"portable": {"count": 1}},
        "settings.json": {"theme": "studio_dark"},
        "reader_annotations.json": {"version": 1, "highlights": [{"bookmark_id": 1}]},
        "reader_progress.json": {"progress": [{"bookmark_id": 1, "state": "in_progress", "position": 8}]},
        "flows.json": {"version": 1, "flows": [{"name": "Investigation"}]},
        "feeds.json": {"version": 1, "feeds": [{"url": "https://example.com/feed"}]},
        "smart_collections.json": {"version": 1, "collections": [{"name": "Research"}]},
        "snapshot_history.json": {"versions": [{"bookmark_id": 1, "path": str(history_snapshot)}]},
    }
    for name, payload in fixtures.items():
        (root / name).write_text(json.dumps(payload), encoding="utf-8")


def test_bundle_round_trip_restores_full_library_and_rewrites_portable_paths(tmp_path):
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    source.mkdir()
    _write_library(source)
    bundle = create_recovery_bundle(tmp_path / "library.zip", data_dir=source)

    report = validate_recovery_bundle(bundle)
    assert report.valid
    assert report.rebuild == {
        "embeddings": True,
        "full_text_index": True,
        "reason": "Search indexes are rebuildable and intentionally excluded from recovery bundles.",
    }
    assert {
        "master_bookmarks.json",
        "categories.json",
        "tags.json",
        "settings.json",
        "reader_annotations.json",
        "reader_progress.json",
        "flows.json",
        "feeds.json",
        "smart_collections.json",
        "snapshots/1.html",
        "snapshots/1/history/v1.html",
        "snapshot_history.json",
        "extracted/1.txt",
    }.issubset(report.contents)

    result = restore_recovery_bundle(bundle, data_dir=restored, dry_run=False)
    assert result.applied
    assert Path(result.rollback_bundle).is_file()
    assert (restored / "snapshots" / "1.html").read_text(encoding="utf-8") == "<html>saved</html>"
    assert (restored / "snapshots" / "1" / "history" / "v1.html").read_text(encoding="utf-8") == "<html>older</html>"
    history_envelope = json.loads((restored / "snapshot_history.json").read_text(encoding="utf-8"))
    history_record = history_envelope["document"]["versions"][0]
    assert history_record["path"] == str((restored / "snapshots" / "1" / "history" / "v1.html").resolve())
    payload = json.loads((restored / "master_bookmarks.json").read_text(encoding="utf-8"))
    bookmark = payload["data"][0]
    assert bookmark["snapshot_path"] == str((restored / "snapshots" / "1.html").resolve())
    assert bookmark["extracted_text_path"] == str((restored / "extracted" / "1.txt").resolve())
    assert json.loads((restored / "reader_annotations.json").read_text())["highlights"]
    assert json.loads((restored / "reader_progress.json").read_text())["progress"][0]["state"] == "in_progress"


def test_restore_defaults_to_non_mutating_dry_run(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _write_library(source, title="Bundle")
    _write_library(target, title="Keep me")
    before = (target / "master_bookmarks.json").read_bytes()
    bundle = create_recovery_bundle(tmp_path / "library.zip", data_dir=source)

    result = restore_recovery_bundle(bundle, data_dir=target)

    assert result.report.valid
    assert not result.applied
    assert result.rollback_bundle == ""
    assert (target / "master_bookmarks.json").read_bytes() == before
    assert not (target / "backups" / "recovery_bundles").exists()


def test_dry_run_plans_exact_state_and_backend_switch_without_mutating(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _write_library(source, title="Bundle")
    _write_library(target, title="Keep me")
    current = json.loads((target / "master_bookmarks.json").read_text(encoding="utf-8"))
    SQLiteStorageManager(target / "master_bookmarks.sqlite").save(current["data"])
    stale = target / "snapshots" / "stale.html"
    stale.write_text("stale", encoding="utf-8")
    before = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    bundle = create_recovery_bundle(tmp_path / "library.zip", data_dir=source)

    result = restore_recovery_bundle(bundle, data_dir=target)

    actions = {(action.kind, action.path) for action in result.report.actions}
    assert result.report.storage_backend == "json"
    assert ("backend-switch", "master_bookmarks.json") in actions
    assert ("delete", "master_bookmarks.sqlite") in actions
    assert ("delete", "snapshots/stale.html") in actions
    assert ("update", "master_bookmarks.json") in actions
    after = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    assert after == before


def test_apply_installs_exact_members_retires_alternate_and_verifies_checkpoint(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _write_library(source, title="Bundle")
    _write_library(target, title="Old")
    old = json.loads((target / "master_bookmarks.json").read_text(encoding="utf-8"))
    SQLiteStorageManager(target / "master_bookmarks.sqlite").save(old["data"])
    (target / "snapshots" / "stale.html").write_text("stale", encoding="utf-8")
    bundle = create_recovery_bundle(tmp_path / "library.zip", data_dir=source)

    result = restore_recovery_bundle(bundle, data_dir=target, dry_run=False)

    assert result.applied
    assert result.storage_backend == "json"
    assert result.restored_count == 1
    assert not (target / "master_bookmarks.sqlite").exists()
    assert not (target / "snapshots" / "stale.html").exists()
    assert json.loads((target / "master_bookmarks.json").read_text(encoding="utf-8"))["data"][0]["title"] == "Bundle"
    with zipfile.ZipFile(result.rollback_bundle) as archive:
        manifest = json.loads(archive.read(ROLLBACK_MANIFEST_NAME))
        checkpoint_paths = {entry["relative_path"] for entry in manifest["entries"]}
    assert "master_bookmarks.json" in checkpoint_paths
    assert "master_bookmarks.sqlite" in checkpoint_paths
    assert "snapshots/stale.html" in checkpoint_paths


def test_apply_failure_restores_every_original_managed_root(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _write_library(source, title="Bundle")
    _write_library(target, title="Original")
    (target / "snapshots" / "stale.html").write_text("keep", encoding="utf-8")
    bundle = create_recovery_bundle(tmp_path / "library.zip", data_dir=source)
    before = {path.relative_to(target).as_posix(): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    real_replace = recovery_bundle_module.os.replace
    failed = False

    def fail_once(source_path, destination_path):
        nonlocal failed
        source_path = Path(source_path)
        if (
            not failed
            and source_path.parent.name == "candidate"
            and Path(destination_path).parent == target
        ):
            failed = True
            raise OSError("simulated interrupted install")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(recovery_bundle_module.os, "replace", fail_once)
    try:
        restore_recovery_bundle(bundle, data_dir=target, dry_run=False)
    except OSError as exc:
        assert "interrupted install" in str(exc)
    else:
        raise AssertionError("simulated interrupted restore unexpectedly succeeded")

    after = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and "backups/recovery_bundles" not in path.relative_to(target).as_posix()
    }
    assert after == before


def test_sqlite_bundle_rewrites_capture_paths(tmp_path):
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    source.mkdir()
    _write_library(source)
    raw = json.loads((source / "master_bookmarks.json").read_text(encoding="utf-8"))
    SQLiteStorageManager(source / "master_bookmarks.sqlite").save(raw["data"])
    (source / "master_bookmarks.json").unlink()
    bundle = create_recovery_bundle(tmp_path / "sqlite-library.zip", data_dir=source)

    result = restore_recovery_bundle(bundle, data_dir=restored, dry_run=False)

    assert result.applied
    bookmarks = SQLiteStorageManager(restored / "master_bookmarks.sqlite").load()
    assert bookmarks[0].snapshot_path == str((restored / "snapshots" / "1.html").resolve())
    assert bookmarks[0].extracted_text_path == str((restored / "extracted" / "1.txt").resolve())


def test_validation_rejects_tampered_payload(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_library(source)
    original = create_recovery_bundle(tmp_path / "library.zip", data_dir=source)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(original) as archive, zipfile.ZipFile(tampered, "w") as output:
        for info in archive.infolist():
            data = archive.read(info)
            if info.filename == "library/settings.json":
                data = b'{}'
            output.writestr(info.filename, data)

    report = validate_recovery_bundle(tampered)

    assert not report.valid
    assert any("mismatch: library/settings.json" in error for error in report.errors)


def test_validation_rejects_unmanifested_and_unsafe_members(tmp_path):
    bundle = tmp_path / "unsafe.zip"
    manifest = {"format": "bookmark-organizer-recovery", "version": 1, "entries": []}
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest))
        archive.writestr(INDEX_NAME, "{}")
        archive.writestr("../escape.txt", "bad")

    report = validate_recovery_bundle(bundle)

    assert not report.valid
    assert any("Unsafe archive path" in error for error in report.errors)
    assert any("Unmanifested archive members" in error for error in report.errors)


def test_create_refuses_missing_bookmark_library(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "settings.json").write_text("{}", encoding="utf-8")

    try:
        create_recovery_bundle(tmp_path / "library.zip", data_dir=source)
    except ValueError as exc:
        assert "No bookmark library" in str(exc)
    else:
        raise AssertionError("missing bookmark library should be rejected")


def test_cli_recovery_bundle_restore_is_dry_run_unless_apply_is_present():
    parser = BookmarkCLI.__new__(BookmarkCLI)._build_parser()

    dry_run = parser.parse_args(["recovery-bundle", "restore", "library.zip"])
    apply = parser.parse_args(["recovery-bundle", "restore", "library.zip", "--apply"])

    assert dry_run.action == "restore"
    assert not dry_run.apply
    assert apply.apply


def _make_bookmark_manager(root: Path) -> BookmarkManager:
    return BookmarkManager(
        CategoryManager(filepath=root / "categories.json"),
        TagManager(filepath=root / "tags.json"),
        filepath=root / "master_bookmarks.json",
    )


def test_trash_purge_bundle_restores_record_and_every_owned_artifact(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    snapshots = root / "snapshots"
    extracted = root / "extracted"
    transcripts = root / "transcripts"
    screenshots = root / "screenshots"
    for directory in (snapshots, extracted, transcripts, screenshots):
        directory.mkdir()
    snapshot = snapshots / "41.html"
    snapshot_manifest = snapshots / "41.snapshot.json"
    extracted_text = extracted / "41.txt"
    transcript = transcripts / "41-en.txt"
    screenshot = screenshots / "41.png"
    snapshot.write_text("<html>saved article</html>", encoding="utf-8")
    snapshot_manifest.write_text('{"artifact_name":"41.html"}', encoding="utf-8")
    extracted_text.write_text("Alpha selected passage omega", encoding="utf-8")
    transcript.write_text("Transcript text", encoding="utf-8")
    screenshot.write_bytes(b"PNG fixture")

    manager = _make_bookmark_manager(root)
    bookmark = Bookmark(
        id=41,
        url="https://example.com/trash-contract",
        title="Trash contract",
        is_archived=True,
        snapshot_path=str(snapshot),
        extracted_text_path=str(extracted_text),
        youtube_transcript_path=str(transcript),
        screenshot_path=str(screenshot),
    )
    manager.add_bookmark(bookmark)
    progress = manager.reader_progress_store.save(
        bookmark.id,
        extracted_text.read_text(encoding="utf-8"),
        12,
        state="in_progress",
    ).progress
    annotations = ReaderAnnotationStore(root / "reader_annotations.json")
    highlight = annotations.add_from_text(
        bookmark.id,
        extracted_text.read_text(encoding="utf-8"),
        6,
        14,
        note="Preserve this note",
    )
    history = SnapshotHistoryStore(snapshots)
    version = history.record(
        bookmark.id,
        snapshot,
        source_url=bookmark.url,
        backend="fixture",
    )

    assert manager.delete_bookmark(bookmark.id)
    restarted = _make_bookmark_manager(root)
    trashed = restarted.get_bookmark(bookmark.id, include_deleted=True)
    assert trashed is not None and trashed.is_deleted and trashed.is_archived
    assert restarted.get_bookmark(bookmark.id) is None
    assert Path(trashed.snapshot_path).is_file()
    assert Path(trashed.extracted_text_path).is_file()
    assert Path(trashed.youtube_transcript_path).is_file()
    assert Path(trashed.screenshot_path).is_file()
    assert ReaderProgressStore(root / "reader_progress.json").get(bookmark.id) == progress
    assert ReaderAnnotationStore(root / "reader_annotations.json").list_for_bookmark(bookmark.id)[0].id == highlight.id
    assert SnapshotHistoryStore(snapshots).list_versions(bookmark.id)[0].version_id == version.version_id

    result = restarted.purge_trash([bookmark.id])

    assert result.success, result.errors
    assert result.purged_ids == (bookmark.id,)
    bundle = Path(result.recovery_bundle)
    assert bundle.is_file()
    report = verify_recovery_bundle_coverage(
        bundle,
        bookmark_ids=[bookmark.id],
        relative_paths=[
            "snapshots/41.html",
            "snapshots/41.snapshot.json",
            Path(version.path).relative_to(root).as_posix(),
            "extracted/41.txt",
            "transcripts/41-en.txt",
            "screenshots/41.png",
            "reader_annotations.json",
            "reader_progress.json",
            "snapshot_history.json",
        ],
    )
    assert report.valid
    assert restarted.get_bookmark(bookmark.id, include_deleted=True) is None
    for path in (snapshot, snapshot_manifest, extracted_text, transcript, screenshot, Path(version.path)):
        assert not path.exists()
    assert ReaderProgressStore(root / "reader_progress.json").get(bookmark.id) is None
    assert ReaderAnnotationStore(root / "reader_annotations.json").list_for_bookmark(bookmark.id) == []
    assert SnapshotHistoryStore(snapshots).list_versions(bookmark.id) == []

    restored = tmp_path / "restored"
    restore_result = restore_recovery_bundle(bundle, data_dir=restored, dry_run=False)
    assert restore_result.applied
    restored_manager = _make_bookmark_manager(restored)
    restored_bookmark = restored_manager.get_bookmark(bookmark.id, include_deleted=True)
    assert restored_bookmark is not None and restored_bookmark.is_deleted
    assert restored_bookmark.is_archived
    assert Path(restored_bookmark.snapshot_path).is_file()
    assert Path(restored_bookmark.extracted_text_path).is_file()
    assert Path(restored_bookmark.youtube_transcript_path).is_file()
    assert Path(restored_bookmark.screenshot_path).is_file()
    assert ReaderProgressStore(restored / "reader_progress.json").get(bookmark.id) == progress
    assert ReaderAnnotationStore(restored / "reader_annotations.json").list_for_bookmark(bookmark.id)[0].id == highlight.id
    assert SnapshotHistoryStore(restored / "snapshots").list_versions(bookmark.id)[0].version_id == version.version_id


def test_trash_purge_bundle_failure_leaves_records_and_artifacts_untouched(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    extracted = root / "extracted"
    extracted.mkdir()
    artifact = extracted / "9.txt"
    artifact.write_text("keep me", encoding="utf-8")
    manager = _make_bookmark_manager(root)
    bookmark = manager.add_bookmark(
        Bookmark(
            id=9,
            url="https://example.com/keep-trash",
            title="Keep trash",
            extracted_text_path=str(artifact),
        )
    )
    manager.delete_bookmark(bookmark.id)

    def fail_bundle(*_args, **_kwargs):
        raise OSError("simulated full disk")

    result = manager.purge_trash(
        [bookmark.id],
        recovery_bundle_factory=fail_bundle,
    )

    assert not result.success
    assert result.purged_ids == ()
    assert result.failed_ids == (bookmark.id,)
    assert "simulated full disk" in result.errors[0]
    assert artifact.read_text(encoding="utf-8") == "keep me"
    assert manager.get_bookmark(bookmark.id, include_deleted=True).is_deleted


def test_trash_purge_coverage_failure_keeps_records_and_artifacts(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    snapshots = root / "snapshots"
    snapshots.mkdir()
    artifact = snapshots / "12.html"
    artifact.write_text("saved copy", encoding="utf-8")
    manager = _make_bookmark_manager(root)
    bookmark = manager.add_bookmark(
        Bookmark(
            id=12,
            url="https://example.com/reject-incomplete-recovery",
            title="Reject incomplete recovery",
            snapshot_path=str(artifact),
        )
    )
    manager.move_to_trash(bookmark.id)

    def reject_coverage(*_args, **_kwargs):
        raise ValueError("simulated missing artifact coverage")

    result = manager.purge_trash(
        [bookmark.id],
        recovery_coverage_verifier=reject_coverage,
    )

    assert not result.success
    assert result.purged_ids == ()
    assert result.failed_ids == (bookmark.id,)
    assert "missing artifact coverage" in result.errors[0]
    assert Path(result.recovery_bundle).is_file()
    assert artifact.read_text(encoding="utf-8") == "saved copy"
    assert manager.get_bookmark(bookmark.id, include_deleted=True).is_deleted


def test_sqlite_trash_purge_verifies_the_stored_record(tmp_path):
    root = tmp_path / "sqlite-library"
    root.mkdir()
    manager = BookmarkManager(
        CategoryManager(filepath=root / "categories.json"),
        TagManager(filepath=root / "tags.json"),
        filepath=root / "master_bookmarks.sqlite",
        storage_backend="sqlite",
    )
    bookmark = manager.add_bookmark(
        Bookmark(
            id=22,
            url="https://example.com/sqlite-trash",
            title="SQLite trash",
        )
    )
    manager.move_to_trash(bookmark.id)

    result = manager.purge_trash([bookmark.id])

    assert result.success, result.errors
    assert result.purged_ids == (bookmark.id,)
    report = verify_recovery_bundle_coverage(
        result.recovery_bundle,
        bookmark_ids=[bookmark.id],
    )
    assert report.valid
    assert report.storage_backend == "sqlite"
    assert manager.get_bookmark(bookmark.id, include_deleted=True) is None
