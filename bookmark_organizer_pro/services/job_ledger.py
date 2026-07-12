"""Bounded, local-only history for capture and indexing work.

The ledger intentionally stores operational metadata only.  It never records a
URL, bookmark title, page content, query text, or credentials.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log


JOB_LEDGER_FILE = DATA_DIR / "job_ledger.json"
_URL_RE = re.compile(r"(?i)\bhttps?://[^\s\]\[<>{}\"']+")


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def safe_domain(url_or_domain: str | None) -> str:
    """Return only a normalized hostname, never URL path/query/user info."""
    value = str(url_or_domain or "").strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value if "://" in value else f"//{value}")
        hostname = (parsed.hostname or "").strip().rstrip(".").lower()
        return hostname.encode("idna").decode("ascii")[:255]
    except (UnicodeError, ValueError):
        return ""


def redact_job_error(error: object) -> str:
    """Bound and redact an error without leaking source URLs or content."""
    text = str(error or "")
    text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/\-=]+", r"\1[REDACTED]", text)
    text = re.sub(
        r"(?i)((?:api[_-]?key|apiToken|token|secret|password)\s*[:=]\s*)[^\s,;}]+",
        r"\1[REDACTED]",
        text,
    )
    text = _URL_RE.sub("[URL]", text)
    return " ".join(text.split())[:500]


@dataclass
class JobRecord:
    job_id: str
    job_type: str
    bookmark_id: int | None
    domain: str
    backend: str
    started_at: str
    completed_at: str = ""
    duration_ms: int = 0
    bytes_processed: int = 0
    outcome: str = "running"
    retryable: bool = False
    error: str = ""
    attempt: int = 1

    @classmethod
    def from_dict(cls, value: dict) -> "JobRecord | None":
        try:
            job_type = str(value.get("job_type") or "").strip()[:40]
            if not job_type:
                return None
            bookmark_id = value.get("bookmark_id")
            bookmark_id = int(bookmark_id) if bookmark_id is not None else None
            outcome = str(value.get("outcome") or "failure")
            if outcome not in {"running", "success", "failure", "cancelled"}:
                outcome = "failure"
            return cls(
                job_id=str(value.get("job_id") or uuid.uuid4().hex[:12])[:40],
                job_type=job_type,
                bookmark_id=bookmark_id,
                domain=safe_domain(value.get("domain")),
                backend=str(value.get("backend") or "")[:80],
                started_at=str(value.get("started_at") or "")[:40],
                completed_at=str(value.get("completed_at") or "")[:40],
                duration_ms=max(0, int(value.get("duration_ms") or 0)),
                bytes_processed=max(0, int(value.get("bytes_processed") or 0)),
                outcome=outcome,
                retryable=bool(value.get("retryable")),
                error=redact_job_error(value.get("error")),
                attempt=max(1, int(value.get("attempt") or 1)),
            )
        except (TypeError, ValueError):
            return None


class JobRun:
    """Handle used by a service to complete a persisted running job."""

    def __init__(self, ledger: "JobLedger", record: JobRecord):
        self.ledger = ledger
        self.record = record
        self._started_monotonic = time.monotonic()
        self._completed = False

    def succeed(self, *, bytes_processed: int = 0, backend: str | None = None) -> JobRecord:
        return self._finish("success", bytes_processed, False, "", backend)

    def fail(
        self,
        error: object,
        *,
        retryable: bool = True,
        bytes_processed: int = 0,
        backend: str | None = None,
    ) -> JobRecord:
        return self._finish("failure", bytes_processed, retryable, error, backend)

    def cancel(self, error: object = "cancelled") -> JobRecord:
        return self._finish("cancelled", 0, True, error, None)

    def _finish(
        self,
        outcome: str,
        bytes_processed: int,
        retryable: bool,
        error: object,
        backend: str | None,
    ) -> JobRecord:
        if self._completed:
            return self.record
        self.record.completed_at = _now()
        self.record.duration_ms = max(0, round((time.monotonic() - self._started_monotonic) * 1000))
        self.record.bytes_processed = max(0, int(bytes_processed or 0))
        self.record.outcome = outcome
        self.record.retryable = bool(retryable)
        self.record.error = redact_job_error(error)
        if backend is not None:
            self.record.backend = str(backend or "")[:80]
        self.ledger._replace(self.record)
        self._completed = True
        return self.record

    def __enter__(self) -> "JobRun":
        return self

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        if exc is not None:
            self.fail(exc, retryable=True)
        elif not self._completed:
            self.succeed()
        return False


class JobLedger:
    """Thread-safe atomic JSON ledger with bounded retention."""

    _lock = threading.RLock()

    def __init__(self, path: Path = JOB_LEDGER_FILE, max_records: int = 500):
        self.path = Path(path)
        self.max_records = max(10, min(5000, int(max_records)))

    def start(
        self,
        job_type: str,
        *,
        bookmark_id: int | None = None,
        url_or_domain: str = "",
        backend: str = "",
    ) -> JobRun:
        job_type = str(job_type or "unknown").strip().lower().replace(" ", "_")[:40]
        domain = safe_domain(url_or_domain)
        with self._lock:
            records = self.list_records()
            attempt = 1 + max(
                (
                    item.attempt
                    for item in records
                    if item.job_type == job_type
                    and item.bookmark_id == bookmark_id
                    and item.domain == domain
                    and item.outcome == "failure"
                ),
                default=0,
            )
            record = JobRecord(
                job_id=uuid.uuid4().hex[:12],
                job_type=job_type,
                bookmark_id=int(bookmark_id) if bookmark_id is not None else None,
                domain=domain,
                backend=str(backend or "")[:80],
                started_at=_now(),
                attempt=attempt,
            )
            self._append(record)
        return JobRun(self, record)

    def list_records(
        self,
        *,
        job_type: str = "",
        outcome: str = "",
        retryable: bool | None = None,
        domain: str = "",
        limit: int | None = None,
    ) -> list[JobRecord]:
        records = self._read()
        if job_type:
            records = [item for item in records if item.job_type == job_type]
        if outcome:
            records = [item for item in records if item.outcome == outcome]
        if retryable is not None:
            records = [item for item in records if item.retryable is retryable]
        if domain:
            normalized = safe_domain(domain)
            records = [item for item in records if item.domain == normalized]
        records.sort(key=lambda item: item.started_at, reverse=True)
        if limit is not None:
            records = records[:max(0, int(limit))]
        return records

    def get(self, job_id: str) -> JobRecord | None:
        prefix = str(job_id or "")
        matches = [item for item in self._read() if item.job_id.startswith(prefix)]
        return matches[0] if len(matches) == 1 else None

    def clear(self, *, job_type: str = "", outcome: str = "") -> int:
        with self._lock:
            records = self._read()
            kept = [
                item for item in records
                if not ((not job_type or item.job_type == job_type) and (not outcome or item.outcome == outcome))
            ]
            removed = len(records) - len(kept)
            if removed:
                self._write(kept)
        return removed

    def health(self, records: Iterable[JobRecord] | None = None) -> dict:
        items = list(records if records is not None else self._read())
        completed = [item for item in items if item.outcome != "running"]
        failures = [item for item in completed if item.outcome == "failure"]
        retryable = [item for item in failures if item.retryable]
        durations = [item.duration_ms for item in completed]
        by_type: dict[str, dict[str, int]] = {}
        for item in completed:
            metrics = by_type.setdefault(item.job_type, {"jobs": 0, "failures": 0, "bytes": 0})
            metrics["jobs"] += 1
            metrics["failures"] += int(item.outcome == "failure")
            metrics["bytes"] += item.bytes_processed

        cutoff = datetime.now() - timedelta(days=7)
        recent_bytes = 0
        for item in completed:
            try:
                if datetime.fromisoformat(item.completed_at) >= cutoff:
                    recent_bytes += item.bytes_processed
            except (TypeError, ValueError):
                continue
        try:
            ledger_bytes = self.path.stat().st_size
        except OSError:
            ledger_bytes = 0
        return {
            "jobs": len(completed),
            "running": sum(item.outcome == "running" for item in items),
            "failures": len(failures),
            "retryable_failures": len(retryable),
            "failure_rate": round(len(failures) / len(completed), 4) if completed else 0.0,
            "average_duration_ms": round(sum(durations) / len(durations)) if durations else 0,
            "processed_bytes": sum(item.bytes_processed for item in completed),
            "storage_growth_7d_bytes": recent_bytes,
            "ledger_bytes": ledger_bytes,
            "by_type": by_type,
            "privacy": {"content_stored": False, "urls_stored": False, "telemetry": False},
        }

    def _read(self) -> list[JobRecord]:
        with self._lock:
            if not self.path.exists():
                return []
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                raw = payload.get("jobs", []) if isinstance(payload, dict) else []
                return [record for item in raw if isinstance(item, dict) if (record := JobRecord.from_dict(item))]
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Could not load local job ledger: %s", exc)
                return []

    def _append(self, record: JobRecord) -> None:
        with self._lock:
            records = self._read()
            records.append(record)
            self._write(records)

    def _replace(self, record: JobRecord) -> None:
        with self._lock:
            records = self._read()
            found = any(item.job_id == record.job_id for item in records)
            records = [record if item.job_id == record.job_id else item for item in records]
            if not found:
                records.append(record)
            self._write(records)

    def _write(self, records: list[JobRecord]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            records = sorted(records, key=lambda item: item.started_at)[-self.max_records :]
            payload = {"version": 1, "updated_at": _now(), "jobs": [asdict(item) for item in records]}
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, self.path)
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise
