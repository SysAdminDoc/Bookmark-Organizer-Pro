"""Durable, resumable import sessions with row-level diagnostics."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from bookmark_organizer_pro.text_format import pluralize
from typing import Any, Callable

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.services.atomic_document_store import AtomicDocumentStore
from bookmark_organizer_pro.services.job_ledger import JobLedger, redact_job_error
from bookmark_organizer_pro.utils import normalize_url


IMPORT_SESSIONS_FILE = DATA_DIR / "import_sessions.json"

# Every state a row can end in that one of the report's counters covers. A row
# outside this set is a record with no reported outcome.
_COUNTED_ROW_STATES = frozenset({"completed", "duplicate", "failed", "pending"})


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
    #: Damage to the source file. A truncated export parses into fewer records
    #: with no error, so an import can only be called complete when this is "".
    malformed_source: str = ""

    @property
    def found(self) -> int:
        """Records the source actually contained.

        The rows are what parsed; the losses are what the parser could not turn
        into a row. Their sum is the number a user counts in the export file,
        which is the question an import has to be able to answer.
        """
        return self.total + self.losses

    @property
    def accounted(self) -> int:
        """Records this import can say an outcome for."""
        return self.added + self.duplicates + self.failed + self.pending + self.losses

    @property
    def balances(self) -> bool:
        """Whether every record found has a recorded outcome.

        A row in an unrecognized state is invisible in the four counts above,
        which is how a partial import reads as a complete one. Reporting the
        gap is the entire point of the reconciliation.
        """
        return self.found == self.accounted

    @property
    def unaccounted(self) -> int:
        return self.found - self.accounted

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.__dict__)
        payload.update(
            found=self.found,
            accounted=self.accounted,
            unaccounted=self.unaccounted,
            balances=self.balances,
        )
        return payload


@dataclass(frozen=True)
class ImportPreflight:
    """Parsed source summary shown before a durable import mutates the library."""

    source: str
    source_paths: tuple[str, ...]
    source_digest: str
    total: int
    losses: int
    causes: dict[str, int]
    field_coverage: dict[str, int]
    bookmarks: tuple[Any, ...] = field(repr=False, compare=False)
    #: Damage to the file itself, as opposed to a bad record inside it.
    malformed_source: str = ""


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

    @classmethod
    def digest_sources(cls, paths: list[Path]) -> str:
        if len(paths) == 1:
            return cls.digest_source(paths[0])
        digest = hashlib.sha256()
        for path in paths:
            digest.update(b"\0source\0")
            digest.update(cls.digest_source(path).encode("ascii"))
        return digest.hexdigest()

    @staticmethod
    def _session_id(source: str, digest: str) -> str:
        return hashlib.sha256(f"{source}\0{digest}".encode()).hexdigest()[:20]

    @staticmethod
    def _row_key(index: int, url: str) -> str:
        canonical = normalize_url(url)
        return hashlib.sha256(f"{index}\0{canonical}".encode()).hexdigest()[:24]

    @staticmethod
    def _source_paths(source_path) -> list[Path]:
        values = source_path if isinstance(source_path, (list, tuple)) else [source_path]
        paths = [Path(value).resolve() for value in values]
        if not paths:
            raise ValueError("Import requires at least one source file")
        for path in paths:
            if not path.is_file():
                raise ValueError(f"Import source is not a readable file: {path}")
        return paths

    @staticmethod
    def _parse(importer, paths: list[Path]) -> list[Any]:
        if len(paths) > 1 and hasattr(importer, "from_paths"):
            return list(importer.from_paths([str(path) for path in paths]))
        if len(paths) != 1:
            raise ValueError("This importer accepts exactly one source file")
        return list(importer.from_path(str(paths[0])))

    def _apply_rows(
        self, manager, parsed, row_map, existing, session_id, cancel_requested, on_progress
    ) -> bool:
        """Write pending rows in one batch. Returns True if cancelled early.

        The whole loop runs inside ``manager.batch()`` so the library is written
        once at the end instead of once per row; a 20k-bookmark migration would
        otherwise rewrite the entire library 20k times.
        """
        batch = getattr(manager, "batch", None)
        scope = batch() if callable(batch) else contextlib.nullcontext()
        with scope:
            for key, bookmark in parsed:
                row = row_map.get(key)
                if row is None or row.get("state") in {"completed", "duplicate"}:
                    continue
                latest = self.get(session_id) or {}
                if latest.get("cancel_requested") or (cancel_requested and cancel_requested()):
                    return True
                canonical = normalize_url(bookmark.url)
                try:
                    if canonical in existing:
                        self._set_row(session_id, key, "duplicate", "canonical URL already exists")
                    else:
                        category = str(getattr(bookmark, "category", "") or "")
                        if category in {"", "Imported", "Uncategorized", "Uncategorized / Needs Review"}:
                            categorizer = getattr(getattr(manager, "category_manager", None), "categorize_url", None)
                            if categorizer:
                                bookmark.category = categorizer(bookmark.url, bookmark.title)
                        manager.add_bookmark(bookmark)
                        existing.add(canonical)
                        self._set_row(session_id, key, "completed", "")
                except Exception as exc:
                    self._set_row(session_id, key, "failed", redact_job_error(exc))
                if on_progress:
                    on_progress(self._report(self.get(session_id) or {}))
        return False

    @staticmethod
    def _library_file_is_absent(manager) -> bool:
        """True only when the library has never been written to disk.

        A missing file is the one safepoint failure that is safe to recover
        from, because there is no prior state that a write could destroy.
        """
        storage = getattr(manager, "storage", None)
        filepath = getattr(storage, "filepath", None)
        if filepath is None:
            return False
        try:
            return not Path(filepath).exists()
        except (OSError, TypeError, ValueError):
            return False

    def preflight(self, importer, source_path, *, source: str) -> ImportPreflight:
        paths = self._source_paths(source_path)
        digest = self.digest_sources(paths)
        bookmarks = self._parse(importer, paths)
        if not bookmarks:
            raise ValueError("Import source contains 0 valid bookmarks; no changes were made")
        stats = getattr(importer, "stats", None)
        losses = max(0, int(getattr(stats, "skipped", 0) or 0))
        raw_causes = getattr(stats, "causes", {}) or {}
        causes = {
            str(cause)[:300]: max(1, int(count))
            for cause, count in raw_causes.items()
            if str(cause).strip()
        }
        placeholders = {"", "Imported", "Uncategorized", "Uncategorized / Needs Review"}
        coverage = {
            "title": sum(bool(str(bookmark.title or "").strip()) for bookmark in bookmarks),
            "folder": sum(str(bookmark.category or "").strip() not in placeholders for bookmark in bookmarks),
            "tags": sum(bool(bookmark.tags) for bookmark in bookmarks),
            "notes": sum(bool(str(bookmark.notes or bookmark.description or "").strip()) for bookmark in bookmarks),
            "source date": sum(bool(str(bookmark.add_date or "").strip()) for bookmark in bookmarks),
        }
        return ImportPreflight(
            source=str(source),
            source_paths=tuple(str(path) for path in paths),
            source_digest=digest,
            total=len(bookmarks),
            losses=losses,
            causes=causes,
            field_coverage=coverage,
            bookmarks=tuple(bookmarks),
            malformed_source=str(getattr(stats, "malformed_source", "") or "")[:300],
        )

    def run(
        self,
        manager,
        importer,
        source_path,
        *,
        source: str,
        retry_failed: bool = False,
        cancel_requested: Callable[[], bool] | None = None,
        on_progress: Callable[[ImportSessionReport], None] | None = None,
        prepared: ImportPreflight | None = None,
    ) -> ImportSessionReport:
        paths = self._source_paths(source_path)
        digest = self.digest_sources(paths)
        if prepared is None:
            prepared = self.preflight(importer, paths, source=source)
        if prepared.source != str(source) or prepared.source_digest != digest:
            raise RuntimeError("Import preflight no longer matches the selected source")
        session_id = self._session_id(source, digest)
        bookmarks = list(prepared.bookmarks)
        parsed = [(self._row_key(index, bookmark.url), bookmark) for index, bookmark in enumerate(bookmarks)]
        session = self._ensure_session(session_id, source, paths, digest, parsed, prepared)
        if session["status"] == "completed" and not retry_failed:
            return self._report(session)
        if retry_failed:
            self._update_session(session_id, lambda item: self._reset_failed(item))
        session = self.get(session_id) or session
        if not session.get("safepoint"):
            safepoint = manager.create_safepoint(f"pre-import-{session_id[:8]}") or ""
            if not safepoint and self._library_file_is_absent(manager):
                # A library that has never been written has no file to snapshot,
                # which is the normal first-run migration case. Persist the
                # empty state so the safepoint is a real rollback target.
                # Any OTHER safepoint failure (copy error, unwritable backup
                # directory, full disk) must still refuse the import without
                # touching the library.
                try:
                    manager.save_bookmarks()
                except Exception as exc:
                    raise RuntimeError(
                        "Import stopped because a rollback safepoint could not be created"
                    ) from exc
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
            cancelled_early = self._apply_rows(
                manager, parsed, row_map, existing, session_id, cancel_requested, on_progress
            )
            if cancelled_early:
                self._update_session(session_id, lambda item: item.update(status="cancelled") or item)
                job.cancel("import cancelled with remaining rows checkpointed")
                return self._finalize(session_id, started, manager, on_progress)
            report = self._finalize(session_id, started, manager, on_progress)
            if report.failed:
                job.fail(f"{pluralize(report.failed, 'import row')} failed", retryable=True,
                         bytes_processed=self._source_size(paths))
            else:
                job.succeed(bytes_processed=self._source_size(paths))
            return report
        except Exception as exc:
            terminal_cause = redact_job_error(exc)
            self._update_session(
                session_id,
                lambda item: item.update(status="interrupted", terminal_cause=terminal_cause) or item,
            )
            job.fail(exc, retryable=True, bytes_processed=self._source_size(paths))
            raise

    @staticmethod
    def _source_size(paths: list[Path]) -> int:
        return sum(path.stat().st_size for path in paths)

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
        source_paths = self._paths_for_session(session)
        self._validate_retry_sources(session, source_paths)
        return self.run(
            manager,
            importer,
            source_paths,
            source=session["source"],
            retry_failed=True,
        )

    def resume(self, manager, session_id: str) -> ImportSessionReport:
        session = self.get(session_id)
        if not session:
            raise RuntimeError("Import session was not found")
        importer = self._importer_for_source(session.get("source", ""))
        source_paths = self._paths_for_session(session)
        self._validate_retry_sources(session, source_paths)
        return self.run(manager, importer, source_paths, source=session["source"])

    @staticmethod
    def _paths_for_session(session: dict[str, Any]) -> list[Path]:
        values = session.get("source_paths") or [session.get("source_path")]
        return [Path(str(value or "")) for value in values]

    def _validate_retry_sources(self, session: dict[str, Any], paths: list[Path]) -> None:
        if not paths or any(not path.is_file() for path in paths):
            raise RuntimeError("Original import source is no longer available")
        if self.digest_sources(paths) != session.get("source_digest"):
            raise RuntimeError("Original import source changed; retry was refused")

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

    def rejected_rows(self, session_id: str) -> list[dict[str, Any]]:
        """Every record that did not land, with the reason it did not.

        A count tells a user something went wrong; this tells them which rows,
        so they can fix the source and re-import only those.
        """
        session = self.get(session_id) or {}
        rejected = []
        for row in session.get("rows", []):
            state = str(row.get("state") or "pending")
            if state in {"completed", "duplicate"}:
                continue
            rejected.append({
                "position": int(row.get("index", 0)) + 1,
                # Sessions written before rows carried a URL still list their
                # position and reason rather than being dropped from the file.
                "url": str(row.get("url") or ""),
                "state": state,
                "reason": str(row.get("cause") or "").strip() or "no reason recorded",
            })
        return rejected

    def write_rejected_rows(self, session_id: str, destination: str | Path) -> Path:
        """Write the rejected rows somewhere the user can open them."""
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        from bookmark_organizer_pro.utils.runtime import csv_safe_cell

        rows = self.rejected_rows(session_id)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["position", "url", "state", "reason"]
            )
            writer.writeheader()
            for row in rows:
                # The URL and the reason come from a file the user did not
                # write, and this one opens in a spreadsheet.
                writer.writerow({
                    "position": row["position"],
                    "url": csv_safe_cell(row["url"]),
                    "state": csv_safe_cell(row["state"]),
                    "reason": csv_safe_cell(row["reason"]),
                })
        return path

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

    def _ensure_session(self, session_id, source, paths, digest, parsed, preflight):
        existing = self.get(session_id)
        if existing:
            return existing
        session = {
            "session_id": session_id,
            "source": str(source)[:80],
            "source_path": str(paths[0]),
            "source_paths": [str(path) for path in paths],
            "source_digest": digest,
            "status": "pending",
            "created_at": _now(),
            "updated_at": _now(),
            "duration_ms": 0,
            "losses": preflight.losses,
            "malformed_source": preflight.malformed_source,
            "source_causes": dict(preflight.causes),
            "field_coverage": dict(preflight.field_coverage),
            "safepoint": "",
            "final_revision": 0,
            "cancel_requested": False,
            "terminal_cause": "",
            # The key is a digest, so the URL is kept alongside it: a list of
            # rejected rows is only reviewable if it names the rows.
            "rows": [
                {
                    "key": key,
                    "index": index,
                    "state": "pending",
                    "cause": "",
                    "url": str(getattr(bookmark, "url", "") or "")[:2048],
                }
                for index, (key, bookmark) in enumerate(parsed)
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
                # Everything the parser found may have landed and the file can
                # still have been cut off. That is not a completed import of
                # that file, and calling it one is the failure this reports.
                if item.get("malformed_source") and item["status"] == "completed":
                    item["status"] = "attention"
                # A row in a state none of the counters recognize would be
                # invisible, and the import would report success while having
                # silently lost it. Say so instead.
                unknown = [state for state in states if state not in _COUNTED_ROW_STATES]
                if unknown:
                    item["status"] = "accounting_error"
                    item["terminal_cause"] = (
                        f"unaccounted row states: {sorted(set(map(str, unknown)))}"
                    )
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
        from bookmark_organizer_pro.importers import (
            BrowserProfileSessionImporter,
            FirefoxBookmarkBackupImporter,
            GenericFileSessionImporter,
            ZoteroRDFSessionImporter,
        )

        normalized = str(source or "").lower()
        if normalized in {"generic-files", "genericfilesession"}:
            return GenericFileSessionImporter()
        if normalized.startswith("browserprofile:"):
            return BrowserProfileSessionImporter(normalized.split(":", 1)[1])

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
                importers_extra.MappedCSVImporter,
                importers_extra.OmnivoreImporter,
                FirefoxBookmarkBackupImporter,
                ZoteroRDFSessionImporter,
            )
        }
        importer_class = classes.get(normalized)
        if importer_class is None:
            raise RuntimeError(f"Retry is unavailable for import source {source!r}")
        return importer_class()

    @staticmethod
    def _report(session: dict[str, Any]) -> ImportSessionReport:
        rows = session.get("rows", [])
        states = [row.get("state", "pending") for row in rows]
        causes: dict[str, int] = {}
        for cause, count in (session.get("source_causes") or {}).items():
            causes[str(cause)] = max(1, int(count))
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
            malformed_source=str(session.get("malformed_source") or ""),
        )
