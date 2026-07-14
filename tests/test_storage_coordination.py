import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from bookmark_organizer_pro.core import (
    SQLiteStorageManager,
    StorageConflictError,
    StorageManager,
    StorageRecoveryRequiredError,
    StorageVersionError,
)
from bookmark_organizer_pro.managers.bookmarks import BookmarkManager
from bookmark_organizer_pro.models import Bookmark


def _bookmark(bookmark_id: int, name: str) -> Bookmark:
    return Bookmark(
        id=bookmark_id,
        url=f"https://{name.lower()}.example",
        title=name,
        tags=["preserved"],
        custom_data={"source_id": f"source-{bookmark_id}"},
    )


@pytest.mark.parametrize("backend,suffix", [("json", ".json"), ("sqlite", ".sqlite")])
def test_independent_managers_interleave_writes_without_loss(tmp_path, backend, suffix):
    path = tmp_path / f"bookmarks{suffix}"
    first = BookmarkManager(object(), object(), filepath=path, storage_backend=backend)
    second = BookmarkManager(object(), object(), filepath=path, storage_backend=backend)

    first.add_bookmark(_bookmark(1, "First"))
    second.add_bookmark(_bookmark(2, "Second"))
    first.update_bookmark(1, title="First updated")
    second.update_bookmark(2, title="Second updated")

    verifier = BookmarkManager(object(), object(), filepath=path, storage_backend=backend)
    assert {bookmark.id for bookmark in verifier.get_all_bookmarks()} == {1, 2}
    assert verifier.get_bookmark(1).title == "First updated"
    assert verifier.get_bookmark(2).title == "Second updated"
    assert verifier.storage.current_revision() == 4


@pytest.mark.parametrize("backend,suffix", [("json", ".json"), ("sqlite", ".sqlite")])
@pytest.mark.parametrize("operation", ["add", "update", "delete"])
def test_failed_bookmark_mutations_restore_memory_revision_and_disk(
    tmp_path, monkeypatch, backend, suffix, operation
):
    path = tmp_path / f"transaction{suffix}"
    manager = BookmarkManager(object(), object(), filepath=path, storage_backend=backend)
    manager.add_bookmark(_bookmark(1, "Original"))
    before_state = [bookmark.to_dict() for bookmark in manager.get_all_bookmarks()]
    before_revision = manager._storage_revision
    before_bytes = path.read_bytes()

    if operation == "add":
        mutate = lambda: manager.add_bookmark(_bookmark(2, "Added"))
    elif operation == "update":
        bookmark = manager.get_bookmark(1)
        bookmark.title = "Changed before update"
        mutate = lambda: manager.update_bookmark(bookmark)
    else:
        mutate = lambda: manager.delete_bookmark(1)

    monkeypatch.setattr(manager.storage, "save", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        mutate()

    assert [bookmark.to_dict() for bookmark in manager.get_all_bookmarks()] == before_state
    assert manager._storage_revision == before_revision
    assert path.read_bytes() == before_bytes


def test_nested_batch_failure_rolls_back_even_when_inner_error_is_caught(tmp_path):
    path = tmp_path / "nested-batch.json"
    manager = BookmarkManager(object(), object(), filepath=path, storage_backend="json")
    manager.add_bookmark(_bookmark(1, "Original"))
    before_state = [bookmark.to_dict() for bookmark in manager.get_all_bookmarks()]
    before_revision = manager._storage_revision
    before_bytes = path.read_bytes()

    with manager.batch():
        manager.add_bookmark(_bookmark(2, "Outer"))
        try:
            with manager.batch():
                manager.add_bookmark(_bookmark(3, "Inner"))
                raise RuntimeError("abort nested transaction")
        except RuntimeError:
            pass
        manager.add_bookmark(_bookmark(4, "After caught failure"))

    assert [bookmark.to_dict() for bookmark in manager.get_all_bookmarks()] == before_state
    assert manager._storage_revision == before_revision
    assert path.read_bytes() == before_bytes


def test_bookmark_update_rejects_identity_changes_and_repairs_live_alias(tmp_path):
    manager = BookmarkManager(
        object(), object(), filepath=tmp_path / "immutable-id.json", storage_backend="json"
    )
    manager.add_bookmark(_bookmark(1, "Original"))

    with pytest.raises(ValueError, match="immutable"):
        manager.update_bookmark(1, id=2)
    aliased = manager.get_bookmark(1)
    aliased.id = 2
    with pytest.raises(ValueError, match="immutable"):
        manager.update_bookmark(aliased)

    assert list(manager.bookmarks) == [1]
    assert manager.get_bookmark(1).id == 1
    assert manager.get_bookmark(2) is None


@pytest.mark.parametrize("storage_type,suffix", [(StorageManager, ".json"), (SQLiteStorageManager, ".sqlite")])
def test_simultaneous_stale_writers_commit_once_and_surface_conflict(
    tmp_path, storage_type, suffix
):
    path = tmp_path / f"bookmarks{suffix}"
    left = storage_type(path)
    right = storage_type(path)
    assert left.load() == []
    assert right.load() == []
    barrier = threading.Barrier(2)
    outcomes = []

    def write(storage, bookmark):
        barrier.wait()
        try:
            storage.save([bookmark.to_dict()], expected_revision=0)
            outcomes.append("saved")
        except StorageConflictError:
            outcomes.append("conflict")

    threads = [
        threading.Thread(target=write, args=(left, _bookmark(1, "Left"))),
        threading.Thread(target=write, args=(right, _bookmark(2, "Right"))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == ["conflict", "saved"]
    assert storage_type(path).current_revision() == 1


def test_json_migrations_are_ordered_verified_and_idempotent(tmp_path):
    path = tmp_path / "bookmarks.json"
    backup_dir = tmp_path / "backups"
    safepoint_dir = backup_dir / "safepoints"
    original = _bookmark(7, "Legacy").to_dict()
    path.write_text(
        json.dumps({"version": 1, "metadata": {"source": "fixture"}, "data": [original]}),
        encoding="utf-8",
    )

    with (
        patch("bookmark_organizer_pro.core.storage_manager.BACKUP_DIR", backup_dir),
        patch("bookmark_organizer_pro.core.storage_manager.SAFEPOINT_DIR", safepoint_dir),
    ):
        storage = StorageManager(path)
        loaded = storage.load()
        first_safepoints = list(safepoint_dir.glob("*.json"))
        assert len(first_safepoints) == 1
        hash_path = first_safepoints[0].with_suffix(".sha256")
        assert hash_path.is_file()
        assert hash_path.read_text(encoding="utf-8").split()[0] == hashlib.sha256(
            first_safepoints[0].read_bytes()
        ).hexdigest()

        reloaded = StorageManager(path).load()
        assert len(list(safepoint_dir.glob("*.json"))) == 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == StorageManager.CURRENT_VERSION
    assert payload["revision"] == 0
    assert loaded[0].to_dict() == original
    assert reloaded[0].to_dict() == original


def test_json_future_version_is_read_only_with_upgrade_guidance(tmp_path):
    path = tmp_path / "bookmarks.json"
    path.write_text(
        json.dumps(
            {
                "version": StorageManager.CURRENT_VERSION + 1,
                "revision": 9,
                "data": [_bookmark(1, "Future").to_dict()],
            }
        ),
        encoding="utf-8",
    )
    original = path.read_bytes()
    storage = StorageManager(path)

    assert storage.load() == []
    assert storage.status.state == "future_version"
    with pytest.raises(StorageVersionError, match="newer than supported"):
        storage.save([])
    assert path.read_bytes() == original


def test_sqlite_v1_migration_preserves_fields_and_creates_verified_safepoint(tmp_path):
    path = tmp_path / "bookmarks.sqlite"
    backup_dir = tmp_path / "backups"
    original = _bookmark(2**63 + 5, "Legacy sqlite").to_dict()
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES('schema_version', '1')")
        conn.execute(
            SQLiteStorageManager.CREATE_BOOKMARKS_SQL.replace(
                "id TEXT PRIMARY KEY", "id INTEGER PRIMARY KEY"
            )
        )
        conn.execute(
            """
            INSERT INTO bookmarks(
                id, position, url, title, category, parent_category,
                created_at, modified_at, is_pinned, read_later, payload_json
            ) VALUES (?, 0, ?, ?, '', '', '', '', 0, 0, ?)
            """,
            (2**63 - 1, original["url"], original["title"], json.dumps(original)),
        )

    with patch("bookmark_organizer_pro.core.sqlite_storage.BACKUP_DIR", backup_dir):
        storage = SQLiteStorageManager(path)
        loaded = storage.load()
        safepoints = list((backup_dir / "migrations").glob("*.sqlite"))
        assert len(safepoints) == 1
        digest = hashlib.sha256(safepoints[0].read_bytes()).hexdigest()
        assert safepoints[0].with_suffix(".sha256").read_text(
            encoding="utf-8"
        ).split()[0] == digest
        SQLiteStorageManager(path)
        assert len(list((backup_dir / "migrations").glob("*.sqlite"))) == 1

    assert loaded[0].to_dict() == original
    assert storage.get_metadata()["schema_version"] == str(storage.CURRENT_SCHEMA)
    with sqlite3.connect(path) as conn:
        id_type = next(
            row[2] for row in conn.execute("PRAGMA table_info(bookmarks)") if row[1] == "id"
        )
    assert id_type == "TEXT"


def test_sqlite_future_schema_is_not_downgraded(tmp_path):
    path = tmp_path / "bookmarks.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO metadata VALUES('schema_version', '99')")

    storage = SQLiteStorageManager(path)
    assert storage.status.state == "future_version"
    with pytest.raises(StorageVersionError, match="newer than supported"):
        storage.save([])
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "99"


def test_sqlite_corrupt_file_is_preserved_and_manager_stays_write_locked(tmp_path):
    path = tmp_path / "bookmarks.sqlite"
    recovery_dir = tmp_path / "recovery"
    damaged = b"SQLite format 3\x00" + (b"damaged" * 50)
    path.write_bytes(damaged)

    with patch("bookmark_organizer_pro.core.sqlite_storage.RECOVERY_DIR", recovery_dir):
        manager = BookmarkManager(object(), object(), filepath=path, storage_backend="sqlite")

        assert manager.recovery_required
        assert manager.get_all_bookmarks() == []
        preserved = list(recovery_dir.glob("*.sqlite"))
        assert len(preserved) == 1
        assert preserved[0].read_bytes() == damaged
        with pytest.raises(StorageRecoveryRequiredError, match="Restore a verified backup"):
            manager.add_bookmark(_bookmark(9, "Blocked"))
        assert path.read_bytes() == damaged


def test_sqlite_malformed_row_requires_explicit_salvage(tmp_path):
    path = tmp_path / "bookmarks.sqlite"
    recovery_dir = tmp_path / "recovery"
    storage = SQLiteStorageManager(path)
    storage.save([_bookmark(1, "Valid").to_dict()])
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            INSERT INTO bookmarks(id, position, url, title, payload_json)
            VALUES('2', 2, 'https://bad.example', 'Bad', '{not json')
            """
        )
        conn.commit()
    finally:
        conn.close()

    with patch("bookmark_organizer_pro.core.sqlite_storage.RECOVERY_DIR", recovery_dir):
        assert storage.load() == []
        assert storage.status.state == "corrupt"
        recovered = storage.salvage()
        assert [bookmark.id for bookmark in recovered] == [1]
        preserved = Path(storage.commit_salvage(recovered))

    assert preserved.is_file()
    assert [bookmark.id for bookmark in storage.load()] == [1]
    assert storage.status.state == "valid"


def test_sqlite_restore_rejects_tampering_and_recovers_verified_backup(tmp_path):
    path = tmp_path / "bookmarks.sqlite"
    backup_dir = tmp_path / "backups"
    recovery_dir = tmp_path / "recovery"
    with (
        patch("bookmark_organizer_pro.core.sqlite_storage.BACKUP_DIR", backup_dir),
        patch("bookmark_organizer_pro.core.sqlite_storage.RECOVERY_DIR", recovery_dir),
    ):
        storage = SQLiteStorageManager(path)
        storage.save([_bookmark(1, "First").to_dict()])
        storage.save([_bookmark(2, "Second").to_dict()])
        backup_name = storage.get_backups()[0][0]
        backup_path = backup_dir / backup_name
        original_backup = backup_path.read_bytes()

        backup_path.write_bytes(original_backup + b"tampered")
        assert not storage.restore_backup(backup_name)
        backup_path.write_bytes(original_backup)

        path.write_bytes(b"broken sqlite")
        damaged = SQLiteStorageManager(path)
        assert damaged.recovery_required
        assert damaged.restore_backup(backup_name)
        assert [bookmark.id for bookmark in damaged.load()] == [1]
