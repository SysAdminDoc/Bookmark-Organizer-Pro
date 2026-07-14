"""Recoverable, versioned JSON documents for local service sidecars."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.private_files import (
    atomic_copy_private_file,
    restrict_private_file,
)


class AtomicDocumentError(RuntimeError):
    """Base error for recoverable document persistence."""


class AtomicDocumentRecoveryError(AtomicDocumentError):
    """Raised when a damaged document must be recovered before mutation."""


class AtomicDocumentConflictError(AtomicDocumentError):
    """Raised when an optimistic writer is based on an older revision."""


class AtomicDocumentVersionError(AtomicDocumentRecoveryError):
    """Raised when a document uses a newer unsupported schema version."""


@dataclass(frozen=True)
class AtomicDocumentStatus:
    """Inspectable integrity and recovery state for one document."""

    state: str
    path: Path
    revision: int = 0
    error: str = ""
    quarantine_path: Path | None = None
    backup_path: Path | None = None

    @property
    def recovery_required(self) -> bool:
        return self.state in {"corrupt", "future_version"}


@contextmanager
def exclusive_document_lock(path: Path):
    """Serialize a complete read-modify-write cycle across local processes."""
    lock_path = Path(f"{path}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
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
        else:  # pragma: no cover - exercised by macOS/Linux packages
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _canonical_bytes(document: Any) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _checksum(document: Any) -> str:
    return hashlib.sha256(_canonical_bytes(document)).hexdigest()


def require_list_document(document: Any) -> None:
    """Validate a list-backed sidecar document."""
    if not isinstance(document, list):
        raise ValueError("sidecar document must be an array")


def require_mapping_document(document: Any) -> None:
    """Validate an object-backed sidecar document."""
    if not isinstance(document, dict):
        raise ValueError("sidecar document must be an object")


class AtomicDocumentStore:
    """Atomic JSON document with migrations, checksums, backup, and recovery.

    Legacy unwrapped JSON is schema version 0. Each registered migration must
    advance exactly one version; the current representation is always stored in
    a self-describing envelope. ``update`` holds the process and file locks over
    the complete read-modify-write cycle so concurrent writers cannot silently
    replace each other's changes.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        schema: str,
        current_version: int = 1,
        default_factory: Callable[[], Any] = dict,
        migrations: Mapping[int, Callable[[Any], Any]] | None = None,
        validator: Callable[[Any], None] | None = None,
        sensitive: bool = False,
    ):
        if not schema or current_version < 1:
            raise ValueError("schema is required and current_version must be positive")
        self.path = Path(path)
        self.schema = str(schema)
        self.current_version = int(current_version)
        self.default_factory = default_factory
        self.migrations = dict(migrations or {0: lambda value: value})
        self.validator = validator or (lambda _value: None)
        self.sensitive = bool(sensitive)
        self._thread_lock = threading.RLock()
        self.revision = 0
        self.status = AtomicDocumentStatus(
            "absent" if not self.path.exists() else "unread",
            self.path,
        )

    @property
    def backup_path(self) -> Path:
        return Path(f"{self.path}.bak")

    @property
    def recovery_dir(self) -> Path:
        return self.path.parent / "recovery"

    def load(self) -> Any:
        """Load and migrate the document, recovering a verified backup if possible."""
        with self._thread_lock, exclusive_document_lock(self.path):
            return copy.deepcopy(self._load_locked())

    def save(self, document: Any, *, expected_revision: int | None = None) -> int:
        """Replace the document atomically, optionally rejecting a stale writer."""
        with self._thread_lock, exclusive_document_lock(self.path):
            if self.path.exists():
                current = self._load_locked()
                if self.status.recovery_required:
                    raise AtomicDocumentRecoveryError(self.status.error)
                del current
                persisted_revision = self.revision
            else:
                persisted_revision = 0
            if expected_revision is not None and expected_revision != persisted_revision:
                raise AtomicDocumentConflictError(
                    f"Stale {self.schema} revision {expected_revision}; current revision is "
                    f"{persisted_revision}. Reload and retry."
                )
            self.validator(document)
            revision = persisted_revision + 1
            self._write_locked(document, revision, preserve_current=self.path.exists())
            return revision

    def update(self, mutator: Callable[[Any], Any | None]) -> Any:
        """Apply a mutation to the latest revision under one cross-process lock."""
        with self._thread_lock, exclusive_document_lock(self.path):
            document = self._load_locked() if self.path.exists() else self.default_factory()
            if self.status.recovery_required:
                raise AtomicDocumentRecoveryError(self.status.error)
            working = copy.deepcopy(document)
            replacement = mutator(working)
            if replacement is not None:
                working = replacement
            self.validator(working)
            self._write_locked(
                working,
                self.revision + 1,
                preserve_current=self.path.exists(),
            )
            return copy.deepcopy(working)

    def _load_locked(self) -> Any:
        if not self.path.exists():
            self.revision = 0
            self.status = AtomicDocumentStatus("absent", self.path)
            return self.default_factory()
        try:
            if self.sensitive:
                restrict_private_file(self.path)
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            document, revision, migrated = self._decode(raw)
            if migrated:
                # A sensitive legacy document may contain plaintext credentials.
                # Never copy it into the durable backup slot during migration.
                self._write_locked(
                    document,
                    revision + 1,
                    preserve_current=not self.sensitive,
                )
                if self.sensitive:
                    self._atomic_copy(self.path, self.backup_path)
            else:
                self.revision = revision
                self.status = AtomicDocumentStatus("valid", self.path, revision=revision)
            return document
        except AtomicDocumentVersionError as exc:
            self.status = AtomicDocumentStatus(
                "future_version",
                self.path,
                error=str(exc),
                backup_path=self.backup_path,
            )
            return self.default_factory()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self._recover_locked(exc)

    def _decode(self, raw: Any) -> tuple[Any, int, bool]:
        if isinstance(raw, dict) and raw.get("schema") == self.schema and "document" in raw:
            version = raw.get("version")
            revision = raw.get("revision")
            if not isinstance(version, int) or version < 1:
                raise ValueError("document version must be a positive integer")
            if not isinstance(revision, int) or revision < 0:
                raise ValueError("document revision must be a non-negative integer")
            if version > self.current_version:
                raise AtomicDocumentVersionError(
                    f"{self.schema} schema {version} is newer than supported schema {self.current_version}"
                )
            document = raw["document"]
            digest = raw.get("checksum")
            if not isinstance(digest, str) or digest != _checksum(document):
                raise ValueError("document checksum verification failed")
            migrated = version != self.current_version
        else:
            version = 0
            revision = 0
            document = raw
            migrated = True

        while version < self.current_version:
            migration = self.migrations.get(version)
            if migration is None:
                raise AtomicDocumentVersionError(f"No {self.schema} migration is registered from schema {version}")
            document = migration(copy.deepcopy(document))
            version += 1
        self.validator(document)
        return document, revision, migrated

    def _recover_locked(self, error: Exception) -> Any:
        quarantine = self._quarantine_copy_locked()
        if self.backup_path.exists():
            try:
                if self.sensitive:
                    restrict_private_file(self.backup_path)
                backup_raw = json.loads(self.backup_path.read_text(encoding="utf-8"))
                document, revision, _migrated = self._decode(backup_raw)
                self._write_locked(document, revision + 1, preserve_current=False)
                self.status = AtomicDocumentStatus(
                    "recovered",
                    self.path,
                    revision=self.revision,
                    error=str(error),
                    quarantine_path=quarantine,
                    backup_path=self.backup_path,
                )
                log.warning("Recovered %s from verified backup; damaged source: %s", self.schema, quarantine)
                return document
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as backup_error:
                error = AtomicDocumentRecoveryError(f"{error}; backup recovery also failed: {backup_error}")
        self.status = AtomicDocumentStatus(
            "corrupt",
            self.path,
            error=str(error),
            quarantine_path=quarantine,
            backup_path=self.backup_path if self.backup_path.exists() else None,
        )
        log.error("Recovery required for %s: %s", self.path, error)
        return self.default_factory()

    def _quarantine_copy_locked(self) -> Path | None:
        try:
            self.recovery_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            destination = self.recovery_dir / f"{self.path.name}.{timestamp}.corrupt"
            if self.sensitive:
                atomic_copy_private_file(self.path, destination)
            else:
                shutil.copy2(self.path, destination)
            return destination
        except OSError as exc:
            log.error("Could not quarantine damaged sidecar %s: %s", self.path, exc)
            return None

    def _write_locked(self, document: Any, revision: int, *, preserve_current: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if preserve_current and self.path.exists():
            self._atomic_copy(self.path, self.backup_path)
        envelope = {
            "schema": self.schema,
            "version": self.current_version,
            "revision": revision,
            "updated_at": datetime.now().isoformat(timespec="milliseconds"),
            "checksum": _checksum(document),
            "document": document,
        }
        fd, temporary = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(envelope, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            verified = json.loads(Path(temporary).read_text(encoding="utf-8"))
            decoded, decoded_revision, migrated = self._decode(verified)
            if migrated or decoded_revision != revision or decoded != document:
                raise ValueError("atomic document verification failed")
            if self.sensitive:
                restrict_private_file(temporary)
            os.replace(temporary, self.path)
            self._fsync_parent()
            self.revision = revision
            self.status = AtomicDocumentStatus(
                "valid",
                self.path,
                revision=revision,
                backup_path=self.backup_path,
            )
        except Exception:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _atomic_copy(self, source: Path, destination: Path) -> None:
        fd, temporary = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        os.close(fd)
        try:
            shutil.copy2(source, temporary)
            with open(temporary, "rb+") as handle:
                os.fsync(handle.fileno())
            if self.sensitive:
                restrict_private_file(temporary)
            os.replace(temporary, destination)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise

    def _fsync_parent(self) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
