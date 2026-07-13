"""Optional SQLite bookmark storage with WAL mode."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import sqlite3
import threading
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from bookmark_organizer_pro.constants import BACKUP_DIR
from bookmark_organizer_pro.core.storage_manager import (
    RECOVERY_DIR,
    StorageConflictError,
    StorageRecoveryRequiredError,
    StorageStatus,
    StorageVersionError,
    _exclusive_file_lock,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


def _canonical_bookmark_digest(bookmarks: List[Bookmark]) -> str:
    """Return a stable digest over the complete, ordered bookmark payload."""
    payload = [bookmark.to_dict() for bookmark in bookmarks]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _migration_identity(bookmarks: List[Bookmark], revision: int) -> tuple:
    """Describe the fields that must survive a backend migration exactly."""
    return (
        len(bookmarks),
        tuple(str(bookmark.id) for bookmark in bookmarks),
        int(revision),
        _canonical_bookmark_digest(bookmarks),
    )


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
        self._lock = threading.RLock()
        self.revision = 0
        self.recovery_copy: Path | None = None
        self.status = StorageStatus(
            "absent" if not self.filepath.exists() else "unread",
            self.filepath,
        )
        try:
            self._init_db()
        except StorageVersionError as exc:
            self.status = StorageStatus("future_version", self.filepath, error=str(exc))
            log.error("Recovery required for %s: %s", self.filepath, exc)
        except Exception as exc:
            self._mark_corrupt(exc)

    def _connect(self) -> sqlite3.Connection:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        # Autocommit mode keeps transaction ownership explicit. In particular,
        # save() can always issue BEGIN before its replacement transaction
        # instead of colliding with an implicit sqlite3 transaction.
        conn = sqlite3.connect(str(self.filepath), timeout=30, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            return conn
        except Exception:
            conn.close()
            raise

    def _init_db(self) -> None:
        existed_before = self.filepath.exists()
        with closing(self._connect()) as conn:
            if existed_before:
                self._validate_integrity(conn)
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
            self.status = StorageStatus("unread", self.filepath)

    @staticmethod
    def _validate_integrity(conn: sqlite3.Connection) -> None:
        result = conn.execute("PRAGMA quick_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            detail = result[0] if result else "no result"
            raise sqlite3.DatabaseError(f"SQLite integrity check failed: {detail}")

    @classmethod
    def _validate_schema(cls, conn: sqlite3.Connection) -> int:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = {"metadata", "bookmarks"} - tables
        if missing:
            raise sqlite3.DatabaseError(
                f"SQLite schema is missing required table(s): {', '.join(sorted(missing))}"
            )
        metadata = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM metadata").fetchall()
        }
        try:
            version = int(metadata.get("schema_version", ""))
            revision = int(metadata.get("revision", "0"))
        except (TypeError, ValueError) as exc:
            raise sqlite3.DatabaseError("SQLite schema metadata is invalid") from exc
        if version > cls.CURRENT_SCHEMA:
            raise StorageVersionError(
                f"SQLite schema {version} is newer than supported schema "
                f"{cls.CURRENT_SCHEMA}; upgrade the application before editing"
            )
        if version != cls.CURRENT_SCHEMA:
            raise sqlite3.DatabaseError(
                f"SQLite schema {version} was not migrated to {cls.CURRENT_SCHEMA}"
            )
        if revision < 0:
            raise sqlite3.DatabaseError("SQLite revision cannot be negative")
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(bookmarks)").fetchall()
        }
        required = {
            "id", "position", "url", "title", "category", "parent_category",
            "created_at", "modified_at", "is_pinned", "read_later", "payload_json",
        }
        if missing_columns := required - columns:
            raise sqlite3.DatabaseError(
                "SQLite bookmarks schema is missing column(s): "
                + ", ".join(sorted(missing_columns))
            )
        return revision

    def _preserve_corrupt_source(self) -> Path | None:
        if self.recovery_copy is not None or not self.filepath.is_file():
            return self.recovery_copy
        RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        preserved = RECOVERY_DIR / (
            f"{self.filepath.stem}_corrupt_{stamp}{self.filepath.suffix}"
        )
        shutil.copy2(self.filepath, preserved)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.filepath}{suffix}")
            if sidecar.is_file():
                shutil.copy2(sidecar, Path(f"{preserved}{suffix}"))
        self.recovery_copy = preserved
        return preserved

    def _close_wal_for_replacement(self) -> None:
        """Checkpoint a readable database and release WAL files before replacement."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.filepath), timeout=1, isolation_level=None)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.Error:
            pass
        finally:
            if conn is not None:
                conn.close()
        for suffix in ("-wal", "-shm"):
            Path(f"{self.filepath}{suffix}").unlink(missing_ok=True)

    def _mark_corrupt(self, error: Exception | str) -> None:
        detail = str(error)
        try:
            preserved = self._preserve_corrupt_source()
            if preserved:
                detail = f"{detail}; damaged source preserved at {preserved}"
        except Exception as preserve_error:
            detail = f"{detail}; source preservation failed: {preserve_error}"
        self.status = StorageStatus("corrupt", self.filepath, error=detail)
        log.error("Recovery required for %s: %s", self.filepath, detail)

    def assert_writable(self) -> None:
        if self.status.recovery_required:
            error_type = (
                StorageVersionError
                if self.status.state == "future_version"
                else StorageRecoveryRequiredError
            )
            raise error_type(
                f"Cannot save {self.filepath}: {self.status.error}. "
                "Restore a verified backup or explicitly salvage complete rows first."
            )

    @property
    def recovery_required(self) -> bool:
        return self.status.recovery_required

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

    @staticmethod
    def _decode_rows(rows) -> List[Bookmark]:
        bookmarks: List[Bookmark] = []
        seen_ids = set()
        seen_positions = set()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
                if not isinstance(payload, dict):
                    raise ValueError("payload is not an object")
                bookmark = Bookmark.from_dict(payload)
                bookmark_id = str(bookmark.id)
                position = int(row["position"])
                if bookmark_id in seen_ids:
                    raise ValueError(f"duplicate bookmark id {bookmark_id}")
                if position in seen_positions:
                    raise ValueError(f"duplicate bookmark position {position}")
            except Exception as exc:
                row_id = row["id"] if "id" in row.keys() else "?"
                raise sqlite3.DatabaseError(
                    f"Invalid SQLite bookmark row {row_id}: {exc}"
                ) from exc
            seen_ids.add(bookmark_id)
            seen_positions.add(position)
            bookmarks.append(bookmark)
        return bookmarks

    @classmethod
    def _validate_database_file(cls, path: Path) -> List[Bookmark]:
        uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            cls._validate_integrity(conn)
            cls._validate_schema(conn)
            rows = conn.execute(
                "SELECT id, position, url, title, payload_json "
                "FROM bookmarks ORDER BY position ASC, id ASC"
            ).fetchall()
            bookmarks = cls._decode_rows(rows)
            metadata_count = conn.execute(
                "SELECT value FROM metadata WHERE key = 'count'"
            ).fetchone()
            if metadata_count is not None and int(metadata_count[0]) != len(bookmarks):
                raise sqlite3.DatabaseError(
                    f"SQLite metadata count {metadata_count[0]} does not match "
                    f"{len(bookmarks)} bookmark row(s)"
                )
            return bookmarks

    def _backup_database(self, label: str = "backup") -> str:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destination = BACKUP_DIR / (
            f"{self.filepath.stem}_{label}_{stamp}{self.filepath.suffix}"
        )
        with closing(self._connect()) as source, closing(
            sqlite3.connect(str(destination))
        ) as target:
            source.backup(target)
        self._validate_database_file(destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        destination.with_suffix(".sha256").write_text(
            f"{digest}  {destination.name}\n", encoding="utf-8"
        )
        backups = sorted(
            BACKUP_DIR.glob(f"{self.filepath.stem}_backup_*{self.filepath.suffix}"),
            key=lambda item: item.stat().st_mtime,
        )
        for old in backups[:-10]:
            old.unlink(missing_ok=True)
            old.with_suffix(".sha256").unlink(missing_ok=True)
        return str(destination.relative_to(BACKUP_DIR)).replace("\\", "/")

    def create_safepoint(self, label: str = "manual") -> str | None:
        """Create a verified SQLite snapshot usable by restore_backup()."""
        with self._lock:
            self.assert_writable()
            if not self.filepath.is_file():
                return None
            safe_label = "".join(
                char if char.isalnum() or char in "-_" else "_" for char in label
            ).strip("_") or "manual"
            return self._backup_database(f"safepoint_{safe_label}")

    def current_revision(self) -> int:
        """Return the revision visible to a new database connection."""
        self.assert_writable()
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
        self.assert_writable()
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
                existing_count = conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
                if existing_count:
                    self._backup_database()
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
                self.status = StorageStatus(
                    "valid_empty" if not prepared else "valid",
                    self.filepath,
                    count=len(prepared),
                )
                return next_revision
            except Exception:
                conn.rollback()
                raise

    def load(self) -> List[Bookmark]:
        """Load SQLite bookmarks or enter write-locked recovery mode."""
        if self.status.recovery_required:
            return []
        if not self.filepath.exists():
            self.status = StorageStatus("absent", self.filepath)
            return []
        try:
            with closing(self._connect()) as conn:
                self._validate_integrity(conn)
                self.revision = self._validate_schema(conn)
                rows = conn.execute(
                    "SELECT id, position, url, title, payload_json "
                    "FROM bookmarks ORDER BY position ASC, id ASC"
                ).fetchall()
                bookmarks = self._decode_rows(rows)
                metadata_count = conn.execute(
                    "SELECT value FROM metadata WHERE key = 'count'"
                ).fetchone()
                if metadata_count is not None and int(metadata_count[0]) != len(bookmarks):
                    raise sqlite3.DatabaseError(
                        f"SQLite metadata count {metadata_count[0]} does not match "
                        f"{len(bookmarks)} bookmark row(s)"
                    )
            self.status = StorageStatus(
                "valid_empty" if not bookmarks else "valid",
                self.filepath,
                count=len(bookmarks),
            )
            return bookmarks
        except StorageVersionError as exc:
            self.status = StorageStatus("future_version", self.filepath, error=str(exc))
            log.error("Recovery required for %s: %s", self.filepath, exc)
            return []
        except Exception as exc:
            self._mark_corrupt(exc)
            return []

    def get_metadata(self) -> Dict[str, str]:
        if self.status.recovery_required:
            return {}
        if not self.filepath.exists():
            return {}
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute("SELECT key, value FROM metadata").fetchall()
            return {row["key"]: row["value"] for row in rows}
        except sqlite3.Error as exc:
            self._mark_corrupt(exc)
            return {}

    def salvage(self) -> List[Bookmark]:
        """Read only complete, internally consistent rows from a damaged database."""
        if not self.status.recovery_required:
            raise StorageRecoveryRequiredError(
                "Salvage is only available while SQLite recovery is required"
            )
        try:
            uri = f"file:{self.filepath.resolve().as_posix()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, position, url, title, payload_json "
                    "FROM bookmarks ORDER BY position ASC, id ASC"
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageRecoveryRequiredError(
                f"SQLite rows could not be read for salvage: {exc}"
            ) from exc

        recovered: List[Bookmark] = []
        seen_ids = set()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
                bookmark = Bookmark.from_dict(payload)
                bookmark_id = str(bookmark.id)
                if bookmark_id in seen_ids:
                    continue
            except Exception:
                continue
            seen_ids.add(bookmark_id)
            recovered.append(bookmark)
        return recovered

    def commit_salvage(self, bookmarks: List[Bookmark]) -> str:
        """Replace a damaged database with explicitly accepted recovered rows."""
        if not self.status.recovery_required:
            raise StorageRecoveryRequiredError(
                "Salvage is only available while SQLite recovery is required"
            )
        if not bookmarks:
            raise StorageRecoveryRequiredError(
                "No complete SQLite rows could be recovered; restore a backup instead"
            )
        preserved = self._preserve_corrupt_source()
        if preserved is None:
            raise StorageRecoveryRequiredError("The damaged SQLite source was not preserved")

        temporary = self.filepath.with_name(
            f".{self.filepath.name}.salvage-{os.getpid()}-{threading.get_ident()}"
        )
        for candidate in (temporary, Path(f"{temporary}-wal"), Path(f"{temporary}-shm")):
            candidate.unlink(missing_ok=True)
        replacement = SQLiteStorageManager(temporary)
        try:
            replacement.save([bookmark.to_dict() for bookmark in bookmarks])
            self._validate_database_file(temporary)
            self._close_wal_for_replacement()
            os.replace(temporary, self.filepath)
            self.recovery_copy = None
            self.status = StorageStatus("unread", self.filepath)
            self._init_db()
            loaded = self.load()
            if len(loaded) != len(bookmarks):
                raise StorageRecoveryRequiredError(
                    "Recovered SQLite row count changed during verification"
                )
        except Exception:
            self._mark_corrupt("SQLite salvage replacement could not be verified")
            raise
        finally:
            for candidate in (temporary, Path(f"{temporary}-wal"), Path(f"{temporary}-shm")):
                candidate.unlink(missing_ok=True)
        return str(preserved)

    def get_backups(self) -> List[Tuple[str, datetime, int]]:
        """List verified SQLite backups and safepoints, newest first."""
        candidates = list(BACKUP_DIR.glob(f"{self.filepath.stem}_*{self.filepath.suffix}"))
        backups: List[Tuple[str, datetime, int]] = []
        for candidate in candidates:
            try:
                stat = candidate.stat()
                relative = str(candidate.relative_to(BACKUP_DIR)).replace("\\", "/")
                backups.append((relative, datetime.fromtimestamp(stat.st_mtime), stat.st_size))
            except OSError as exc:
                log.warning("Could not inspect SQLite backup %s: %s", candidate, exc)
        return sorted(backups, key=lambda item: item[1], reverse=True)

    def restore_backup(self, backup_name: str) -> bool:
        """Restore a hash-verified, fully readable SQLite backup."""
        backup_root = BACKUP_DIR.resolve()
        backup_path = (backup_root / backup_name).resolve()
        try:
            backup_path.relative_to(backup_root)
        except ValueError:
            log.error("Invalid SQLite backup name: %s", backup_name)
            return False
        if not backup_path.is_file() or backup_path.suffix != self.filepath.suffix:
            return False
        hash_path = backup_path.with_suffix(".sha256")
        if not hash_path.is_file():
            log.error("SQLite backup has no integrity hash: %s", backup_name)
            return False
        try:
            expected = hash_path.read_text(encoding="utf-8").split()[0]
            actual = hashlib.sha256(backup_path.read_bytes()).hexdigest()
            if expected != actual:
                raise ValueError("SHA-256 mismatch")
            restored = self._validate_database_file(backup_path)
        except Exception as exc:
            log.error("SQLite backup validation failed for %s: %s", backup_name, exc)
            return False

        temporary = self.filepath.with_name(f".{self.filepath.name}.restore-{os.getpid()}")
        try:
            if self.filepath.is_file():
                if self.status.recovery_required:
                    self._preserve_corrupt_source()
                else:
                    self._backup_database("pre_restore")
            shutil.copy2(backup_path, temporary)
            self._validate_database_file(temporary)
            self._close_wal_for_replacement()
            os.replace(temporary, self.filepath)
            self.recovery_copy = None
            self.status = StorageStatus("unread", self.filepath)
            self._init_db()
            loaded = self.load()
            return len(loaded) == len(restored) and not self.status.recovery_required
        except Exception as exc:
            log.error("SQLite backup restore failed for %s: %s", backup_name, exc)
            self._mark_corrupt(exc)
            return False
        finally:
            temporary.unlink(missing_ok=True)


def migrate_json_to_sqlite(json_path: Path, sqlite_path: Path) -> int:
    """Stage and verify a JSON library before atomically activating SQLite.

    The JSON library remains untouched and authoritative throughout.  A
    verified JSON safepoint is required before any destination is staged, and
    the destination is only made visible after count, ordered IDs, revision,
    and canonical bookmark content all match.
    """
    from bookmark_organizer_pro.core.storage_manager import StorageManager

    source_path = Path(json_path)
    destination_path = Path(sqlite_path)
    if source_path.resolve() == destination_path.resolve():
        raise ValueError("JSON source and SQLite destination must be different files")
    destination_files = (
        destination_path,
        Path(f"{destination_path}-wal"),
        Path(f"{destination_path}-shm"),
    )
    if any(path.exists() for path in destination_files):
        raise FileExistsError(
            f"SQLite destination or a sidecar already exists: {destination_path}. "
            "Move or remove it before starting a verified migration."
        )

    source = StorageManager(source_path)
    bookmarks = source.load()
    if source.status.recovery_required:
        raise StorageRecoveryRequiredError(
            f"Cannot migrate {source_path}: {source.status.error}. "
            "Restore or salvage the JSON library before migrating."
        )
    if source.status.state not in {"valid", "valid_empty"}:
        raise StorageRecoveryRequiredError(
            f"Cannot migrate {source_path}: a valid JSON library is required"
        )

    source_identity = _migration_identity(bookmarks, source.revision)
    safepoint_name = source.create_safepoint("pre-sqlite-migration")
    if not safepoint_name:
        raise StorageRecoveryRequiredError(
            f"Could not create a pre-migration safepoint for {source_path}"
        )
    safepoint_path = (BACKUP_DIR / safepoint_name).resolve()
    safepoint_hash = safepoint_path.with_suffix(".sha256")
    if not safepoint_path.is_file() or not safepoint_hash.is_file():
        raise StorageRecoveryRequiredError(
            f"Pre-migration safepoint could not be verified: {safepoint_path}"
        )
    expected_hash = safepoint_hash.read_text(encoding="utf-8").split()[0]
    if hashlib.sha256(safepoint_path.read_bytes()).hexdigest() != expected_hash:
        raise StorageRecoveryRequiredError(
            f"Pre-migration safepoint hash mismatch: {safepoint_path}"
        )
    safepoint = StorageManager(safepoint_path)
    safepoint_bookmarks = safepoint.load()
    if (
        safepoint.status.recovery_required
        or _migration_identity(safepoint_bookmarks, safepoint.revision) != source_identity
    ):
        raise StorageRecoveryRequiredError(
            f"Pre-migration safepoint does not match the JSON source: {safepoint_path}"
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination_path.with_name(
        f".{destination_path.name}.migration-{os.getpid()}-{threading.get_ident()}.tmp"
    )
    temporary_files = (temporary, Path(f"{temporary}-wal"), Path(f"{temporary}-shm"))
    for candidate in temporary_files:
        candidate.unlink(missing_ok=True)

    try:
        staged = SQLiteStorageManager(temporary)
        staged.save([bookmark.to_dict() for bookmark in bookmarks])
        with closing(staged._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('revision', ?)",
                (str(source.revision),),
            )
            conn.commit()
        staged.revision = source.revision
        staged._close_wal_for_replacement()

        migrated = staged._validate_database_file(temporary)
        uri = f"file:{temporary.resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            destination_revision = staged._validate_schema(conn)
        destination_identity = _migration_identity(migrated, destination_revision)
        if destination_identity != source_identity:
            raise StorageRecoveryRequiredError(
                "SQLite migration verification failed: source and destination "
                "count, IDs, revision, or canonical digest differ"
            )

        # Keep the cross-process JSON writer lock through the final source
        # comparison and activation, closing the last race between verification
        # and os.replace().  The first load upgraded any supported legacy schema,
        # so a different version here is necessarily a concurrent replacement.
        with _exclusive_file_lock(source_path):
            with open(source_path, "r", encoding="utf-8") as handle:
                current_raw = json.load(handle)
            if not isinstance(current_raw, dict):
                raise StorageConflictError(
                    "JSON source changed during SQLite migration; no destination was activated"
                )
            current_version = current_raw.get("version", 1)
            current_revision = current_raw.get("revision", 0)
            if (
                current_version != StorageManager.CURRENT_VERSION
                or not isinstance(current_revision, int)
                or current_revision < 0
            ):
                raise StorageConflictError(
                    "JSON source changed during SQLite migration; no destination was activated"
                )
            current_bookmarks = source._decode_bookmarks(current_raw)
            if _migration_identity(current_bookmarks, current_revision) != source_identity:
                raise StorageConflictError(
                    "JSON source changed during SQLite migration; no destination was activated"
                )
            os.replace(temporary, destination_path)
        return len(bookmarks)
    finally:
        for candidate in temporary_files:
            candidate.unlink(missing_ok=True)
