"""Redacted, bounded projection of local bookmark processing history."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import re
from pathlib import Path
from bookmark_organizer_pro.constants import APP_DIR
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.job_ledger import (
    JobLedger,
    JobRecord,
    redact_job_error,
)
from bookmark_organizer_pro.services.snapshot import SnapshotArchiver, SnapshotFailureStore
from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore


MAX_TIMELINE_EVENTS = 200
MAX_ARTIFACT_BYTES = 2_000_000_000
MAX_DIGEST_BYTES = 100_000_000
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"(?i)(?:[a-z]:\\|\\\\|/)[^\s,;]+")
_LABEL_RE = re.compile(r"[^a-zA-Z0-9_.:/ -]+")


def sanitize_processing_error(error: object) -> str:
    """Return a short error that cannot expose URLs, paths, or secrets."""

    text = redact_job_error(error)
    text = re.sub(
        r"(?i)(response\s+body\s*[:=]).*$",
        r"\1 [REDACTED]",
        text,
    )
    text = _PATH_RE.sub("[PATH]", text)
    return " ".join(text.split())[:500]


def _safe_label(value: object, fallback: str = "unknown") -> str:
    text = _LABEL_RE.sub("", str(value or "")).strip()
    return text[:80] or fallback


def _safe_size(value: object) -> int:
    try:
        return min(MAX_ARTIFACT_BYTES, max(0, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def _safe_digest(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if _DIGEST_RE.fullmatch(text) else ""


def _timestamp_key(value: str) -> tuple[int, str]:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return (0, parsed.isoformat())
    except (TypeError, ValueError):
        return (1, text)


@dataclass(frozen=True)
class ProcessingTimelineEvent:
    """One sanitized local processing event or derived artifact state."""

    event_id: str
    operation: str
    backend: str
    state: str
    timestamp: str
    artifact_size: int = 0
    artifact_digest: str = ""
    error: str = ""
    retryable: bool = False
    removable: bool = False
    artifact_id: str = ""
    job_id: str = ""
    language: str = ""

    @property
    def digest(self) -> str:
        """Compatibility alias for consumers that call digests simply ``digest``."""

        return self.artifact_digest

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProcessingTimeline:
    """Chronologically ordered events for one bookmark."""

    bookmark_id: int | None
    events: tuple[ProcessingTimelineEvent, ...]

    @property
    def retryable_events(self) -> tuple[ProcessingTimelineEvent, ...]:
        return tuple(event for event in self.events if event.retryable)

    @property
    def failed_events(self) -> tuple[ProcessingTimelineEvent, ...]:
        return tuple(event for event in self.events if event.state == "failure")

    def to_dict(self) -> dict:
        return {
            "bookmark_id": self.bookmark_id,
            "events": [event.to_dict() for event in self.events],
        }


class ProcessingTimelineService:
    """Project local processing records without reading or exposing content."""

    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        job_ledger: JobLedger | None = None,
        failure_store: SnapshotFailureStore | None = None,
        history_store: SnapshotHistoryStore | None = None,
        event_limit: int = MAX_TIMELINE_EVENTS,
    ):
        inferred_dir = Path(getattr(job_ledger, "path", APP_DIR)).parent
        self.data_dir = Path(data_dir or inferred_dir).resolve()
        self.job_ledger = job_ledger or JobLedger(self.data_dir / "job_ledger.json")
        self.failure_store = failure_store or SnapshotFailureStore(
            self.data_dir / "snapshot_failures.json"
        )
        self.history_store = history_store or SnapshotHistoryStore(
            self.data_dir / "snapshots"
        )
        self.snapshots_dir = self.data_dir / "snapshots"
        self.extracted_dir = self.data_dir / "extracted"
        self.transcripts_dir = self.data_dir / "transcripts"
        self.embeddings_dir = self.data_dir / "embeddings"
        self.event_limit = max(10, min(MAX_TIMELINE_EVENTS, int(event_limit)))

    def project(self, bookmark: Bookmark) -> ProcessingTimeline:
        """Build a best-effort projection from all compatible local stores."""

        events: list[ProcessingTimelineEvent] = []
        bookmark_id = bookmark.id
        if bookmark_id is not None:
            events.append(
                ProcessingTimelineEvent(
                    event_id=f"capture:{int(bookmark_id)}",
                    operation="capture",
                    backend="library",
                    state="success",
                    timestamp=str(bookmark.created_at or ""),
                )
            )

        jobs = self._safe_jobs(bookmark_id)
        for record in jobs:
            events.append(self._event_from_job(record))

        for failure in self._safe_failures(bookmark_id):
            events.append(self._event_from_failure(failure))

        versions = self._safe_versions(bookmark_id)
        if versions:
            for version in versions:
                size, digest, present = self._artifact_info(
                    version.path,
                    expected_size=version.size,
                    expected_digest=version.sha256,
                )
                events.append(
                    ProcessingTimelineEvent(
                        event_id=f"snapshot:{version.version_id}",
                        operation="snapshot",
                        backend=_safe_label(version.backend, "snapshot"),
                        state="success" if present else "missing",
                        timestamp=str(version.captured_at or ""),
                        artifact_size=size,
                        artifact_digest=digest,
                        removable=True,
                        artifact_id=version.version_id,
                    )
                )
        elif str(bookmark.snapshot_path or "").strip():
            size, digest, present = self._artifact_info(
                bookmark.snapshot_path,
                expected_size=bookmark.snapshot_size,
                expected_digest=bookmark.snapshot_sha256,
            )
            events.append(
                ProcessingTimelineEvent(
                    event_id=f"snapshot:current:{bookmark_id}",
                    operation="snapshot",
                    backend=_safe_label(bookmark.snapshot_backend, "snapshot"),
                    state="success" if present else "missing",
                    timestamp=str(bookmark.snapshot_at or ""),
                    artifact_size=size,
                    artifact_digest=digest,
                    removable=True,
                    artifact_id="current",
                )
            )

        if str(bookmark.extracted_text_path or "").strip():
            size, digest, present = self._artifact_info(bookmark.extracted_text_path)
            ingest = self._latest_job(jobs, {"ingest"})
            events.append(
                ProcessingTimelineEvent(
                    event_id=f"extraction:{bookmark_id}",
                    operation="extraction",
                    backend=_safe_label(ingest.backend if ingest else "content-extractor"),
                    state="success" if present else "missing",
                    timestamp=self._job_timestamp(ingest) or str(bookmark.modified_at or ""),
                    artifact_size=size,
                    artifact_digest=digest,
                    removable=True,
                    artifact_id="extracted-text",
                )
            )

        if str(getattr(bookmark, "youtube_transcript_path", "") or "").strip():
            size, digest, present = self._artifact_info(
                bookmark.youtube_transcript_path,
                expected_size=getattr(bookmark, "youtube_transcript_chars", 0),
                expected_digest=getattr(bookmark, "youtube_transcript_sha256", ""),
            )
            transcript = self._latest_job(jobs, {"youtube_transcript"})
            events.append(
                ProcessingTimelineEvent(
                    event_id=f"transcript:{bookmark_id}",
                    operation="youtube_transcript",
                    backend=_safe_label(
                        getattr(bookmark, "youtube_transcript_backend", "")
                        or (transcript.backend if transcript else "yt-dlp")
                    ),
                    state="success" if present else "missing",
                    timestamp=str(
                        getattr(bookmark, "youtube_transcript_fetched_at", "")
                        or self._job_timestamp(transcript)
                        or bookmark.modified_at
                        or ""
                    ),
                    artifact_size=size,
                    artifact_digest=digest,
                    removable=True,
                    artifact_id="youtube-transcript",
                    language=str(getattr(bookmark, "youtube_transcript_language", "") or "")[:32],
                )
            )

        if str(getattr(bookmark, "embedding_model", "") or "").strip():
            embedding = self._latest_job(jobs, {"embedding"})
            events.append(
                ProcessingTimelineEvent(
                    event_id=f"embedding:{bookmark_id}",
                    operation="embedding",
                    backend=_safe_label(
                        getattr(bookmark, "embedding_model", "")
                        or (embedding.backend if embedding else "embedding")
                    ),
                    state="success",
                    timestamp=self._job_timestamp(embedding) or str(bookmark.modified_at or ""),
                    artifact_size=_safe_size(embedding.bytes_processed if embedding else 0),
                    removable=True,
                    artifact_id="embedding",
                )
            )

        event_order = {
            "capture": 0,
            "metadata": 10,
            "link_check": 20,
            "ingest": 30,
            "extraction": 40,
            "snapshot": 50,
            "youtube_transcript": 60,
            "embedding": 70,
        }
        events.sort(
            key=lambda event: (
                *_timestamp_key(event.timestamp),
                event_order.get(event.operation, 25),
                event.event_id,
            )
        )
        return ProcessingTimeline(bookmark_id, tuple(events[-self.event_limit :]))

    def list_events(self, bookmark: Bookmark) -> list[ProcessingTimelineEvent]:
        """Return the projection as a list for simple UI/API consumers."""

        return list(self.project(bookmark).events)

    def diagnostics(self) -> dict[str, int | bool]:
        """Return aggregate, content-free timeline health for support diagnostics."""
        try:
            jobs = self.job_ledger.list_records()
        except Exception:
            jobs = []
        try:
            failures = self.failure_store.list_failures()
        except Exception:
            failures = []
        try:
            versions = self.history_store.list_all_versions()
        except Exception:
            versions = []
        return {
            "available": True,
            "job_events": len(jobs),
            "snapshot_failures": len(failures),
            "snapshot_versions": len(versions),
            "retryable_failures": sum(
                1 for record in jobs if record.outcome == "failure" and record.retryable
            ) + sum(1 for record in failures if record.retry_eligible),
        }

    def remove_derived_artifact(
        self,
        bookmark: Bookmark,
        event: ProcessingTimelineEvent,
        *,
        vector_store=None,
    ) -> tuple[bool, str]:
        """Remove one derived representation while preserving the bookmark."""

        operation = str(event.operation or "").strip().lower()
        if operation == "snapshot":
            if event.artifact_id and event.artifact_id != "current":
                if self.history_store.remove_version(event.artifact_id):
                    return True, "Snapshot version removed"
                return False, "Snapshot version could not be removed"
            archiver = SnapshotArchiver(
                snapshots_dir=self.snapshots_dir,
                failure_store=self.failure_store,
                job_ledger=self.job_ledger,
                history_store=self.history_store,
            )
            if not archiver.delete_snapshot(bookmark):
                return False, "Snapshot artifact could not be removed"
            self.history_store.clear_bookmark(bookmark.id)
            return True, "Snapshot artifact removed"

        if operation == "youtube_transcript":
            from bookmark_organizer_pro.services.youtube_transcript import YouTubeTranscriptService

            result = YouTubeTranscriptService(
                job_ledger=self.job_ledger,
                transcripts_dir=self.transcripts_dir,
            ).remove(bookmark)
            return bool(result.success), result.error or "Transcript artifact removed"

        if operation == "extraction":
            path = self._safe_path(bookmark.extracted_text_path)
            if path is None:
                return False, "Extracted text path is outside local storage"
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                return False, sanitize_processing_error(exc)
            bookmark.extracted_text_path = ""
            return True, "Extracted text removed"

        if operation == "embedding":
            if vector_store is None:
                return False, "Embedding index is unavailable"
            try:
                vector_store.delete_bookmark(int(bookmark.id))
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
                return False, sanitize_processing_error(exc)
            bookmark.embedding_model = ""
            bookmark.embedding_dim = 0
            return True, "Embedding index entries removed"

        return False, f"No removal action for {operation or 'unknown'}"

    def _safe_jobs(self, bookmark_id: int | None) -> list[JobRecord]:
        if bookmark_id is None:
            return []
        try:
            return [
                record
                for record in self.job_ledger.list_records()
                if record.bookmark_id == bookmark_id
            ]
        except Exception:
            return []

    def _safe_failures(self, bookmark_id: int | None):
        if bookmark_id is None:
            return []
        try:
            return [
                record
                for record in self.failure_store.list_failures()
                if record.bookmark_id == bookmark_id
            ]
        except Exception:
            return []

    def _safe_versions(self, bookmark_id: int | None):
        if bookmark_id is None:
            return []
        try:
            return self.history_store.list_versions(bookmark_id)
        except Exception:
            return []

    @staticmethod
    def _latest_job(jobs: list[JobRecord], types: set[str]) -> JobRecord | None:
        return next(
            (
                record
                for record in jobs
                if record.job_type in types and record.outcome == "success"
            ),
            None,
        )

    @staticmethod
    def _job_timestamp(record: JobRecord | None) -> str:
        if record is None:
            return ""
        return str(record.completed_at or record.started_at or "")

    @staticmethod
    def _event_from_job(record: JobRecord) -> ProcessingTimelineEvent:
        operation = _safe_label(record.job_type, "job")
        return ProcessingTimelineEvent(
            event_id=f"job:{record.job_id}",
            operation=operation,
            backend=_safe_label(record.backend),
            state=record.outcome,
            timestamp=str(record.completed_at or record.started_at or ""),
            artifact_size=_safe_size(record.bytes_processed),
            error=sanitize_processing_error(record.error),
            retryable=bool(record.retryable and record.outcome == "failure"),
            artifact_id=record.job_id,
            job_id=record.job_id,
            language=str(record.language or "")[:32],
        )

    @staticmethod
    def _event_from_failure(record) -> ProcessingTimelineEvent:
        backends = []
        details = []
        for attempt in tuple(getattr(record, "attempts", ()) or ()):
            backend = _safe_label(getattr(attempt, "backend", ""))
            if backend and backend not in backends:
                backends.append(backend)
            message = sanitize_processing_error(getattr(attempt, "message", ""))
            if message:
                details.append(f"{backend}: {message}")
        error = sanitize_processing_error(getattr(record, "error", ""))
        if details:
            error = "; ".join(details)[:500]
        return ProcessingTimelineEvent(
            event_id=f"snapshot-failure:{getattr(record, 'key', 'unknown')}",
            operation="snapshot",
            backend=", ".join(backends)[:80] or "snapshot",
            state="failure",
            timestamp=str(getattr(record, "failed_at", "") or ""),
            error=error,
            retryable=bool(getattr(record, "retry_eligible", False)),
            artifact_id="failure",
        )

    def _safe_path(self, value: object) -> Path | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            path = Path(raw).expanduser().resolve(strict=False)
            if not path.is_relative_to(self.data_dir):
                return None
            return path
        except (OSError, RuntimeError, ValueError):
            return None

    def _artifact_info(
        self,
        path_value: object,
        *,
        expected_size: object = 0,
        expected_digest: object = "",
    ) -> tuple[int, str, bool]:
        expected_size_value = _safe_size(expected_size)
        expected_digest_value = _safe_digest(expected_digest)
        path = self._safe_path(path_value)
        if path is None:
            return expected_size_value, expected_digest_value, False
        try:
            if not path.is_file():
                return expected_size_value, expected_digest_value, False
            size = _safe_size(path.stat().st_size)
            if size > MAX_DIGEST_BYTES:
                return size, expected_digest_value, True
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return size, digest.hexdigest(), True
        except OSError:
            return expected_size_value, expected_digest_value, False


__all__ = [
    "MAX_TIMELINE_EVENTS",
    "ProcessingTimeline",
    "ProcessingTimelineEvent",
    "ProcessingTimelineService",
    "sanitize_processing_error",
]
