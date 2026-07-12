"""Persistent JSON storage with atomic writes, backups, and corruption recovery."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..constants import BACKUP_DIR
from ..logging_config import log
from ..models import Bookmark

# Preserved "safepoint" snapshots (startup, pre-import, manual) live in a
# subdirectory so the rolling per-save backup rotation never deletes them.
SAFEPOINT_DIR = BACKUP_DIR / "safepoints"
MAX_SAFEPOINTS = 30
RECOVERY_DIR = BACKUP_DIR / "recovery"


class StorageRecoveryRequiredError(RuntimeError):
    """Raised when a damaged library must be recovered before it can be saved."""


class StorageConflictError(RuntimeError):
    """Raised when a writer attempts to replace a newer library revision."""


class StorageVersionError(StorageRecoveryRequiredError):
    """Raised when a library was written by a newer, unsupported schema."""


@contextmanager
def _exclusive_file_lock(path: Path):
    """Hold a small sidecar file lock across revision check and replacement."""
    lock_path = Path(f"{path}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - exercised on Linux/macOS packages
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class StorageStatus:
    """Current JSON library state, including an actionable parse failure."""

    state: str
    path: Path
    count: int = 0
    error: str = ""

    @property
    def recovery_required(self) -> bool:
        return self.state in {"corrupt", "future_version"}


class StorageManager:
    """Atomic JSON persistence with timestamped backups.

    - save() writes to a temp file then atomically replaces the target
    - Each save creates a timestamped backup; only the 10 most recent are kept
    - Safepoints (create_safepoint) are preserved separately for disaster recovery
    - load() tolerates individual corrupt entries (logs warning, skips)
    """

    CURRENT_VERSION = 4

    def __init__(self, filepath: Path):
        self.filepath = Path(filepath)
        self._lock = threading.RLock()
        self.revision = 0
        self.status = StorageStatus(
            "absent" if not self.filepath.exists() else "unread",
            self.filepath,
        )

    def _require_writable(self) -> None:
        if self.status.recovery_required:
            error_type = (
                StorageVersionError
                if self.status.state == "future_version"
                else StorageRecoveryRequiredError
            )
            raise error_type(
                f"Cannot save {self.filepath}: {self.status.error}. "
                "Restore a verified backup or explicitly salvage the damaged file first."
            )

    def assert_writable(self) -> None:
        """Fail before callers mutate in-memory state during recovery mode."""
        self._require_writable()

    def _read_header(self) -> Tuple[int, int]:
        """Return persisted (schema version, revision) without decoding records."""
        if not self.filepath.exists():
            return self.CURRENT_VERSION, 0
        with open(self.filepath, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, list):
            return 0, 0
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON value must be an object or array")
        version = raw.get("version", 1)
        revision = raw.get("revision", 0)
        if not isinstance(version, int) or version < 0:
            raise ValueError("storage version must be a non-negative integer")
        if not isinstance(revision, int) or revision < 0:
            raise ValueError("storage revision must be a non-negative integer")
        return version, revision

    def current_revision(self) -> int:
        """Read the revision currently persisted by another process."""
        try:
            version, revision = self._read_header()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise StorageRecoveryRequiredError(
                f"Cannot read the current revision for {self.filepath}: {exc}"
            ) from exc
        if version > self.CURRENT_VERSION:
            raise StorageVersionError(
                f"Library schema {version} is newer than supported schema "
                f"{self.CURRENT_VERSION}; upgrade the application before editing"
            )
        return revision

    def save(
        self,
        data: List[Dict],
        metadata: Dict = None,
        expected_revision: Optional[int] = None,
    ) -> int:
        """Save data atomically, rejecting replacement of a newer revision."""
        self._require_writable()
        with self._lock, _exclusive_file_lock(self.filepath):
            version, persisted_revision = self._read_header()
            if version > self.CURRENT_VERSION:
                raise StorageVersionError(
                    f"Library schema {version} is newer than supported schema "
                    f"{self.CURRENT_VERSION}; upgrade the application before editing"
                )
            if expected_revision is not None and expected_revision != persisted_revision:
                raise StorageConflictError(
                    f"Stale library revision {expected_revision}; current revision is "
                    f"{persisted_revision}. Reload and retry the change."
                )
            next_revision = persisted_revision + 1
            payload = {
                "version": self.CURRENT_VERSION,
                "revision": next_revision,
                "metadata": metadata or {
                    "saved_at": datetime.now().isoformat(),
                    "count": len(data),
                },
                "data": data,
            }
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            if self.filepath.exists():
                self._create_backup()
            fd, temp_path = tempfile.mkstemp(
                dir=self.filepath.resolve().parent, suffix='.tmp', text=True
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, self.filepath)
                self.revision = next_revision
                self.status = StorageStatus(
                    "valid_empty" if not data else "valid",
                    self.filepath,
                    count=len(data),
                )
                return next_revision
            except Exception:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise

    def _create_backup(self):
        """Create a timestamped backup; rotate to keep only 10."""
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{self.filepath.stem}_{timestamp}.json"
            backup_path = BACKUP_DIR / backup_name
            counter = 1
            while backup_path.exists():
                backup_path = BACKUP_DIR / f"{self.filepath.stem}_{timestamp}_{counter}.json"
                counter += 1
            shutil.copy2(self.filepath, backup_path)

            try:
                digest = hashlib.sha256(backup_path.read_bytes()).hexdigest()
                backup_path.with_suffix(".sha256").write_text(
                    f"{digest}  {backup_path.name}\n", encoding="utf-8",
                )
            except OSError as he:
                log.warning(f"Could not write backup hash: {he}")

            backups = sorted(BACKUP_DIR.glob(f"{self.filepath.stem}_*.json"))
            while len(backups) > 10:
                old = backups.pop(0)
                try:
                    old.unlink()
                except OSError:
                    continue
                # Also clean up orphaned .sha256 hash file
                sha_file = old.with_suffix(".sha256")
                try:
                    if sha_file.exists():
                        sha_file.unlink()
                except OSError:
                    pass
        except Exception as e:
            log.warning(f"Backup creation failed: {e}")

    def create_safepoint(self, label: str = "manual") -> Optional[str]:
        """Create a preserved snapshot for disaster recovery.

        Unlike the rolling per-save backups (which rotate out after 10 saves),
        safepoints are kept in a separate directory and retained for the last
        MAX_SAFEPOINTS milestones — so a known-good state captured at startup or
        before an import survives a whole session of edits. Returns the
        safepoint name (relative to BACKUP_DIR, usable with restore_backup), or
        None if nothing was captured.
        """
        try:
            if not self.filepath.exists():
                return None
            SAFEPOINT_DIR.mkdir(parents=True, exist_ok=True)
            safe_label = re.sub(r"[^a-z0-9_-]+", "-", str(label).lower()).strip("-") or "manual"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{self.filepath.stem}_safepoint_{safe_label}_{ts}"
            dest = SAFEPOINT_DIR / f"{base}.json"
            counter = 1
            while dest.exists():
                dest = SAFEPOINT_DIR / f"{base}_{counter}.json"
                counter += 1
            with self._lock:
                shutil.copy2(self.filepath, dest)
            try:
                digest = hashlib.sha256(dest.read_bytes()).hexdigest()
                dest.with_suffix(".sha256").write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
            except OSError as he:
                log.warning(f"Could not write safepoint hash: {he}")

            safepoints = sorted(
                SAFEPOINT_DIR.glob(f"{self.filepath.stem}_safepoint_*.json"),
                key=lambda p: p.stat().st_mtime,
            )
            while len(safepoints) > MAX_SAFEPOINTS:
                old = safepoints.pop(0)
                try:
                    old.unlink()
                except OSError:
                    continue
                sha_file = old.with_suffix(".sha256")
                try:
                    if sha_file.exists():
                        sha_file.unlink()
                except OSError:
                    pass
            log.info(f"Safepoint created ({safe_label}): {dest.name}")
            return f"safepoints/{dest.name}"
        except Exception as e:
            log.warning(f"Safepoint creation failed: {e}")
            return None

    @staticmethod
    def _migrate_v0_to_v1(raw):
        if not isinstance(raw, list):
            raise ValueError("legacy schema 0 must be a bookmark array")
        return {"version": 1, "metadata": {"count": len(raw)}, "data": raw}

    @staticmethod
    def _migrate_v1_to_v2(raw):
        migrated = dict(raw)
        data = migrated.get("data")
        if not isinstance(data, list):
            raise ValueError("schema 1 bookmark data must be an array")
        metadata = migrated.get("metadata")
        migrated["metadata"] = dict(metadata) if isinstance(metadata, dict) else {}
        migrated["metadata"].setdefault("count", len(data))
        migrated["version"] = 2
        return migrated

    @staticmethod
    def _migrate_v2_to_v3(raw):
        migrated = dict(raw)
        if not isinstance(migrated.get("data"), list):
            raise ValueError("schema 2 bookmark data must be an array")
        migrated["version"] = 3
        return migrated

    @staticmethod
    def _migrate_v3_to_v4(raw):
        migrated = dict(raw)
        if not isinstance(migrated.get("data"), list):
            raise ValueError("schema 3 bookmark data must be an array")
        migrated.setdefault("revision", 0)
        migrated["version"] = 4
        return migrated

    MIGRATIONS = {
        0: "_migrate_v0_to_v1",
        1: "_migrate_v1_to_v2",
        2: "_migrate_v2_to_v3",
        3: "_migrate_v3_to_v4",
    }

    def _upgrade_payload(self, raw):
        """Apply every ordered schema transition and preserve a verified source."""
        if isinstance(raw, list):
            version = 0
        elif isinstance(raw, dict):
            version = raw.get("version", 1)
        else:
            raise ValueError("top-level JSON value must be an object or array")
        if not isinstance(version, int) or version < 0:
            raise ValueError("storage version must be a non-negative integer")
        if version > self.CURRENT_VERSION:
            raise StorageVersionError(
                f"Library schema {version} is newer than supported schema "
                f"{self.CURRENT_VERSION}; upgrade the application before editing"
            )
        if version == self.CURRENT_VERSION:
            return raw, False

        safepoint = self.create_safepoint(
            f"pre-migration-v{version}-to-v{self.CURRENT_VERSION}"
        )
        if not safepoint:
            raise StorageRecoveryRequiredError(
                f"Could not create a pre-migration safepoint for {self.filepath}"
            )
        migrated = raw
        while version < self.CURRENT_VERSION:
            transition_name = self.MIGRATIONS.get(version)
            if transition_name is None:
                raise StorageVersionError(
                    f"No migration is registered from JSON schema {version}"
                )
            migrated = getattr(self, transition_name)(migrated)
            version += 1
            if migrated.get("version") != version:
                raise RuntimeError(f"JSON migration to schema {version} did not advance")
        return migrated, True

    def _write_payload_atomic(self, payload: Dict) -> None:
        fd, temp_path = tempfile.mkstemp(
            dir=self.filepath.resolve().parent, suffix=".migration.tmp", text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            with open(temp_path, "r", encoding="utf-8") as handle:
                verified = json.load(handle)
            if verified.get("version") != self.CURRENT_VERSION:
                raise ValueError("migrated library verification failed")
            os.replace(temp_path, self.filepath)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def _decode_bookmarks(self, raw) -> List[Bookmark]:
        """Validate a complete JSON document without accepting partial data loss."""
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            if "data" not in raw:
                raise ValueError("bookmark library object is missing the data array")
            items = raw["data"]
        else:
            raise ValueError("top-level JSON value must be an object or array")
        if not isinstance(items, list):
            raise ValueError("bookmark data must be an array")

        bookmarks = []
        for position, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"bookmark at index {position} is not an object")
            try:
                bookmarks.append(Bookmark.from_dict(item))
            except Exception as exc:
                raise ValueError(f"bookmark at index {position} is invalid: {exc}") from exc
        return bookmarks

    def _mark_corrupt(self, error: Exception | str) -> None:
        detail = str(error)
        self.status = StorageStatus("corrupt", self.filepath, error=detail)
        log.error(f"Recovery required for {self.filepath}: {detail}")

    def load(self) -> List[Bookmark]:
        """Load bookmarks or enter fail-closed recovery mode on corruption."""
        with self._lock:
            if not self.filepath.exists():
                self.status = StorageStatus("absent", self.filepath)
                return []

            try:
                with _exclusive_file_lock(self.filepath):
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    raw, migrated = self._upgrade_payload(raw)
                    if migrated:
                        self._write_payload_atomic(raw)
                bookmarks = self._decode_bookmarks(raw)
                self.revision = raw.get("revision", 0) if isinstance(raw, dict) else 0
                self.status = StorageStatus(
                    "valid_empty" if not bookmarks else "valid",
                    self.filepath,
                    count=len(bookmarks),
                )
                return bookmarks
            except json.JSONDecodeError as e:
                self._mark_corrupt(
                    f"invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"
                )
                return []
            except StorageVersionError as e:
                self.status = StorageStatus("future_version", self.filepath, error=str(e))
                log.error(f"Recovery required for {self.filepath}: {e}")
                return []
            except Exception as e:
                self._mark_corrupt(e)
                return []

    def salvage(self) -> List[Bookmark]:
        """Extract complete bookmark objects from damaged JSON without writing it."""
        if not self.status.recovery_required:
            raise StorageRecoveryRequiredError("Salvage is only available in recovery mode")
        text = self.filepath.read_text(encoding="utf-8", errors="replace")
        decoder = json.JSONDecoder()
        recovered: Dict[Tuple[Optional[int], str], Bookmark] = {}
        cursor = 0
        while True:
            start = text.find("{", cursor)
            if start < 0:
                break
            cursor = start + 1
            try:
                candidate, end = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            cursor = start + max(end, 1)
            if not isinstance(candidate, dict) or "url" not in candidate:
                continue
            if not any(key in candidate for key in ("id", "title", "category", "tags", "created_at")):
                continue
            try:
                bookmark = Bookmark.from_dict(candidate)
            except Exception:
                continue
            recovered[(bookmark.id, bookmark.url)] = bookmark
        return list(recovered.values())

    def commit_salvage(self, bookmarks: List[Bookmark]) -> str:
        """Preserve the damaged source, then replace it with explicit salvage results."""
        if not self.status.recovery_required:
            raise StorageRecoveryRequiredError("Salvage is only available in recovery mode")
        if not bookmarks:
            raise StorageRecoveryRequiredError(
                "No complete bookmark records could be recovered; restore a backup instead"
            )
        RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        preserved = RECOVERY_DIR / f"{self.filepath.stem}_corrupt_{timestamp}{self.filepath.suffix}"
        shutil.copy2(self.filepath, preserved)
        previous_status = self.status
        self.status = StorageStatus("absent", self.filepath)
        try:
            self.filepath.unlink()
            self.save([bookmark.to_dict() for bookmark in bookmarks])
        except Exception:
            if not self.filepath.exists():
                shutil.copy2(preserved, self.filepath)
            self.status = previous_status
            raise
        return str(preserved)

    def get_backups(self) -> List[Tuple[str, datetime, int]]:
        """List available backups + safepoints, newest first.

        Each entry is (name, mtime, size); ``name`` is relative to BACKUP_DIR
        (e.g. ``safepoints/...json`` for safepoints) and can be passed straight
        to restore_backup.
        """
        backups = []
        candidates = list(BACKUP_DIR.glob(f"{self.filepath.stem}_*.json"))
        candidates += list(SAFEPOINT_DIR.glob(f"{self.filepath.stem}_safepoint_*.json"))
        for f in candidates:
            try:
                stat = f.stat()
                rel = str(f.relative_to(BACKUP_DIR)).replace("\\", "/")
                backups.append((
                    rel,
                    datetime.fromtimestamp(stat.st_mtime),
                    stat.st_size,
                ))
            except Exception as e:
                log.warning(f"Error reading backup {f.name}: {e}")
        return sorted(backups, key=lambda x: x[1], reverse=True)

    def restore_backup(self, backup_name: str) -> bool:
        """Restore from a named backup file."""
        backup_root = BACKUP_DIR.resolve()
        backup_path = (backup_root / backup_name).resolve()
        try:
            backup_path.relative_to(backup_root)
        except ValueError:
            log.error(f"Invalid backup name (path traversal blocked): {backup_name}")
            return False
        if not backup_path.is_file():
            log.error(f"Backup not found: {backup_name}")
            return False
        try:
            with open(backup_path, "r", encoding="utf-8") as backup_file:
                restored = self._decode_bookmarks(json.load(backup_file))
        except Exception as exc:
            log.error(f"Backup validation failed for {backup_name}: {exc}")
            return False
        hash_path = backup_path.with_suffix(".sha256")
        if hash_path.is_file():
            try:
                expected = hash_path.read_text(encoding="utf-8").split()[0].strip()
                actual = hashlib.sha256(backup_path.read_bytes()).hexdigest()
                if expected != actual:
                    log.error(f"Backup integrity check failed for {backup_name}")
                    return False
                log.info(f"Backup integrity verified: {backup_name}")
            except Exception as ve:
                log.warning(f"Could not verify backup hash: {ve}")
        try:
            with self._lock:
                self.filepath.parent.mkdir(parents=True, exist_ok=True)
                if self.filepath.is_file():
                    pre_restore = BACKUP_DIR / f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    shutil.copy2(self.filepath, pre_restore)
                    log.info(f"Pre-restore backup saved: {pre_restore.name}")
                shutil.copy2(backup_path, self.filepath)
                self.status = StorageStatus(
                    "valid_empty" if not restored else "valid",
                    self.filepath,
                    count=len(restored),
                )
            return True
        except Exception as e:
            log.error(f"Failed to restore backup {backup_name}: {e}")
            return False
