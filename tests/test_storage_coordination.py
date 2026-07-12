import hashlib
import json
import sqlite3
import threading
from unittest.mock import patch

import pytest

from bookmark_organizer_pro.core import (
    SQLiteStorageManager,
    StorageConflictError,
    StorageManager,
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

    with pytest.raises(StorageVersionError, match="newer than supported"):
        SQLiteStorageManager(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()[0] == "99"
