"""Optional SQLite bookmark storage with WAL mode."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from bookmark_organizer_pro.constants import BACKUP_DIR
from bookmark_organizer_pro.core.storage_manager import StorageConflictError, StorageVersionError
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


class SQLiteStorageManager:
    """SQLite persistence backend matching StorageManager's load/save shape."""

    CURRENT_SCHEMA = 2
    CREATE_BOOKMARKS_SQL = """
        CREATE TABLE IF NOT EXISTS bookmarks (
            id TEXT PRIMARY KEY,
            position INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            parent_category TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            modified_at TEXT NOT NULL DEFAULT '',
            is_pinned INTEGER NOT NULL DEFAULT 0,
            read_later INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL
        );
    """

    def __init__(self, filepath: Path):
        self.filepath = Path(filepath)
        self._lock = threading.Lock()
        self.revision = 0
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        # Autocommit mode keeps transaction ownership explicit. In particular,
        # save() can always issue BEGIN before its replacement transaction
        # instead of colliding with an implicit sqlite3 transaction.
        conn = sqlite3.connect(str(self.filepath), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        existed_before = self.filepath.exists()
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            version = int(row["value"]) if row else 0
            if version > self.CURRENT_SCHEMA:
                raise StorageVersionError(
                    f"SQLite schema {version} is newer than supported schema "
                    f"{self.CURRENT_SCHEMA}; upgrade the application before editing"
                )
            if existed_before and version < self.CURRENT_SCHEMA:
                self._create_migration_safepoint(conn, version)
            try:
                conn.execute("BEGIN IMMEDIATE")
                while version < self.CURRENT_SCHEMA:
                    migration = self.MIGRATIONS.get(version)
                    if migration is None:
                        raise StorageVersionError(
                            f"No migration is registered from SQLite schema {version}"
                        )
                    getattr(self, migration)(conn)
                    version += 1
                    conn.execute(
                        "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                        ("schema_version", str(version)),
                    )
                conn.execute(
                    "INSERT OR IGNORE INTO metadata(key, value) VALUES('revision', '0')"
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            revision_row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'revision'"
            ).fetchone()
            self.revision = int(revision_row["value"]) if revision_row else 0

    def _create_migration_safepoint(
        self, conn: sqlite3.Connection, source_version: int
    ) -> Path:
        """Back up and hash the pre-migration database before changing schema."""
        migration_dir = BACKUP_DIR / "migrations"
        migration_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = migration_dir / (
            f"{self.filepath.stem}_schema{source_version}_pre_{timestamp}.sqlite"
        )
        with closing(sqlite3.connect(str(destination))) as backup_conn:
            conn.backup(backup_conn)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        hash_path = destination.with_suffix(".sha256")
        hash_path.write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise OSError(f"Could not verify SQLite migration safepoint {destination}")
        return destination

    def _migrate_v0_to_v1(self, conn: sqlite3.Connection) -> None:
        conn.execute(self.CREATE_BOOKMARKS_SQL)
        self._create_indexes(conn)

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        self._ensure_text_id_schema(conn)
        conn.execute(
            "INSERT OR IGNORE INTO metadata(key, value) VALUES('revision', '0')"
        )

    MIGRATIONS = {
        0: "_migrate_v0_to_v1",
        1: "_migrate_v1_to_v2",
    }

    def _ensure_text_id_schema(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(bookmarks)").fetchall()
        if not rows:
            conn.execute(self.CREATE_BOOKMARKS_SQL)
            self._create_indexes(conn)
            return
        id_row = next((row for row in rows if row["name"] == "id"), None)
        if id_row and str(id_row["type"]).upper() == "TEXT":
            self._create_indexes(conn)
            return
        conn.execute("ALTER TABLE bookmarks RENAME TO bookmarks_old")
        conn.execute(self.CREATE_BOOKMARKS_SQL)
        conn.execute(
            """
            INSERT OR REPLACE INTO bookmarks(
                id, position, url, title, category, parent_category,
                created_at, modified_at, is_pinned, read_later, payload_json
            )
            SELECT
                CAST(id AS TEXT), position, url, title, category, parent_category,
                created_at, modified_at, is_pinned, read_later, payload_json
            FROM bookmarks_old
            """
        )
        conn.execute("DROP TABLE bookmarks_old")
        self._create_indexes(conn)

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON bookmarks(url)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_category ON bookmarks(category)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_created_at ON bookmarks(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_modified_at ON bookmarks(modified_at)"
        )

    def current_revision(self) -> int:
        """Return the revision visible to a new database connection."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'revision'"
            ).fetchone()
        return int(row["value"]) if row else 0

    def save(
        self,
        data: List[Dict],
        metadata: Dict = None,
        expected_revision: int | None = None,
    ) -> int:
        """Replace bookmark rows atomically unless the caller's revision is stale."""
        if not isinstance(data, list):
            raise ValueError("SQLite replacement save requires a list of bookmark objects")

        prepared = []
        seen_ids = set()
        for position, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"SQLite save rejected bookmark at index {position}: not an object")
            try:
                bookmark = Bookmark.from_dict(item)
                payload = bookmark.to_dict()
                encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            except Exception as exc:
                raise ValueError(
                    f"SQLite save rejected bookmark at index {position} "
                    f"(id={item.get('id', '?')}): {exc}"
                ) from exc
            bookmark_id = str(bookmark.id)
            if bookmark_id in seen_ids:
                raise ValueError(
                    f"SQLite save rejected duplicate bookmark id {bookmark_id} at index {position}"
                )
            seen_ids.add(bookmark_id)
            prepared.append((position, bookmark, encoded))

        payload_meta = dict(metadata or {})
        payload_meta.setdefault("saved_at", datetime.now().isoformat())
        payload_meta["count"] = len(prepared)
        with self._lock, closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT value FROM metadata WHERE key = 'revision'"
                ).fetchone()
                persisted_revision = int(row["value"]) if row else 0
                if (
                    expected_revision is not None
                    and expected_revision != persisted_revision
                ):
                    raise StorageConflictError(
                        f"Stale library revision {expected_revision}; current revision is "
                        f"{persisted_revision}. Reload and retry the change."
                    )
                next_revision = persisted_revision + 1
                conn.execute("DELETE FROM bookmarks")
                for position, bookmark, encoded in prepared:
                    conn.execute(
                        """
                        INSERT INTO bookmarks(
                            id, position, url, title, category, parent_category,
                            created_at, modified_at, is_pinned, read_later, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(bookmark.id),
                            position,
                            bookmark.url,
                            bookmark.title,
                            bookmark.category,
                            bookmark.parent_category,
                            bookmark.created_at,
                            bookmark.modified_at,
                            int(bookmark.is_pinned),
                            int(bookmark.read_later),
                            encoded,
                        ),
                    )
                persisted_count = conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
                if persisted_count != len(prepared):
                    raise sqlite3.IntegrityError(
                        f"SQLite replacement count mismatch: expected {len(prepared)}, "
                        f"persisted {persisted_count}"
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                    ("saved_at", str(payload_meta.get("saved_at", ""))),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                    ("count", str(payload_meta.get("count", len(data)))),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES('revision', ?)",
                    (str(next_revision),),
                )
                conn.commit()
                self.revision = next_revision
                return next_revision
            except Exception:
                conn.rollback()
                raise

    def load(self) -> List[Bookmark]:
        """Load bookmarks from SQLite, skipping corrupt rows."""
        if not self.filepath.exists():
            return []
        bookmarks: List[Bookmark] = []
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT payload_json FROM bookmarks ORDER BY position ASC, id ASC"
                ).fetchall()
        except sqlite3.Error as exc:
            log.error(f"Could not load SQLite bookmarks from {self.filepath}: {exc}")
            return []

        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
                bookmarks.append(Bookmark.from_dict(payload))
            except Exception as exc:
                log.warning(f"Skipping corrupt SQLite bookmark entry: {exc}")
        self.revision = self.current_revision()
        return bookmarks

    def get_metadata(self) -> Dict[str, str]:
        if not self.filepath.exists():
            return {}
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute("SELECT key, value FROM metadata").fetchall()
            return {row["key"]: row["value"] for row in rows}
        except sqlite3.Error as exc:
            log.warning(f"Could not load SQLite metadata: {exc}")
            return {}


def migrate_json_to_sqlite(json_path: Path, sqlite_path: Path) -> int:
    """Copy bookmarks from the existing JSON storage file into SQLite."""
    from bookmark_organizer_pro.core.storage_manager import StorageManager

    bookmarks = StorageManager(Path(json_path)).load()
    SQLiteStorageManager(Path(sqlite_path)).save([bm.to_dict() for bm in bookmarks])
    return len(bookmarks)
