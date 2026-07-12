"""Recovery and coordination contracts for versioned service sidecars."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentConflictError,
    AtomicDocumentRecoveryError,
    AtomicDocumentStore,
    require_list_document,
)


def make_store(path: Path) -> AtomicDocumentStore:
    return AtomicDocumentStore(
        path,
        schema="tests/items",
        default_factory=list,
        validator=require_list_document,
    )


def test_legacy_document_migrates_with_version_revision_and_integrity(tmp_path: Path):
    path = tmp_path / "items.json"
    path.write_text('[{"id": 1}]', encoding="utf-8")

    store = make_store(path)
    assert store.load() == [{"id": 1}]
    envelope = json.loads(path.read_text(encoding="utf-8"))

    assert envelope["schema"] == "tests/items"
    assert envelope["version"] == 1
    assert envelope["revision"] == 1
    assert len(envelope["checksum"]) == 64
    assert json.loads(Path(f"{path}.bak").read_text(encoding="utf-8")) == [{"id": 1}]


def test_corrupt_document_recovers_verified_backup_and_quarantines_exact_bytes(tmp_path: Path):
    path = tmp_path / "items.json"
    store = make_store(path)
    store.save([{"id": 1}])
    store.save([{"id": 2}])
    damaged = b'{"truncated":'
    path.write_bytes(damaged)

    assert store.load() == [{"id": 1}]
    assert store.status.state == "recovered"
    assert store.status.quarantine_path is not None
    assert store.status.quarantine_path.read_bytes() == damaged
    assert make_store(path).load() == [{"id": 1}]


def test_unrecoverable_document_fails_closed_until_repaired(tmp_path: Path):
    path = tmp_path / "items.json"
    path.write_text("{broken", encoding="utf-8")
    store = make_store(path)

    assert store.load() == []
    assert store.status.recovery_required
    with pytest.raises(AtomicDocumentRecoveryError):
        store.update(lambda values: values.append({"id": 1}))
    assert path.read_text(encoding="utf-8") == "{broken"


def test_optimistic_save_rejects_stale_revision(tmp_path: Path):
    path = tmp_path / "items.json"
    first = make_store(path)
    second = make_store(path)
    first.load()
    second.load()
    first.save([{"id": 1}], expected_revision=0)

    with pytest.raises(AtomicDocumentConflictError):
        second.save([{"id": 2}], expected_revision=0)
    assert make_store(path).load() == [{"id": 1}]


def test_concurrent_updates_share_one_lock_held_read_modify_write(tmp_path: Path):
    path = tmp_path / "items.json"
    stores = [make_store(path), make_store(path)]
    barrier = threading.Barrier(2)

    def append(store: AtomicDocumentStore, value: int):
        barrier.wait()
        store.update(lambda items: items.append({"id": value}))

    threads = [threading.Thread(target=append, args=(stores[index], index), daemon=True) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert sorted(item["id"] for item in make_store(path).load()) == [0, 1]


@pytest.mark.parametrize(
    ("legacy", "factory", "expected_count"),
    [
        (
            [{"id": "flow-1", "name": "Trail", "steps": []}],
            lambda path: __import__("bookmark_organizer_pro.services.flows", fromlist=["FlowManager"]).FlowManager(
                path
            ),
            1,
        ),
        (
            [
                {
                    "id": "feed-1",
                    "url": "https://example.com/feed.xml",
                    "name": "Example",
                }
            ],
            lambda path: __import__(
                "bookmark_organizer_pro.services.rss_feeds", fromlist=["FeedRegistry"]
            ).FeedRegistry(path),
            1,
        ),
        (
            [{"id": "smart-1", "name": "Saved", "filters": {}}],
            lambda path: __import__(
                "bookmark_organizer_pro.services.smart_collections",
                fromlist=["SmartCollectionManager"],
            ).SmartCollectionManager(path),
            1,
        ),
        (
            {"highlights": []},
            lambda path: __import__(
                "bookmark_organizer_pro.services.reader_annotations",
                fromlist=["ReaderAnnotationStore"],
            ).ReaderAnnotationStore(path),
            0,
        ),
        (
            {"version": 1, "jobs": []},
            lambda path: __import__("bookmark_organizer_pro.services.job_ledger", fromlist=["JobLedger"]).JobLedger(
                path
            ),
            0,
        ),
    ],
)
def test_service_sidecars_migrate_legacy_documents(tmp_path, legacy, factory, expected_count):
    path = tmp_path / "sidecar.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    service = factory(path)
    if hasattr(service, "list_flows"):
        items = service.list_flows()
    elif hasattr(service, "list_feeds"):
        items = service.list_feeds()
    elif hasattr(service, "list_all"):
        items = service.list_all()
    elif hasattr(service, "list_records"):
        items = service.list_records()
    else:
        items = service.list_all()

    assert len(items) == expected_count
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["version"] == 1
    assert envelope["revision"] == 1
    assert service.storage_status.state == "valid"
