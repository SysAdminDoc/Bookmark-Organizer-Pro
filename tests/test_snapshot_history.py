from pathlib import Path

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.snapshot import SnapshotArchiver, SnapshotFailureStore
from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore


def test_snapshot_history_retains_versions_and_reports_content_provenance(tmp_path: Path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    current = snapshots / "7.html"
    store = SnapshotHistoryStore(snapshots, max_versions=2)

    current.write_text("<main>First value</main>", encoding="utf-8")
    first = store.record(
        7, current, source_url="https://example.com/a",
        resolved_url="https://example.com/a", status_code=200, backend="python",
        captured_at="2026-01-01T00:00:00+00:00",
    )
    current.write_text("<main>Second value</main>", encoding="utf-8")
    second = store.record(
        7, current, source_url="https://example.com/a",
        resolved_url="https://example.com/b", status_code=301, backend="python",
        captured_at="2026-01-02T00:00:00+00:00",
    )
    report = store.change_report(first.version_id, second.version_id)
    assert report["content_changed"] is True
    assert report["redirect_changed"] is True
    assert report["status_changed"] is True
    assert any("Second value" in line for line in report["diff"])

    current.write_text("<main>Third value</main>", encoding="utf-8")
    third = store.record(
        7, current, source_url="https://example.com/a", status_code=200,
        backend="browser-extension", captured_at="2026-01-03T00:00:00+00:00",
    )
    versions = store.list_versions(7)
    assert [item.version_id for item in versions] == [third.version_id, second.version_id]
    assert not Path(first.path).exists()
    assert Path(second.path).exists()


def test_snapshot_archiver_records_every_successful_recapture(tmp_path: Path):
    snapshots = tmp_path / "snapshots"
    history = SnapshotHistoryStore(snapshots, max_versions=5)
    archiver = SnapshotArchiver(
        snapshots,
        failure_store=SnapshotFailureStore(tmp_path / "failures.json"),
        history_store=history,
    )
    bookmark = Bookmark(id=9, url="https://example.com", title="Example")
    generation = iter(("one", "two"))

    def capture(_url, out_path):
        out_path.write_text(f"<main>{next(generation)}</main>", encoding="utf-8")
        archiver._last_provenance = {"resolved_url": "https://example.com/final", "status_code": 200}
        return True, str(out_path)

    archiver._snapshot_monolith = capture
    assert archiver.snapshot(bookmark)[0] is True
    assert archiver.snapshot(bookmark)[0] is True

    versions = history.list_versions(9)
    assert len(versions) == 2
    assert versions[0].sha256 != versions[1].sha256
    assert all(Path(version.path).exists() for version in versions)


def test_unassigned_bookmark_histories_have_independent_retention(tmp_path: Path):
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    current = snapshots / "pending.html"
    store = SnapshotHistoryStore(snapshots, max_versions=1)

    current.write_text("<main>First URL</main>", encoding="utf-8")
    first = store.record(
        None, current, source_url="https://one.example",
        captured_at="2026-01-01T00:00:00+00:00",
    )
    current.write_text("<main>Second URL</main>", encoding="utf-8")
    second = store.record(
        None, current, source_url="https://two.example",
        captured_at="2026-01-02T00:00:00+00:00",
    )

    assert Path(first.path).is_file()
    assert Path(second.path).is_file()
    assert Path(first.path).parent != Path(second.path).parent
