import base64
import hashlib
import json
import zipfile
from pathlib import Path

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.job_ledger import JobLedger
from bookmark_organizer_pro.services.recovery_bundle import (
    create_recovery_bundle,
    restore_recovery_bundle,
)
from bookmark_organizer_pro.services.snapshot import (
    SnapshotArchiver,
    SnapshotFailureStore,
    classify_snapshot_payload,
    ensure_snapshot_manifest,
    load_snapshot_manifest,
    open_snapshot_file,
    snapshot_manifest_path,
)
from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore
from bookmark_organizer_pro.services.zip_export import ZipExporter
from bookmark_organizer_pro.ui.reader_view import reader_empty_message
from bookmark_organizer_pro.url_utils import URLUtilities


PDF_BYTES = (
    b"%PDF-1.7\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 1\n0000000000 65535 f \n"
    b"trailer\n<< /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
)
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeResponse:
    def __init__(self, payload: bytes, content_type: str):
        self.payload = payload
        self.headers = {
            "content-type": content_type,
            "content-length": str(len(payload)),
        }
        self.status_code = 200
        self.encoding = "utf-8"
        self.closed = False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65_536):
        del chunk_size
        midpoint = max(1, len(self.payload) // 2)
        yield self.payload[:midpoint]
        yield self.payload[midpoint:]

    def close(self):
        self.closed = True


def _archiver(tmp_path: Path) -> SnapshotArchiver:
    snapshots = tmp_path / "snapshots"
    return SnapshotArchiver(
        snapshots,
        failure_store=SnapshotFailureStore(tmp_path / "failures.json"),
        job_ledger=JobLedger(tmp_path / "jobs.json"),
        history_store=SnapshotHistoryStore(snapshots),
    )


def _use_builtin_backend(monkeypatch, archiver: SnapshotArchiver, response: FakeResponse):
    monkeypatch.setattr(URLUtilities, "check_safe_url", lambda _url: (True, "allowed"))
    monkeypatch.setattr(archiver, "_snapshot_monolith", lambda *_args: (False, "missing"))
    monkeypatch.setattr(archiver, "_snapshot_singlefile", lambda *_args: (False, "missing"))
    monkeypatch.setattr(archiver, "_snapshot_playwright", lambda *_args: (False, "missing"))
    from bookmark_organizer_pro.services.egress import public_egress

    monkeypatch.setattr(public_egress, "get", lambda *_args, **_kwargs: response)


def test_pdf_capture_round_trips_exact_bytes_and_writes_manifest(monkeypatch, tmp_path):
    archiver = _archiver(tmp_path)
    response = FakeResponse(PDF_BYTES, "application/pdf; charset=binary")
    _use_builtin_backend(monkeypatch, archiver, response)
    bookmark = Bookmark(id=7, url="https://example.com/report", title="Report")

    ok, path_text = archiver.snapshot(bookmark)

    assert ok is True
    artifact = Path(path_text)
    assert artifact.name == "7.pdf"
    assert artifact.read_bytes() == PDF_BYTES
    assert response.closed is True
    manifest = load_snapshot_manifest(artifact)
    assert manifest.to_dict() == {
        "schema": "bookmark-organizer-pro/snapshot-manifest",
        "schema_version": 1,
        "artifact_name": "7.pdf",
        "backend": "python",
        "captured_at": bookmark.snapshot_at,
        "final_url": "https://example.com/report",
        "mime_type": "application/pdf",
        "representation": "binary",
        "sha256": hashlib.sha256(PDF_BYTES).hexdigest(),
        "size_bytes": len(PDF_BYTES),
        "source_url": "https://example.com/report",
        "status_code": 200,
    }
    assert bookmark.snapshot_mime_type == "application/pdf"
    assert bookmark.snapshot_sha256 == manifest.sha256
    assert bookmark.snapshot_backend == "python"
    version = archiver.history_store.list_versions(7)[0]
    assert Path(version.path).suffix == ".pdf"
    assert Path(version.path).read_bytes() == PDF_BYTES
    assert version.mime_type == "application/pdf"
    assert version.representation == "binary"
    assert not list(artifact.parent.glob(".*.tmp"))


def test_unsupported_or_mismatched_binary_fails_without_artifact(monkeypatch, tmp_path):
    for payload, mime_type in (
        (b"PK\x03\x04unsupported archive", "application/zip"),
        (PDF_BYTES, "text/html"),
    ):
        case_dir = tmp_path / hashlib.sha256(payload + mime_type.encode()).hexdigest()[:8]
        archiver = _archiver(case_dir)
        _use_builtin_backend(
            monkeypatch,
            archiver,
            FakeResponse(payload, mime_type),
        )
        bookmark = Bookmark(
            id=8,
            url="https://example.com/download",
            title="Download",
        )

        ok, message = archiver.snapshot(bookmark)

        assert ok is False
        assert "unsupported" in message or "conflicts" in message
        assert bookmark.snapshot_path == ""
        assert list((case_dir / "snapshots").iterdir()) == []


def test_html_capture_remains_bundled_html(monkeypatch, tmp_path):
    html = b"<!doctype html><html><body><main>Offline article</main><script>x()</script></body></html>"
    archiver = _archiver(tmp_path)
    _use_builtin_backend(
        monkeypatch,
        archiver,
        FakeResponse(html, "text/html; charset=utf-8"),
    )
    bookmark = Bookmark(id=9, url="https://example.com/article", title="Article")

    ok, path_text = archiver.snapshot(bookmark)

    assert ok is True
    artifact = Path(path_text)
    assert artifact.name == "9.html"
    assert b"Offline article" in artifact.read_bytes()
    assert b"<script" not in artifact.read_bytes()
    manifest = load_snapshot_manifest(artifact)
    assert manifest.mime_type == "text/html"
    assert manifest.representation == "bundled-html"


def test_signature_classifier_is_allowlisted_and_rejects_spoofing():
    pdf_format, error = classify_snapshot_payload(PDF_BYTES, "application/octet-stream")
    assert error == ""
    assert pdf_format is not None
    assert (pdf_format.mime_type, pdf_format.extension) == ("application/pdf", ".pdf")

    image_format, error = classify_snapshot_payload(PNG_BYTES, "image/png")
    assert error == ""
    assert image_format is not None
    assert (image_format.mime_type, image_format.extension) == ("image/png", ".png")

    rejected, error = classify_snapshot_payload(PDF_BYTES, "image/png")
    assert rejected is None
    assert "conflicts" in error

    rejected, error = classify_snapshot_payload(b'{"html": "<main>not a page</main>"}', "application/json")
    assert rejected is None
    assert "unsupported" in error


def test_reader_routes_binary_snapshots_to_the_offline_copy():
    bookmark = Bookmark(
        id=12,
        url="https://example.com/report",
        title="Report",
        snapshot_mime_type="application/pdf",
    )

    message = reader_empty_message(bookmark)

    assert "verified PDF offline copy" in message
    assert "highlights require separately extracted text" in message


def test_legacy_html_snapshot_migrates_to_verified_manifest(tmp_path):
    artifact = tmp_path / "17.html"
    artifact.write_text("<html><body>Legacy</body></html>", encoding="utf-8")
    bookmark = Bookmark(
        id=17,
        url="https://example.com/legacy",
        title="Legacy",
        snapshot_path=str(artifact),
        snapshot_at="2026-07-01T12:00:00+00:00",
    )

    manifest = ensure_snapshot_manifest(bookmark)

    assert snapshot_manifest_path(artifact).is_file()
    assert manifest.backend == "legacy"
    assert manifest.mime_type == "text/html"
    assert bookmark.snapshot_sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_binary_export_preserves_extension_bytes_and_portable_manifest(tmp_path):
    artifact = tmp_path / "snapshots" / "21.pdf"
    artifact.parent.mkdir()
    artifact.write_bytes(PDF_BYTES)
    bookmark = Bookmark(
        id=21,
        url="https://example.com/report",
        title="Report",
        snapshot_path=str(artifact),
        snapshot_mime_type="application/pdf",
    )
    ensure_snapshot_manifest(bookmark)
    exporter = ZipExporter(tmp_path / "exports")

    ok, path_text = exporter.export_one(bookmark)

    assert ok is True
    with zipfile.ZipFile(path_text) as archive:
        assert "snapshot.pdf" in archive.namelist()
        assert "snapshot.html" not in archive.namelist()
        assert archive.read("snapshot.pdf") == PDF_BYTES
        manifest = json.loads(archive.read("snapshot-manifest.json"))
        assert manifest["artifact_name"] == "snapshot.pdf"
        assert manifest["mime_type"] == "application/pdf"
        assert manifest["sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()


def test_recovery_bundle_round_trips_binary_artifact_and_manifest(tmp_path):
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    artifact = source / "snapshots" / "24.pdf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(PDF_BYTES)
    bookmark = Bookmark(
        id=24,
        url="https://example.com/report",
        title="Report",
        snapshot_path=str(artifact.resolve()),
        snapshot_mime_type="application/pdf",
    )
    ensure_snapshot_manifest(bookmark)
    (source / "master_bookmarks.json").write_text(
        json.dumps({"version": 4, "data": [bookmark.to_dict()]}),
        encoding="utf-8",
    )

    bundle = create_recovery_bundle(tmp_path / "library.zip", data_dir=source)
    result = restore_recovery_bundle(bundle, data_dir=restored, dry_run=False)

    assert result.applied is True
    restored_artifact = restored / "snapshots" / "24.pdf"
    assert restored_artifact.read_bytes() == PDF_BYTES
    assert load_snapshot_manifest(restored_artifact).mime_type == "application/pdf"
    payload = json.loads(
        (restored / "master_bookmarks.json").read_text(encoding="utf-8")
    )
    assert payload["data"][0]["snapshot_path"] == str(restored_artifact.resolve())
    assert payload["data"][0]["snapshot_sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()


def test_open_snapshot_verifies_digest_before_launch(tmp_path):
    artifact = tmp_path / "31.pdf"
    artifact.write_bytes(PDF_BYTES)
    bookmark = Bookmark(
        id=31,
        url="https://example.com/report",
        title="Report",
        snapshot_path=str(artifact),
        snapshot_mime_type="application/pdf",
    )
    ensure_snapshot_manifest(bookmark)
    opened = []

    ok, _detail = open_snapshot_file(
        bookmark,
        opener=lambda uri: opened.append(uri) or True,
    )

    assert ok is True
    assert opened == [artifact.resolve().as_uri()]
    artifact.write_bytes(PDF_BYTES + b"tampered")
    ok, detail = open_snapshot_file(
        bookmark,
        opener=lambda uri: opened.append(uri) or True,
    )
    assert ok is False
    assert "digest" in detail or "size" in detail
    assert len(opened) == 1


def test_delete_snapshot_removes_binary_artifact_and_manifest(tmp_path):
    archiver = _archiver(tmp_path)
    artifact = tmp_path / "snapshots" / "33.pdf"
    artifact.write_bytes(PDF_BYTES)
    bookmark = Bookmark(
        id=33,
        url="https://example.com/report",
        title="Report",
        snapshot_path=str(artifact),
        snapshot_mime_type="application/pdf",
    )
    ensure_snapshot_manifest(bookmark)
    manifest_path = snapshot_manifest_path(artifact)

    assert archiver.delete_snapshot(bookmark) is True

    assert not artifact.exists()
    assert not manifest_path.exists()
    assert bookmark.snapshot_path == ""
    assert bookmark.snapshot_mime_type == ""
    assert bookmark.snapshot_sha256 == ""
    assert bookmark.snapshot_backend == ""


def test_failed_history_commit_restores_previous_current_artifact(
    monkeypatch,
    tmp_path,
):
    artifact = tmp_path / "snapshots" / "35.html"
    artifact.parent.mkdir()
    original = b"<html><body>Original copy</body></html>"
    artifact.write_bytes(original)
    bookmark = Bookmark(
        id=35,
        url="https://example.com/article",
        title="Article",
        snapshot_path=str(artifact),
        snapshot_mime_type="text/html",
    )
    original_manifest = ensure_snapshot_manifest(bookmark).to_dict()
    archiver = _archiver(tmp_path)

    class FailingHistory:
        @staticmethod
        def record(*_args, **_kwargs):
            raise RuntimeError("history unavailable")

    archiver.history_store = FailingHistory()
    _use_builtin_backend(
        monkeypatch,
        archiver,
        FakeResponse(
            b"<html><body>Replacement copy</body></html>",
            "text/html",
        ),
    )

    ok, message = archiver.snapshot(bookmark)

    assert ok is False
    assert "history unavailable" in message
    assert artifact.read_bytes() == original
    assert load_snapshot_manifest(artifact).to_dict() == original_manifest
    assert not list(artifact.parent.glob("*.rollback"))


def test_binary_history_reports_change_without_decoding(tmp_path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    current = snapshots / "40.pdf"
    store = SnapshotHistoryStore(snapshots)
    current.write_bytes(PDF_BYTES)
    first = store.record(
        40,
        current,
        source_url="https://example.com/one",
        mime_type="application/pdf",
        representation="binary",
        captured_at="2026-07-01T00:00:00+00:00",
    )
    current.write_bytes(PDF_BYTES.replace(b"/Catalog", b"/Pages  "))
    second = store.record(
        40,
        current,
        source_url="https://example.com/one",
        mime_type="application/pdf",
        representation="binary",
        captured_at="2026-07-02T00:00:00+00:00",
    )

    report = store.change_report(first.version_id, second.version_id)

    assert report["content_changed"] is True
    assert report["text_diff_available"] is False
    assert report["diff"] == []
