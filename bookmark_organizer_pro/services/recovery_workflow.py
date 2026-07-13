"""Validated, rollback-aware library recovery operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bookmark_organizer_pro.logging_config import log


ProgressCallback = Callable[[str, str, str], None]


@dataclass(frozen=True)
class RecoveryResult:
    """Terminal result for a restore or salvage operation."""

    operation: str
    success: bool
    summary: str
    source: str
    preserved_source: str = ""
    rollback_source: str = ""
    recovered_count: int = 0


class RecoveryWorkflow:
    """Run destructive recovery with explicit progress and final validation."""

    def __init__(self, manager, on_progress: ProgressCallback | None = None):
        self.manager = manager
        self.on_progress = on_progress or (lambda _status, _title, _detail: None)

    def _progress(self, status: str, title: str, detail: str = "") -> None:
        self.on_progress(status, title, detail)

    def _validate_loaded_library(self) -> tuple[bool, str]:
        if self.manager.recovery_required:
            return False, self.manager.recovery_message or "storage still requires recovery"
        bookmarks = list(self.manager.get_all_bookmarks())
        ids = [bookmark.id for bookmark in bookmarks]
        if len(ids) != len(set(ids)):
            return False, "restored library contains duplicate bookmark IDs"
        status = self.manager.storage_status
        expected_count = getattr(status, "count", len(bookmarks)) if status else len(bookmarks)
        if expected_count != len(bookmarks):
            return False, (
                f"storage reports {expected_count} bookmark(s), but {len(bookmarks)} loaded"
            )
        return True, f"validated {len(bookmarks)} bookmark(s)"

    def restore(self, backup_name: str) -> RecoveryResult:
        """Restore one verified backup, rolling back if activation validation fails."""
        backup_name = str(backup_name or "").strip()
        self._progress("ok", "Selected recovery source", backup_name)
        available = {name for name, _mtime, _size in self.manager.list_backups()}
        if backup_name not in available:
            return RecoveryResult(
                "restore", False, "Restore stopped: the selected backup is no longer available.",
                backup_name,
            )

        rollback = ""
        if not self.manager.recovery_required:
            rollback = self.manager.create_safepoint("pre-restore") or ""
            if not rollback:
                return RecoveryResult(
                    "restore", False,
                    "Restore stopped because a rollback safepoint could not be created.",
                    backup_name,
                )
        self._progress(
            "ok",
            "Protected current library",
            rollback or "damaged source will be preserved by the recovery backend",
        )

        try:
            if not self.manager.restore_backup(backup_name):
                raise RuntimeError("backup validation or activation failed")
            valid, detail = self._validate_loaded_library()
            if not valid:
                raise RuntimeError(detail)
            self._progress("ok", "Validated restored library", detail)
            return RecoveryResult(
                "restore", True, f"Restore complete — {detail}.", backup_name,
                rollback_source=rollback,
                recovered_count=len(self.manager.get_all_bookmarks()),
            )
        except Exception as exc:
            log.error("Validated restore failed for %s: %s", backup_name, exc)
            rolled_back = False
            if rollback:
                try:
                    rolled_back = bool(self.manager.restore_backup(rollback))
                except Exception:
                    log.exception("Could not roll back failed restore to %s", rollback)
            preserved = rollback or self._current_source_path()
            suffix = "; the previous library was restored" if rolled_back else ""
            return RecoveryResult(
                "restore", False,
                f"Restore failed: {exc}{suffix}. Preserved source: {preserved}",
                backup_name,
                preserved_source=preserved,
                rollback_source=rollback,
            )

    def salvage(self) -> RecoveryResult:
        """Salvage complete records and prove the damaged source survived."""
        source = self._current_source_path()
        self._progress("ok", "Scanning damaged library", source)
        try:
            count, preserved = self.manager.salvage_corrupt_file()
            self._progress("ok", "Preserved damaged source", preserved)
            preserved_path = Path(preserved)
            if count < 1:
                raise RuntimeError("no complete bookmark records were recovered")
            if not preserved or not preserved_path.is_file():
                raise RuntimeError("damaged source preservation could not be verified")
            valid, detail = self._validate_loaded_library()
            if not valid:
                raise RuntimeError(detail)
            if len(self.manager.get_all_bookmarks()) != count:
                raise RuntimeError("salvaged record count changed during activation")
            self._progress("ok", "Validated salvaged library", detail)
            return RecoveryResult(
                "salvage", True,
                f"Recovered and validated {count} bookmark(s). Damaged source: {preserved}",
                source,
                preserved_source=preserved,
                recovered_count=count,
            )
        except Exception as exc:
            log.error("Validated library salvage failed: %s", exc)
            preserved = self._current_source_path() or source
            return RecoveryResult(
                "salvage", False,
                f"Salvage failed: {exc}. Preserved source: {preserved}",
                source,
                preserved_source=preserved,
            )

    def _current_source_path(self) -> str:
        status = self.manager.storage_status
        path = getattr(status, "path", None) if status else None
        if path is None:
            path = getattr(self.manager, "filepath", "")
        return str(path or "")
