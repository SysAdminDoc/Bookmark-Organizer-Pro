"""Integration coverage for checksummed full-library recovery bundles."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from bookmark_organizer_pro.cli import BookmarkCLI
from bookmark_organizer_pro.core.sqlite_storage import SQLiteStorageManager
from bookmark_organizer_pro.services.recovery_bundle import (
    INDEX_NAME,
    MANIFEST_NAME,
    create_recovery_bundle,
    restore_recovery_bundle,
    validate_recovery_bundle,
)


def _write_library(root: Path, *, title: str = "Original") -> None:
    (root / "snapshots").mkdir(parents=True)
    (root / "extracted").mkdir()
    snapshot = root / "snapshots" / "1.html"
    extracted = root / "extracted" / "1.txt"
    snapshot.write_text("<html>saved</html>", encoding="utf-8")
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
        "flows.json": {"version": 1, "flows": [{"name": "Investigation"}]},
        "feeds.json": {"version": 1, "feeds": [{"url": "https://example.com/feed"}]},
        "smart_collections.json": {"version": 1, "collections": [{"name": "Research"}]},
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
        "flows.json",
        "feeds.json",
        "smart_collections.json",
        "snapshots/1.html",
        "extracted/1.txt",
    }.issubset(report.contents)

    result = restore_recovery_bundle(bundle, data_dir=restored, dry_run=False)
    assert result.applied
    assert Path(result.rollback_bundle).is_file()
    assert (restored / "snapshots" / "1.html").read_text(encoding="utf-8") == "<html>saved</html>"
    payload = json.loads((restored / "master_bookmarks.json").read_text(encoding="utf-8"))
    bookmark = payload["data"][0]
    assert bookmark["snapshot_path"] == str((restored / "snapshots" / "1.html").resolve())
    assert bookmark["extracted_text_path"] == str((restored / "extracted" / "1.txt").resolve())
    assert json.loads((restored / "reader_annotations.json").read_text())["highlights"]


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
