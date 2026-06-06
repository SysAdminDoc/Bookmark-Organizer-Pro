"""Optional SQLite bookmark storage with WAL mode."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


class SQLiteStorageManager:
    """SQLite persistence backend matching StorageManager's load/save shape."""

    CURRENT_SCHEMA = 1

    def __init__(self, filepath: Path):
        self.filepath = Path(filepath)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.filepath), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY,
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
                CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON bookmarks(url);
                CREATE INDEX IF NOT EXISTS idx_bookmarks_category ON bookmarks(category);
                CREATE INDEX IF NOT EXISTS idx_bookmarks_created_at ON bookmarks(created_at);
                CREATE INDEX IF NOT EXISTS idx_bookmarks_modified_at ON bookmarks(modified_at);
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                ("schema_version", str(self.CURRENT_SCHEMA)),
            )
            conn.commit()

    def save(self, data: List[Dict], metadata: Dict = None) -> None:
        """Replace bookmark rows in a single transaction."""
        payload_meta = metadata or {
            "saved_at": datetime.now().isoformat(),
            "count": len(data),
        }
        with self._lock, closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN")
                conn.execute("DELETE FROM bookmarks")
                for position, item in enumerate(data):
                    if not isinstance(item, dict):
                        log.warning("Skipping non-object bookmark entry during SQLite save")
                        continue
                    bookmark = Bookmark.from_dict(item)
                    payload = bookmark.to_dict()
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO bookmarks(
                            id, position, url, title, category, parent_category,
                            created_at, modified_at, is_pinned, read_later, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            bookmark.id,
                            position,
                            bookmark.url,
                            bookmark.title,
                            bookmark.category,
                            bookmark.parent_category,
                            bookmark.created_at,
                            bookmark.modified_at,
                            int(bookmark.is_pinned),
                            int(bookmark.read_later),
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        ),
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                    ("saved_at", str(payload_meta.get("saved_at", ""))),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                    ("count", str(payload_meta.get("count", len(data)))),
                )
                conn.commit()
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
