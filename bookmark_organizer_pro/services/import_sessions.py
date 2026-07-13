"""Durable, resumable import sessions with row-level diagnostics."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.services.atomic_document_store import AtomicDocumentStore
from bookmark_organizer_pro.services.job_ledger import JobLedger, redact_job_error
from bookmark_organizer_pro.utils import normalize_url


IMPORT_SESSIONS_FILE = DATA_DIR / "import_sessions.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def _validate(document: Any) -> None:
    if not isinstance(document, dict) or not isinstance(document.get("sessions", []), list):
        raise ValueError("import sessions must contain a sessions array")
    for session in document.get("sessions", []):
        if not isinstance(session, dict) or not session.get("session_id"):
            raise ValueError("import session record is invalid")
        if not isinstance(session.get("rows", []), list):
            raise ValueError("import session rows must be an array")


@dataclass(frozen=True)
class ImportSessionReport:
    session_id: str
    source: str
    source_digest: str
    status: str
    total: int
    added: int
    duplicates: int
    failed: int
    losses: int
    pending: int
    duration_ms: int
    causes: dict[str, int]
    safepoint: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class ImportSessionManager:
    """Persist row checkpoints so interrupted imports can resume safely."""

    def __init__(self, path: str | Path | None = None, job_ledger: JobLedger | None = None):
        self.path = Path(path or IMPORT_SESSIONS_FILE)
        self._store = AtomicDocumentStore(
            self.path,
            schema="bookmark-organizer-pro/import-sessions",
            default_factory=lambda: {"sessions": []},
            validator=_validate,
        )
        ledger_path = self.path.with_name("job_ledger.json")
        self.job_ledger = job_ledger or JobLedger(ledger_path)

    @staticmethod
    def digest_source(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _session_id(source: str, digest: str) -> str:
        return hashlib.sha256(f"{source}\0{digest}".encode()).hexdigest()[:20]

    @staticmethod
    def _row_key(index: int, url: str) -> str:
        canonical = normalize_url(url)
        return hashlib.sha256(f"{index}\0{canonical}".encode()).hexdigest()[:24]

    def run(
        self,
        manager,
        importer,
        source_path: str | Path,
        *,
        source: str,
        retry_failed: bool = False,
        cancel_requested: Callable[[], bool] | None = None,
        on_progress: Callable[[ImportSessionReport], None] | None = None,
    ) -> ImportSessionReport:
        source_path = Path(source_path).resolve()
        digest = self.digest_source(source_path)
        session_id = self._session_id(source, digest)
        bookmarks = list(importer.from_path(str(source_path)))
        parsed = [(self._row_key(index, bookmark.url), bookmark) for index, bookmark in enumerate(bookmarks)]
        session = self._ensure_session(session_id, source, source_path, digest, parsed, importer)
        if session["status"] == "completed" and not retry_failed:
            return self._report(session)
        if retry_failed:
            self._update_session(session_id, lambda item: self._reset_failed(item))
        session = self.get(session_id) or session
        if not session.get("safepoint"):
            safepoint = manager.create_safepoint(f"pre-import-{session_id[:8]}") or ""
            if not safepoint:
                raise RuntimeError("Import stopped because a rollback safepoint could not be created")
            self._update_session(session_id, lambda item: item.update(safepoint=safepoint) or item)

        started = time.monotonic()
        job = self.job_ledger.start("import", backend=source)
        existing = {normalize_url(bookmark.url) for bookmark in manager.get_all_bookmarks()}
        row_map = {row["key"]: row for row in (self.get(session_id) or {}).get("rows", [])}
        self._update_session(session_id, lambda item: item.update(status="running", cancel_requested=False) or item)
        try:
            for key, bookmark in parsed:
                row = row_map.get(key)
                if row is None or row.get("state") in {"completed", "duplicate"}:
                    continue
                latest = self.get(session_id) or {}
                if latest.get("cancel_requested") or (cancel_requested and cancel_requested()):
                    self._update_session(session_id, lambda item: item.update(status="cancelled") or item)
                    job.cancel("import cancelled with remaining rows checkpointed")
                    return self._finalize(session_id, started, manager, on_progress)
                canonical = normalize_url(bookmark.url)
                try:
                    if canonical in existing:
                        self._set_row(session_id, key, "duplicate", "canonical URL already exists")
                    else:
                        manager.add_bookmark(bookmark)
                        existing.add(canonical)
                        self._set_row(session_id, key, "completed", "")
                except Exception as exc:
                    self._set_row(session_id, key, "failed", redact_job_error(exc))
                if on_progress:
                    on_progress(self._report(self.get(session_id) or {}))
            report = self._finalize(session_id, started, manager, on_progress)
            if report.failed:
                job.fail(f"{report.failed} import row(s) failed", retryable=True,
                         bytes_processed=source_path.stat().st_size)
            else:
                job.succeed(bytes_processed=source_path.stat().st_size)
            return report
        except Exception as exc:
            terminal_cause = redact_job_error(exc)
            self._update_session(
                session_id,
                lambda item: item.update(status="interrupted", terminal_cause=terminal_cause) or item,
            )
            job.fail(exc, retryable=True, bytes_processed=source_path.stat().st_size)
            raise

    def request_cancel(self, session_id: str) -> bool:
        session = self.get(session_id)
        if not session:
            return False
        full_id = session["session_id"]

        def mutate(item):
            item["cancel_requested"] = True
            return item

        self._update_session(full_id, mutate)
        return True

    def retry(self, manager, session_id: str) -> ImportSessionReport:
        session = self.get(session_id)
        if not session:
            raise RuntimeError("Import session was not found")
        importer = self._importer_for_source(session.get("source", ""))
        source_path = Path(str(session.get("source_path") or ""))
        if not source_path.is_file():
            raise RuntimeError("Original import source is no longer available")
        if self.digest_source(source_path) != session.get("source_digest"):
            raise RuntimeError("Original import source changed; retry was refused")
        return self.run(
            manager,
            importer,
            source_path,
            source=session["source"],
            retry_failed=True,
        )

    def rollback(self, manager, session_id: str) -> ImportSessionReport:
        session = self.get(session_id)
        if not session or not session.get("safepoint"):
            raise RuntimeError("Import session has no rollback safepoint")
        current_revision = getattr(manager.storage, "current_revision", lambda: 0)()
        final_revision = int(session.get("final_revision") or 0)
        if final_revision and current_revision != final_revision:
            raise RuntimeError("Library changed after this import; rollback was refused to protect newer edits")
        if not manager.restore_backup(session["safepoint"]):
            raise RuntimeError("Import rollback safepoint could not be restored")
        full_id = session["session_id"]
        self._update_session(full_id, lambda item: item.update(status="rolled_back") or item)
        return self._report(self.get(full_id) or {})

    def list(self, limit: int = 50) -> list[ImportSessionReport]:
        sessions = self._store.load().get("sessions", [])
        sessions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return [self._report(item) for item in sessions[: max(0, int(limit))]]

    def get(self, session_id: str) -> dict[str, Any] | None:
        prefix = str(session_id or "")
        matches = [
            item for item in self._store.load().get("sessions", [])
            if str(item.get("session_id", "")).startswith(prefix)
        ]
        return matches[0] if len(matches) == 1 else None

    def report(self, session_id: str) -> ImportSessionReport | None:
        session = self.get(session_id)
        return self._report(session) if session else None

    def _ensure_session(self, session_id, source, path, digest, parsed, importer):
        existing = self.get(session_id)
        if existing:
            return existing
        losses = max(0, int(getattr(getattr(importer, "stats", None), "skipped", 0) or 0))
        session = {
            "session_id": session_id,
            "source": str(source)[:80],
            "source_path": str(path),
            "source_digest": digest,
            "status": "pending",
            "created_at": _now(),
            "updated_at": _now(),
            "duration_ms": 0,
            "losses": losses,
            "safepoint": "",
            "final_revision": 0,
            "cancel_requested": False,
            "terminal_cause": "",
            "rows": [
                {"key": key, "index": index, "state": "pending", "cause": ""}
                for index, (key, _bookmark) in enumerate(parsed)
            ],
        }
        self._store.update(lambda doc: doc["sessions"].append(session) or doc)
        return session

    @staticmethod
    def _reset_failed(item):
        for row in item.get("rows", []):
            if row.get("state") == "failed":
                row.update(state="pending", cause="")
        item["status"] = "pending"
        item["terminal_cause"] = ""
        return item

    def _set_row(self, session_id: str, key: str, state: str, cause: str) -> None:
        def mutate(item):
            for row in item.get("rows", []):
                if row.get("key") == key:
                    row.update(state=state, cause=str(cause or "")[:300])
                    break
            return item
        self._update_session(session_id, mutate)

    def _finalize(self, session_id, started, manager, on_progress):
        def mutate(item):
            states = [row.get("state") for row in item.get("rows", [])]
            if item.get("status") != "cancelled":
                item["status"] = "completed" if "failed" not in states and "pending" not in states else "attention"
            item["duration_ms"] = int(item.get("duration_ms", 0)) + round((time.monotonic() - started) * 1000)
            item["final_revision"] = int(getattr(manager.storage, "current_revision", lambda: 0)())
            return item
        self._update_session(session_id, mutate)
        report = self._report(self.get(session_id) or {})
        if on_progress:
            on_progress(report)
        return report

    def _update_session(self, session_id: str, mutator: Callable[[dict], Any]) -> None:
        def update(document):
            for item in document.get("sessions", []):
                if item.get("session_id") == session_id:
                    mutator(item)
                    item["updated_at"] = _now()
                    break
            return document
        self._store.update(update)

    @staticmethod
    def _importer_for_source(source: str):
        from bookmark_organizer_pro import importers_extra
        from bookmark_organizer_pro.importers import FirefoxBookmarkBackupImporter

        classes = {
            cls.__name__.removesuffix("Importer").lower(): cls
            for cls in (
                importers_extra.PocketExportImporter,
                importers_extra.ReadwiseReaderCSVImporter,
                importers_extra.PinboardJSONImporter,
                importers_extra.InstapaperImporter,
                importers_extra.RedditSavedImporter,
                importers_extra.MatterImporter,
                importers_extra.WallabagJSONImporter,
                importers_extra.ArcBrowserImporter,
                FirefoxBookmarkBackupImporter,
            )
        }
        importer_class = classes.get(str(source or "").lower())
        if importer_class is None:
            raise RuntimeError(f"Retry is unavailable for import source {source!r}")
        return importer_class()

    @staticmethod
    def _report(session: dict[str, Any]) -> ImportSessionReport:
        rows = session.get("rows", [])
        states = [row.get("state", "pending") for row in rows]
        causes: dict[str, int] = {}
        for row in rows:
            cause = str(row.get("cause") or "").strip()
            if cause:
                causes[cause] = causes.get(cause, 0) + 1
        terminal = str(session.get("terminal_cause") or "").strip()
        if terminal:
            causes[terminal] = causes.get(terminal, 0) + 1
        return ImportSessionReport(
            session_id=str(session.get("session_id") or ""),
            source=str(session.get("source") or ""),
            source_digest=str(session.get("source_digest") or ""),
            status=str(session.get("status") or "unknown"),
            total=len(rows),
            added=states.count("completed"),
            duplicates=states.count("duplicate"),
            failed=states.count("failed"),
            losses=max(0, int(session.get("losses") or 0)),
            pending=states.count("pending"),
            duration_ms=max(0, int(session.get("duration_ms") or 0)),
            causes=causes,
            safepoint=str(session.get("safepoint") or ""),
        )
