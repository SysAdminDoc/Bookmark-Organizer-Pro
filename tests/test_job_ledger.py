"""Local capture/index job ledger contracts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.ingest import ContentIngestor
from bookmark_organizer_pro.services.job_ledger import JobLedger, redact_job_error, safe_domain
from bookmark_organizer_pro.services.vector_store import VectorStore


def test_job_ledger_redacts_bounds_filters_and_aggregates(tmp_path: Path):
    ledger = JobLedger(tmp_path / "jobs.json")
    first = ledger.start(
        "snapshot",
        bookmark_id=7,
        url_or_domain="https://user:pass@Private.Example/path?q=secret",
        backend="python",
    )
    first.fail(
        "GET https://private.example/secret?token=abc Authorization: Bearer abc.def",
        retryable=True,
        bytes_processed=12,
    )
    second = ledger.start("embedding", bookmark_id=8, backend="memory/fake")
    second.succeed(bytes_processed=200)

    records = ledger.list_records(outcome="failure", retryable=True)
    assert len(records) == 1
    assert records[0].domain == "private.example"
    assert "private.example/secret" not in records[0].error
    assert "abc.def" not in records[0].error
    assert records[0].attempt == 1

    retry = ledger.start("snapshot", bookmark_id=7, url_or_domain="private.example")
    retry.fail("timeout", retryable=True)
    assert retry.record.attempt == 2

    health = ledger.health()
    assert health["jobs"] == 3
    assert health["failures"] == 2
    assert health["retryable_failures"] == 2
    assert health["processed_bytes"] == 212
    assert health["by_type"]["embedding"]["bytes"] == 200
    assert health["privacy"] == {
        "content_stored": False,
        "urls_stored": False,
        "telemetry": False,
    }

    raw = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    assert "/path" not in raw
    assert "user:pass" not in raw
    assert ledger.clear(job_type="snapshot", outcome="failure") == 2
    assert [item.job_type for item in ledger.list_records()] == ["embedding"]


def test_job_ledger_retention_is_bounded_and_corruption_is_safe(tmp_path: Path):
    path = tmp_path / "jobs.json"
    ledger = JobLedger(path, max_records=10)
    for index in range(15):
        ledger.start("metadata", bookmark_id=index).succeed()
    assert len(ledger.list_records()) == 10
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["schema"] == "bookmark-organizer-pro/job-ledger"
    assert len(payload["document"]["jobs"]) == 10

    path.write_text("{broken", encoding="utf-8")
    assert len(ledger.list_records()) == 10
    assert ledger.storage_status.state == "recovered"
    assert ledger.storage_status.quarantine_path is not None


def test_error_and_domain_helpers_do_not_leak_sensitive_inputs():
    assert safe_domain("https://name:pw@BÜCHER.example:443/a?token=x") == "xn--bcher-kva.example"
    error = redact_job_error("password=hunter2 https://example.test/private\nnext")
    assert "hunter2" not in error
    assert "/private" not in error
    assert "\n" not in error


def test_ingest_records_content_bytes_without_storing_content(tmp_path: Path):
    ledger = JobLedger(tmp_path / "jobs.json")
    html = "<html><title>Private heading</title><body><p>alpha beta gamma delta</p></body></html>"
    result = ContentIngestor(job_ledger=ledger).ingest_url(
        "https://example.com/research/private",
        bookmark_id=42,
        html=html,
        store_text=False,
    )
    assert result.success
    record = ledger.list_records()[0]
    assert record.job_type == "ingest"
    assert record.outcome == "success"
    assert record.bookmark_id == 42
    assert record.domain == "example.com"
    assert record.bytes_processed > 0
    persisted = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    assert "Private heading" not in persisted
    assert "/research/private" not in persisted


def test_vector_upsert_records_backend_and_processed_bytes(tmp_path: Path):
    ledger = JobLedger(tmp_path / "jobs.json")

    class FakeEmbedder:
        available = True
        backend = "fake"
        dim = 2

        @staticmethod
        def embed(texts):
            return [[1.0, 0.0] for _ in texts]

    store = VectorStore(FakeEmbedder(), store_dir=tmp_path / "vectors", job_ledger=ledger)
    store._backend = "memory"
    chunks = [{"id": 0, "text": "sensitive body", "char_start": 0, "char_end": 14}]
    assert store.upsert_bookmark(5, chunks) == 1
    record = ledger.list_records()[0]
    assert record.outcome == "success"
    assert record.backend == "memory/fake"
    assert record.bytes_processed == len("sensitive body".encode())
    assert "sensitive body" not in (tmp_path / "jobs.json").read_text(encoding="utf-8")


def test_snapshot_archiver_records_success_backend_and_size(tmp_path: Path):
    from bookmark_organizer_pro.services.snapshot import SnapshotArchiver

    ledger = JobLedger(tmp_path / "jobs.json")
    bookmark = Bookmark(id=9, url="https://example.com/article", title="Not persisted")
    archiver = SnapshotArchiver(
        snapshots_dir=tmp_path / "snapshots",
        failure_store=SimpleNamespace(clear_for_bookmark=lambda _bookmark: None),
        job_ledger=ledger,
    )

    def capture(_url, path):
        path.write_text("<html>ok</html>", encoding="utf-8")
        return True, str(path)

    capture.__name__ = "_snapshot_monolith"
    archiver._snapshot_monolith = capture
    ok, _path = archiver.snapshot(bookmark)
    assert ok
    record = ledger.list_records()[0]
    assert record.job_type == "snapshot"
    assert record.backend == "monolith"
    assert record.bytes_processed == len("<html>ok</html>")
    assert "Not persisted" not in (tmp_path / "jobs.json").read_text(encoding="utf-8")
