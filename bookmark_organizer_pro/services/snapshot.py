"""Content-aware, manifest-backed offline snapshot archiver.

HTML responses become inert, bundled HTML. Allowlisted binary responses retain
their exact bytes and safe extension. Every current artifact has a checksummed,
versioned manifest that records its capture provenance and representation.
"""

from __future__ import annotations

import base64
import hashlib
import html as html_lib
import importlib
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from bookmark_organizer_pro.constants import DATA_DIR, SNAPSHOTS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.job_ledger import JobLedger
from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore
from bookmark_organizer_pro.url_utils import URLUtilities

SNAPSHOT_FAILURES_FILE = DATA_DIR / "snapshot_failures.json"
_SAFE_CAPTURE_DATA_URI = re.compile(
    r"^data:(?:"
    r"image/(?:png|jpeg|gif|webp|avif|bmp|x-icon|vnd\.microsoft\.icon)|"
    r"font/(?:woff2?|ttf|otf)|"
    r"application/(?:font-woff|font-sfnt|vnd\.ms-fontobject|octet-stream)"
    r");base64,[a-z0-9+/=\s]+$",
    re.IGNORECASE,
)
SNAPSHOT_MANIFEST_SCHEMA = "bookmark-organizer-pro/snapshot-manifest"
SNAPSHOT_MANIFEST_VERSION = 1
_HTML_MIME_TYPES = {"text/html", "application/xhtml+xml"}
_GENERIC_MIME_TYPES = {
    "",
    "application/octet-stream",
    "application/download",
    "application/x-download",
}
_CURRENT_SNAPSHOT_EXTENSIONS = {".html", ".pdf", ".png", ".jpg", ".gif", ".webp"}
_HTML_PREFIX_RE = re.compile(
    br"^(?:(?:<!--.*?-->\s*)*)(?:<!doctype\s+html|<(?:(?:html|head|body|title|meta|link|style|"
    br"main|article|section|div|p|h[1-6]|table|ul|ol|pre|blockquote|nav|header|"
    br"footer)\b))",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class SnapshotFormat:
    """Validated on-disk representation selected from MIME and byte signatures."""

    mime_type: str
    extension: str
    representation: str


@dataclass(frozen=True)
class SnapshotManifest:
    """Self-describing provenance for one current snapshot artifact."""

    source_url: str
    final_url: str
    mime_type: str
    sha256: str
    backend: str
    size_bytes: int
    captured_at: str
    artifact_name: str
    representation: str
    status_code: int | None = None
    schema_version: int = SNAPSHOT_MANIFEST_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SNAPSHOT_MANIFEST_SCHEMA,
            "schema_version": self.schema_version,
            "artifact_name": self.artifact_name,
            "backend": self.backend,
            "captured_at": self.captured_at,
            "final_url": self.final_url,
            "mime_type": self.mime_type,
            "representation": self.representation,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "source_url": self.source_url,
            "status_code": self.status_code,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SnapshotManifest":
        if not isinstance(value, dict):
            raise ValueError("snapshot manifest must be an object")
        if value.get("schema") != SNAPSHOT_MANIFEST_SCHEMA:
            raise ValueError("snapshot manifest schema is not supported")
        if value.get("schema_version") != SNAPSHOT_MANIFEST_VERSION:
            raise ValueError("snapshot manifest version is not supported")
        artifact_name = str(value.get("artifact_name") or "")
        if not artifact_name or Path(artifact_name).name != artifact_name:
            raise ValueError("snapshot manifest artifact name is unsafe")
        digest = str(value.get("sha256") or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("snapshot manifest digest is invalid")
        size = value.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError("snapshot manifest size is invalid")
        mime_type = _normalize_mime(value.get("mime_type"))
        if not mime_type:
            raise ValueError("snapshot manifest MIME type is missing")
        representation = str(value.get("representation") or "")
        if representation not in {"bundled-html", "binary"}:
            raise ValueError("snapshot manifest representation is invalid")
        backend = str(value.get("backend") or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", backend):
            raise ValueError("snapshot manifest backend is invalid")
        captured_at = str(value.get("captured_at") or "")
        try:
            datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("snapshot manifest timestamp is invalid") from exc
        status = value.get("status_code")
        if status is not None:
            if (
                not isinstance(status, int)
                or isinstance(status, bool)
                or not 100 <= status <= 599
            ):
                raise ValueError("snapshot manifest status code is invalid")
        return cls(
            source_url=str(value.get("source_url") or ""),
            final_url=str(value.get("final_url") or ""),
            mime_type=mime_type,
            sha256=digest,
            backend=backend,
            size_bytes=size,
            captured_at=captured_at,
            artifact_name=artifact_name,
            representation=representation,
            status_code=status,
        )


def _normalize_mime(value: object) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def classify_snapshot_payload(
    payload: bytes,
    declared_mime: object = "",
) -> tuple[SnapshotFormat | None, str]:
    """Validate final response bytes and choose a safe representation."""
    if not payload:
        return None, "response body is empty"
    declared = _normalize_mime(declared_mime)
    binary_format: SnapshotFormat | None = None
    compatible_mimes: set[str] = set()
    if (
        len(payload) >= 32
        and payload.startswith(b"%PDF-")
        and b"%%EOF" in payload[-2048:]
    ):
        binary_format = SnapshotFormat("application/pdf", ".pdf", "binary")
        compatible_mimes = {"application/pdf"}
    elif (
        len(payload) >= 33
        and payload.startswith(b"\x89PNG\r\n\x1a\n")
        and payload[12:16] == b"IHDR"
        and payload.endswith(b"IEND\xaeB`\x82")
    ):
        binary_format = SnapshotFormat("image/png", ".png", "binary")
        compatible_mimes = {"image/png"}
    elif (
        len(payload) >= 11
        and payload.startswith(b"\xff\xd8\xff")
        and payload.endswith(b"\xff\xd9")
    ):
        binary_format = SnapshotFormat("image/jpeg", ".jpg", "binary")
        compatible_mimes = {"image/jpeg", "image/jpg"}
    elif (
        len(payload) >= 14
        and payload.startswith((b"GIF87a", b"GIF89a"))
        and payload.endswith(b";")
    ):
        binary_format = SnapshotFormat("image/gif", ".gif", "binary")
        compatible_mimes = {"image/gif"}
    elif (
        len(payload) >= 20
        and payload.startswith(b"RIFF")
        and payload[8:12] == b"WEBP"
        and int.from_bytes(payload[4:8], "little") == len(payload) - 8
        and payload[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
    ):
        binary_format = SnapshotFormat("image/webp", ".webp", "binary")
        compatible_mimes = {"image/webp"}
    if binary_format is not None:
        if declared not in compatible_mimes | _GENERIC_MIME_TYPES:
            return None, (
                f"declared MIME {declared or 'missing'} conflicts with "
                f"{binary_format.mime_type} bytes"
            )
        return binary_format, ""

    prefix = payload[:4096].lstrip(b"\xef\xbb\xbf\t\r\n ")
    looks_like_html = b"\x00" not in prefix and _HTML_PREFIX_RE.search(prefix) is not None
    if looks_like_html:
        if declared not in _HTML_MIME_TYPES | _GENERIC_MIME_TYPES:
            return None, (
                f"declared MIME {declared or 'missing'} conflicts with HTML bytes"
            )
        return SnapshotFormat("text/html", ".html", "bundled-html"), ""
    if declared in _HTML_MIME_TYPES:
        return None, "declared HTML response does not contain recognizable HTML"
    if declared:
        return None, f"unsupported response content type: {declared}"
    return None, "response content type is missing and byte signature is unsupported"


def snapshot_manifest_path(artifact_path: str | Path) -> Path:
    artifact = Path(artifact_path)
    return artifact.with_name(f"{artifact.stem}.snapshot.json")


def _write_snapshot_manifest(
    artifact_path: Path,
    manifest: SnapshotManifest,
) -> Path:
    path = snapshot_manifest_path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


def load_snapshot_manifest(
    artifact_path: str | Path,
    *,
    verify_artifact: bool = True,
) -> SnapshotManifest:
    artifact = Path(artifact_path)
    manifest = SnapshotManifest.from_dict(
        json.loads(snapshot_manifest_path(artifact).read_text(encoding="utf-8"))
    )
    if manifest.artifact_name != artifact.name:
        raise ValueError("snapshot manifest does not describe this artifact")
    if verify_artifact:
        payload = artifact.read_bytes()
        if len(payload) != manifest.size_bytes:
            raise ValueError("snapshot artifact size does not match its manifest")
        if hashlib.sha256(payload).hexdigest() != manifest.sha256:
            raise ValueError("snapshot artifact digest does not match its manifest")
        detected, error = classify_snapshot_payload(payload, manifest.mime_type)
        if detected is None:
            raise ValueError(error)
        if (
            detected.extension != artifact.suffix.lower()
            or detected.representation != manifest.representation
        ):
            raise ValueError("snapshot artifact format does not match its manifest")
    return manifest


def ensure_snapshot_manifest(bookmark: Bookmark) -> SnapshotManifest:
    """Load a current manifest or migrate a valid legacy snapshot in place."""
    artifact = Path(str(bookmark.snapshot_path or ""))
    if not artifact.is_file():
        raise FileNotFoundError("snapshot artifact is unavailable")
    manifest_path = snapshot_manifest_path(artifact)
    if manifest_path.is_file():
        manifest = load_snapshot_manifest(artifact)
    else:
        payload = artifact.read_bytes()
        declared = bookmark.snapshot_mime_type
        if not declared and artifact.suffix.lower() == ".html":
            declared = "text/html"
        detected, error = classify_snapshot_payload(payload, declared)
        if detected is None or detected.extension != artifact.suffix.lower():
            raise ValueError(error or "legacy snapshot extension is unsafe")
        captured_at = bookmark.snapshot_at
        try:
            datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError:
            captured_at = ""
        if not captured_at:
            captured_at = datetime.fromtimestamp(
                artifact.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()
        manifest = SnapshotManifest(
            source_url=bookmark.url,
            final_url=bookmark.url,
            mime_type=detected.mime_type,
            sha256=hashlib.sha256(payload).hexdigest(),
            backend=(
                bookmark.snapshot_backend
                if re.fullmatch(
                    r"[a-z0-9][a-z0-9-]{0,39}",
                    bookmark.snapshot_backend,
                )
                else "legacy"
            ),
            size_bytes=len(payload),
            captured_at=captured_at,
            artifact_name=artifact.name,
            representation=detected.representation,
        )
        _write_snapshot_manifest(artifact, manifest)
    bookmark.snapshot_size = manifest.size_bytes
    bookmark.snapshot_at = manifest.captured_at
    bookmark.snapshot_mime_type = manifest.mime_type
    bookmark.snapshot_sha256 = manifest.sha256
    bookmark.snapshot_backend = manifest.backend
    return manifest


def open_snapshot_file(
    bookmark: Bookmark,
    *,
    opener=None,
) -> tuple[bool, str]:
    """Verify and open a local snapshot without treating it as a remote URL."""
    try:
        manifest = ensure_snapshot_manifest(bookmark)
        artifact = Path(bookmark.snapshot_path).resolve(strict=True)
        if artifact.name != manifest.artifact_name:
            return False, "Snapshot manifest path mismatch"
        launch = opener or webbrowser.open
        if not launch(artifact.as_uri()):
            return False, "The operating system did not open the offline copy"
        return True, str(artifact)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, f"Offline copy could not be verified: {exc}"


def _browser_resource_diagnostics(summary: dict | None) -> dict[str, object]:
    """Return a compact, non-sensitive extension capture diagnostic summary."""
    source = summary if isinstance(summary, dict) else {}

    def bounded_int(name: str, maximum: int) -> int:
        try:
            return min(maximum, max(0, int(source.get(name, 0) or 0)))
        except (TypeError, ValueError):
            return 0

    reasons: dict[str, int] = {}
    raw_reasons = source.get("omitted_by_reason")
    if isinstance(raw_reasons, dict):
        for raw_name, raw_count in list(raw_reasons.items())[:20]:
            name = str(raw_name).strip().lower()
            if not re.fullmatch(r"[a-z0-9_-]{1,40}", name):
                continue
            try:
                count = min(10_000, max(0, int(raw_count)))
            except (TypeError, ValueError):
                continue
            if count:
                reasons[name] = count
    return {
        "count": bounded_int("count", 10_000),
        "inlined": bounded_int("inlined", 10_000),
        "inlined_bytes": bounded_int("inlined_bytes", 5_000_000),
        "omitted": bounded_int("omitted", 10_000),
        "omitted_by_reason": reasons,
    }


def _has_binary(name: str) -> bool:
    return shutil.which(name) is not None


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


@dataclass(frozen=True)
class SnapshotEgressPolicy:
    """Shared network and resource limits for every snapshot backend."""

    max_redirects: int = 5
    max_bytes: int = 25_000_000
    request_timeout_seconds: float = 15.0
    backend_timeout_seconds: float = 120.0
    allow_unsafe_external_backends: bool = False

    @classmethod
    def from_environment(cls) -> "SnapshotEgressPolicy":
        opt_in = os.environ.get("BOOKMARK_SNAPSHOT_ALLOW_UNSAFE_EXTERNAL", "")
        return cls(allow_unsafe_external_backends=opt_in.strip().lower() in {
            "1", "true", "yes", "on",
        })

    @staticmethod
    def check_url(url: str) -> tuple[bool, str]:
        return URLUtilities.check_safe_url(url)


@dataclass(frozen=True)
class SnapshotBackendAttempt:
    backend: str
    ok: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "ok": self.ok,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotBackendAttempt":
        return cls(
            backend=str(data.get("backend") or "unknown"),
            ok=bool(data.get("ok")),
            message=str(data.get("message") or ""),
        )


@dataclass(frozen=True)
class SnapshotFailureRecord:
    bookmark_id: int | None
    url: str
    title: str
    failed_at: str
    error: str
    retry_eligible: bool
    attempts: Tuple[SnapshotBackendAttempt, ...]

    @property
    def key(self) -> str:
        if self.bookmark_id is not None:
            return f"id:{self.bookmark_id}"
        return f"url:{self.url}"

    def to_dict(self) -> dict:
        return {
            "bookmark_id": self.bookmark_id,
            "url": self.url,
            "title": self.title,
            "failed_at": self.failed_at,
            "error": self.error,
            "retry_eligible": self.retry_eligible,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotFailureRecord":
        bookmark_id = data.get("bookmark_id")
        try:
            bookmark_id = int(bookmark_id) if bookmark_id is not None else None
        except (TypeError, ValueError):
            bookmark_id = None
        attempts = tuple(
            SnapshotBackendAttempt.from_dict(item)
            for item in data.get("attempts", [])
            if isinstance(item, dict)
        )
        return cls(
            bookmark_id=bookmark_id,
            url=str(data.get("url") or ""),
            title=str(data.get("title") or ""),
            failed_at=str(data.get("failed_at") or ""),
            error=str(data.get("error") or ""),
            retry_eligible=bool(data.get("retry_eligible", True)),
            attempts=attempts,
        )


class SnapshotFailureStore:
    """Persist recoverable snapshot failures as a compact JSON sidecar."""

    def __init__(self, path: Path = SNAPSHOT_FAILURES_FILE):
        self.path = Path(path)

    def list_failures(self) -> list[SnapshotFailureRecord]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not load snapshot failure report: %s", exc)
            return []
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = payload.get("failures", [])
        else:
            records = []
        if not isinstance(records, list):
            return []
        out = [
            SnapshotFailureRecord.from_dict(item)
            for item in records
            if isinstance(item, dict)
        ]
        return sorted(out, key=lambda item: item.failed_at, reverse=True)

    def get_for_bookmark(self, bookmark: Bookmark) -> SnapshotFailureRecord | None:
        key = self._key_for(bookmark)
        return next((record for record in self.list_failures() if record.key == key), None)

    def record_failure(
        self,
        bookmark: Bookmark,
        error: str,
        attempts: Iterable[SnapshotBackendAttempt],
        retry_eligible: bool = True,
    ) -> SnapshotFailureRecord:
        record = SnapshotFailureRecord(
            bookmark_id=int(bookmark.id) if bookmark.id is not None else None,
            url=bookmark.url or "",
            title=bookmark.title or bookmark.url or "",
            failed_at=datetime.now().isoformat(),
            error=error,
            retry_eligible=retry_eligible,
            attempts=tuple(attempts),
        )
        records = [item for item in self.list_failures() if item.key != record.key]
        records.append(record)
        self._write(records)
        return record

    def clear_for_bookmark(self, bookmark: Bookmark) -> bool:
        key = self._key_for(bookmark)
        records = self.list_failures()
        kept = [item for item in records if item.key != key]
        if len(kept) == len(records):
            return False
        self._write(kept)
        return True

    def clear_all(self) -> int:
        records = self.list_failures()
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError as exc:
                log.warning("Could not clear snapshot failure report: %s", exc)
                return 0
        return len(records)

    def _write(self, records: list[SnapshotFailureRecord]) -> None:
        if not records:
            if self.path.exists():
                try:
                    self.path.unlink()
                except OSError as exc:
                    log.warning("Could not remove empty snapshot failure report: %s", exc)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now().isoformat(),
            "failures": [record.to_dict() for record in sorted(records, key=lambda item: item.key)],
        }
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    @staticmethod
    def _key_for(bookmark: Bookmark) -> str:
        if bookmark.id is not None:
            return f"id:{int(bookmark.id)}"
        return f"url:{bookmark.url or ''}"


class SnapshotArchiver:
    """Capture a validated HTML or allowlisted binary snapshot of a page."""

    MAX_BYTES = 25_000_000  # 25MB hard ceiling per snapshot
    MAX_BROWSER_CAPTURE_BYTES = 5_000_000

    def __init__(
        self,
        snapshots_dir: Path = SNAPSHOTS_DIR,
        failure_store: SnapshotFailureStore | None = None,
        egress_policy: SnapshotEgressPolicy | None = None,
        job_ledger: JobLedger | None = None,
        history_store: SnapshotHistoryStore | None = None,
        max_history_versions: int = 10,
    ):
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.failure_store = failure_store or SnapshotFailureStore()
        self.egress_policy = egress_policy or SnapshotEgressPolicy.from_environment()
        self.job_ledger = job_ledger or JobLedger()
        self.history_store = history_store or SnapshotHistoryStore(
            self.snapshots_dir, max_versions=max_history_versions,
        )
        self._last_provenance: dict = {}

    # --- public API ---------------------------------------------------------

    def snapshot(self, bookmark: Bookmark) -> Tuple[bool, str]:
        """Capture and persist a snapshot. Returns (success, path_or_error)."""
        job = self.job_ledger.start(
            "snapshot", bookmark_id=bookmark.id, url_or_domain=bookmark.url,
        )
        allowed, reason = self.egress_policy.check_url(bookmark.url)
        if not allowed:
            self.failure_store.record_failure(
                bookmark,
                f"Private or unsupported URL: {reason}",
                (),
                retry_eligible=False,
            )
            job.fail(reason, retryable=False)
            return False, f"Private or unsupported URL: {reason}"
        attempts: list[SnapshotBackendAttempt] = []
        for backend in (self._snapshot_monolith, self._snapshot_singlefile,
                        self._snapshot_playwright, self._snapshot_python):
            backend_name = self._backend_label(backend.__name__)
            self._last_provenance = {"resolved_url": bookmark.url, "status_code": None}
            staging_path = self._staging_path(bookmark, backend_name)
            try:
                ok, msg = backend(bookmark.url, staging_path)
            except Exception as exc:
                log.debug(f"Snapshot backend {backend.__name__} crashed: {exc}")
                attempts.append(SnapshotBackendAttempt(backend_name, False, f"crashed: {exc}"))
                self._cleanup_staging(staging_path)
                continue
            if not ok:
                attempts.append(SnapshotBackendAttempt(backend_name, False, str(msg)))
                self._cleanup_staging(staging_path)
                continue
            try:
                artifact_path = self._backend_artifact_path(staging_path)
                if artifact_path is None:
                    raise ValueError("backend reported success without an artifact")
                out_path, manifest = self._commit_capture(
                    bookmark,
                    artifact_path,
                    source_url=bookmark.url,
                    backend=backend_name,
                )
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                attempts.append(
                    SnapshotBackendAttempt(
                        backend_name,
                        False,
                        f"artifact rejected: {exc}",
                    )
                )
                self._cleanup_staging(staging_path)
                continue
            attempts.append(SnapshotBackendAttempt(backend_name, True, str(out_path)))
            self._cleanup_staging(staging_path)
            self.failure_store.clear_for_bookmark(bookmark)
            job.succeed(bytes_processed=manifest.size_bytes, backend=backend_name)
            return True, str(out_path)
        details = "; ".join(f"{attempt.backend}: {attempt.message}" for attempt in attempts)
        error = "All snapshot backends failed"
        if details:
            error = f"{error}: {details}"
        self.failure_store.record_failure(bookmark, error, attempts, retry_eligible=True)
        job.fail(error, retryable=True, backend=attempts[-1].backend if attempts else "")
        return False, error

    def archive(self, bookmark: Bookmark) -> Tuple[bool, str]:
        """Compatibility alias for snapshot()."""
        return self.snapshot(bookmark)

    def _safe_snapshot_id(self, bookmark: Bookmark) -> str:
        if bookmark.id is not None:
            return str(int(bookmark.id))
        return f"url-{hashlib.sha256(bookmark.url.encode('utf-8')).hexdigest()[:16]}"

    def _staging_path(self, bookmark: Bookmark, backend: str) -> Path:
        safe_backend = re.sub(r"[^a-z0-9-]+", "-", backend.lower()).strip("-")
        token = secrets.token_hex(8)
        return self.snapshots_dir / (
            f".{self._safe_snapshot_id(bookmark)}.{safe_backend or 'backend'}.{token}.html"
        )

    @staticmethod
    def _staging_candidates(staging_path: Path) -> list[Path]:
        return [
            staging_path.with_suffix(extension)
            for extension in sorted(_CURRENT_SNAPSHOT_EXTENSIONS)
        ]

    def _cleanup_staging(self, staging_path: Path) -> None:
        for candidate in self._staging_candidates(staging_path):
            try:
                candidate.unlink(missing_ok=True)
            except OSError as exc:
                log.warning("Could not remove staged snapshot %s: %s", candidate, exc)

    def _backend_artifact_path(self, staging_path: Path) -> Path | None:
        declared = self._last_provenance.get("artifact_path")
        if declared:
            candidate = Path(str(declared))
            if (
                candidate.parent.resolve() == self.snapshots_dir.resolve()
                and candidate.stem == staging_path.stem
                and candidate.suffix.lower() in _CURRENT_SNAPSHOT_EXTENSIONS
                and candidate.is_file()
            ):
                return candidate
        return next(
            (
                candidate
                for candidate in self._staging_candidates(staging_path)
                if candidate.is_file()
            ),
            None,
        )

    def _commit_capture(
        self,
        bookmark: Bookmark,
        staged_path: Path,
        *,
        source_url: str,
        backend: str,
        captured_at: str = "",
    ) -> tuple[Path, SnapshotManifest]:
        payload = staged_path.read_bytes()
        detected, error = classify_snapshot_payload(
            payload,
            self._last_provenance.get("mime_type", ""),
        )
        if detected is None:
            raise ValueError(error)
        safe_id = self._safe_snapshot_id(bookmark)
        final_path = self.snapshots_dir / f"{safe_id}{detected.extension}"
        captured = captured_at or datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(payload).hexdigest()
        status = self._last_provenance.get("status_code")
        try:
            status_code = int(status) if status is not None else None
        except (TypeError, ValueError):
            status_code = None
        if status_code is not None and not 100 <= status_code <= 599:
            status_code = None
        manifest = SnapshotManifest(
            source_url=source_url,
            final_url=str(
                self._last_provenance.get("resolved_url") or source_url
            ),
            mime_type=detected.mime_type,
            sha256=digest,
            backend=backend,
            size_bytes=len(payload),
            captured_at=captured,
            artifact_name=final_path.name,
            representation=detected.representation,
            status_code=status_code,
        )
        previous_path = Path(bookmark.snapshot_path) if bookmark.snapshot_path else None
        manifest_path = snapshot_manifest_path(final_path)
        rollback_token = secrets.token_hex(8)
        artifact_backup = final_path.with_name(
            f".{final_path.name}.{rollback_token}.rollback"
        )
        manifest_backup = manifest_path.with_name(
            f".{manifest_path.name}.{rollback_token}.rollback"
        )
        if final_path.is_file():
            shutil.copyfile(final_path, artifact_backup)
        if manifest_path.is_file():
            shutil.copyfile(manifest_path, manifest_backup)
        try:
            os.replace(staged_path, final_path)
            _write_snapshot_manifest(final_path, manifest)
            self.history_store.record(
                bookmark.id,
                final_path,
                source_url=source_url,
                resolved_url=manifest.final_url,
                status_code=status_code,
                backend=backend,
                captured_at=captured,
                mime_type=manifest.mime_type,
                representation=manifest.representation,
            )
        except Exception:
            if artifact_backup.is_file():
                os.replace(artifact_backup, final_path)
            else:
                final_path.unlink(missing_ok=True)
            if manifest_backup.is_file():
                os.replace(manifest_backup, manifest_path)
            else:
                manifest_path.unlink(missing_ok=True)
            raise
        finally:
            for backup in (artifact_backup, manifest_backup):
                try:
                    backup.unlink(missing_ok=True)
                except OSError as exc:
                    log.warning("Could not remove snapshot rollback file %s: %s", backup, exc)
        for extension in _CURRENT_SNAPSHOT_EXTENSIONS:
            stale = self.snapshots_dir / f"{safe_id}{extension}"
            if stale != final_path:
                try:
                    stale.unlink(missing_ok=True)
                except OSError as exc:
                    log.warning("Could not remove superseded snapshot %s: %s", stale, exc)
        if previous_path is not None and previous_path != final_path:
            try:
                if previous_path.resolve().parent == self.snapshots_dir.resolve():
                    previous_path.unlink(missing_ok=True)
            except OSError:
                pass
        bookmark.snapshot_path = str(final_path)
        bookmark.snapshot_size = manifest.size_bytes
        bookmark.snapshot_at = manifest.captured_at
        bookmark.snapshot_mime_type = manifest.mime_type
        bookmark.snapshot_sha256 = manifest.sha256
        bookmark.snapshot_backend = manifest.backend
        bookmark.modified_at = manifest.captured_at
        return final_path, manifest

    def import_browser_snapshot(
        self,
        bookmark: Bookmark,
        html: str,
        *,
        source_url: str,
        selection: str = "",
        resource_summary: dict | None = None,
    ) -> dict:
        """Sanitize and atomically persist DOM captured by the browser extension.

        Browser cookies, storage, and request headers are deliberately not part of
        this contract. The stored document is inert and cannot fetch remote assets.
        """
        encoded = str(html or "").encode("utf-8")
        if not encoded:
            raise ValueError("Snapshot HTML is empty")
        if len(encoded) > self.MAX_BROWSER_CAPTURE_BYTES:
            raise ValueError("Snapshot HTML exceeds the 5 MB limit")
        source_parts = urlsplit(source_url)
        bookmark_parts = urlsplit(bookmark.url)
        if (
            source_parts.scheme.lower(), source_parts.netloc.lower()
        ) != (
            bookmark_parts.scheme.lower(), bookmark_parts.netloc.lower()
        ):
            raise ValueError("Snapshot source origin does not match the bookmark URL")

        bs4 = _try_import("bs4")
        if bs4 is None:
            raise RuntimeError("BeautifulSoup is required to sanitize browser snapshots")
        soup = bs4.BeautifulSoup(html, "html.parser")
        removed_elements = 0
        removed_attributes = 0

        for element in list(soup.find_all((
            "script", "iframe", "frame", "frameset", "object", "embed", "applet",
            "portal", "base", "meta", "link", "form", "input", "button", "select",
            "textarea",
        ))):
            element.decompose()
            removed_elements += 1

        remote_attr_names = {
            "src", "srcset", "poster", "background", "action", "formaction", "ping",
        }
        dangerous_attr_names = {"srcdoc", "nonce", "integrity", "crossorigin"}
        for element in soup.find_all(True):
            for name, value in list(element.attrs.items()):
                lower_name = str(name).lower()
                rendered = " ".join(value) if isinstance(value, list) else str(value or "")
                lowered = rendered.strip().lower()
                remove = (
                    lower_name.startswith("on")
                    or lower_name in dangerous_attr_names
                    or lower_name == "srcset"
                    or (lower_name in remote_attr_names and not lowered.startswith("data:"))
                    or (
                        lower_name in remote_attr_names
                        and lowered.startswith("data:")
                        and not _SAFE_CAPTURE_DATA_URI.fullmatch(rendered.strip())
                    )
                    or (lower_name.endswith("href") and element.name != "a" and not lowered.startswith("data:"))
                    or (lower_name == "href" and lowered.startswith(("javascript:", "data:", "file:", "blob:")))
                )
                if remove:
                    del element.attrs[name]
                    removed_attributes += 1
            if element.name == "a" and element.get("href"):
                element["rel"] = "noopener noreferrer"
                element["referrerpolicy"] = "no-referrer"

        css_import = re.compile(r"@import\s+[^;]+;?", re.IGNORECASE)
        css_url = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)

        def sanitize_css(value: str) -> str:
            without_imports = css_import.sub("", value)
            without_image_sets = re.sub(
                r"(?:-webkit-)?image-set\([^)]*\)",
                "none",
                without_imports,
                flags=re.IGNORECASE,
            )

            def replace_url(match: re.Match) -> str:
                target = match.group(2).strip()
                if target.startswith("data:") and _SAFE_CAPTURE_DATA_URI.fullmatch(target):
                    return match.group(0)
                return "none"

            return css_url.sub(replace_url, without_image_sets)

        for style in soup.find_all("style"):
            original = style.string or style.get_text()
            cleaned = sanitize_css(original)
            if cleaned != original:
                removed_attributes += 1
            style.string = cleaned
        for element in soup.find_all(style=True):
            original = str(element.get("style") or "")
            cleaned = sanitize_css(original)
            if cleaned != original:
                removed_attributes += 1
            element["style"] = cleaned

        if soup.html is None:
            wrapper = bs4.BeautifulSoup("<!doctype html><html><head></head><body></body></html>", "html.parser")
            wrapper.body.append(soup)
            soup = wrapper
        if soup.head is None:
            soup.html.insert(0, soup.new_tag("head"))
        csp = soup.new_tag("meta")
        csp["http-equiv"] = "Content-Security-Policy"
        csp["content"] = (
            "default-src 'none'; img-src data:; style-src 'unsafe-inline' data:; "
            "font-src data:; media-src data:; form-action 'none'; frame-src 'none'"
        )
        soup.head.insert(0, csp)
        if soup.body is None:
            soup.html.append(soup.new_tag("body"))
        disclosure = soup.new_tag("aside")
        disclosure["role"] = "note"
        disclosure["style"] = (
            "padding:12px;margin:0;background:#111827;color:#f9fafb;"
            "font:14px/1.4 system-ui,sans-serif"
        )
        selection_note = f" Selection: {html_lib.escape(selection[:500])}" if selection else ""
        disclosure.append(bs4.BeautifulSoup(
            "Browser capture from " + html_lib.escape(source_url) +
            ". Bounded same-origin assets were embedded; active content and remaining remote resources "
            "were removed; cookies were never transferred." +
            selection_note,
            "html.parser",
        ))
        soup.body.insert(0, disclosure)

        rendered = str(soup).encode("utf-8")
        if len(rendered) > self.MAX_BROWSER_CAPTURE_BYTES:
            raise ValueError("Sanitized snapshot exceeds the 5 MB limit")
        staging_path = self._staging_path(bookmark, "browser-extension")
        try:
            with staging_path.open("xb") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            staging_path.unlink(missing_ok=True)
            raise

        resources = _browser_resource_diagnostics(resource_summary)
        raw_summary = resource_summary if isinstance(resource_summary, dict) else {}
        raw_status = raw_summary.get("status_code")
        try:
            status_code = int(raw_status) if raw_status is not None else None
        except (TypeError, ValueError):
            status_code = None
        self._last_provenance = {
            "artifact_path": str(staging_path),
            "mime_type": "text/html",
            "resolved_url": str(raw_summary.get("resolved_url") or source_url),
            "status_code": status_code,
        }
        now = datetime.now(timezone.utc).isoformat()
        try:
            out_path, manifest = self._commit_capture(
                bookmark,
                staging_path,
                source_url=source_url,
                backend="browser-extension",
                captured_at=now,
            )
        finally:
            self._cleanup_staging(staging_path)
        return {
            "stored": True,
            "path": str(out_path),
            "size": manifest.size_bytes,
            "mime_type": manifest.mime_type,
            "sha256": manifest.sha256,
            "removed_elements": removed_elements,
            "removed_attributes": removed_attributes,
            "resource_count": resources["count"],
            "resources": resources,
            "disclosure": (
                "Bounded same-origin assets embedded; active content and remaining remote resources "
                "removed; cookies were never transferred."
            ),
        }

    def delete_snapshot(self, bookmark: Bookmark) -> bool:
        try:
            safe_id = self._safe_snapshot_id(bookmark)
            for extension in _CURRENT_SNAPSHOT_EXTENSIONS:
                (self.snapshots_dir / f"{safe_id}{extension}").unlink(missing_ok=True)
            snapshot_manifest_path(self.snapshots_dir / f"{safe_id}.html").unlink(
                missing_ok=True
            )
            if bookmark.snapshot_path:
                current = Path(bookmark.snapshot_path)
                if current.parent.resolve() == self.snapshots_dir.resolve():
                    current.unlink(missing_ok=True)
            bookmark.snapshot_path = ""
            bookmark.snapshot_size = 0
            bookmark.snapshot_at = ""
            bookmark.snapshot_mime_type = ""
            bookmark.snapshot_sha256 = ""
            bookmark.snapshot_backend = ""
            return True
        except OSError as exc:
            log.warning(f"Could not delete snapshot: {exc}")
            return False

    def has_snapshot(self, bookmark: Bookmark) -> bool:
        if not bookmark.snapshot_path:
            return False
        try:
            ensure_snapshot_manifest(bookmark)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return True

    @staticmethod
    def _backend_label(method_name: str) -> str:
        return method_name.replace("_snapshot_", "").replace("_", "-")

    # --- backends -----------------------------------------------------------

    def _snapshot_monolith(self, url: str, out_path: Path) -> Tuple[bool, str]:
        if not _has_binary("monolith"):
            return False, "monolith not installed"
        if not self.egress_policy.allow_unsafe_external_backends:
            return False, (
                "monolith disabled: cannot enforce snapshot egress policy; set "
                "BOOKMARK_SNAPSHOT_ALLOW_UNSAFE_EXTERNAL=1 to opt in"
            )
        try:
            subprocess.run(
                ["monolith", "--isolate", "--silent",
                 "--no-audio", "--no-video",
                 "-o", str(out_path), "--", url],
                check=True, timeout=self.egress_policy.backend_timeout_seconds,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return False, f"monolith failed: {exc}"
        if not out_path.exists() or out_path.stat().st_size == 0:
            return False, "monolith produced no output"
        if out_path.stat().st_size > self.egress_policy.max_bytes:
            out_path.unlink(missing_ok=True)
            return False, "snapshot too large"
        return True, str(out_path)

    def _snapshot_singlefile(self, url: str, out_path: Path) -> Tuple[bool, str]:
        cli = None
        for cand in ("single-file", "single-file.exe"):
            if _has_binary(cand):
                cli = cand
                break
        if cli is None:
            return False, "single-file CLI not installed"
        if not self.egress_policy.allow_unsafe_external_backends:
            return False, (
                "single-file disabled: cannot enforce snapshot egress policy; set "
                "BOOKMARK_SNAPSHOT_ALLOW_UNSAFE_EXTERNAL=1 to opt in"
            )
        try:
            subprocess.run(
                [cli, "--", url, str(out_path)],
                check=True, timeout=self.egress_policy.backend_timeout_seconds,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return False, f"single-file failed: {exc}"
        if not out_path.exists() or out_path.stat().st_size == 0:
            return False, "single-file produced no output"
        if out_path.stat().st_size > self.egress_policy.max_bytes:
            out_path.unlink(missing_ok=True)
            return False, "snapshot too large"
        return True, str(out_path)

    def _snapshot_playwright(self, url: str, out_path: Path) -> Tuple[bool, str]:
        """Headless Chromium via playwright — captures JS-rendered SPAs."""
        pw_sync = _try_import("playwright.sync_api")
        if pw_sync is None:
            return False, "playwright not installed"
        deadline = time.monotonic() + self.egress_policy.backend_timeout_seconds
        violations: list[str] = []
        transferred_bytes = 0

        def _redirect_count(request) -> int:
            count = 0
            previous = getattr(request, "redirected_from", None)
            while previous is not None:
                count += 1
                previous = getattr(previous, "redirected_from", None)
            return count

        def _route_request(route, request) -> None:
            nonlocal transferred_bytes
            allowed, reason = self.egress_policy.check_url(request.url)
            if not allowed:
                violations.append(f"blocked {request.url}: {reason}")
                route.abort("blockedbyclient")
                return
            if _redirect_count(request) > self.egress_policy.max_redirects:
                violations.append(f"redirect limit exceeded for {request.url}")
                route.abort("blockedbyclient")
                return
            remaining_ms = int(max(0, deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                violations.append("snapshot time limit exceeded")
                route.abort("timedout")
                return
            try:
                response = route.fetch(max_redirects=0, timeout=remaining_ms)
                body = response.body()
            except Exception as exc:
                violations.append(f"request failed for {request.url}: {exc}")
                route.abort("failed")
                return
            transferred_bytes += len(body)
            if len(body) > self.egress_policy.max_bytes:
                violations.append(f"resource byte limit exceeded for {request.url}")
                route.abort("blockedbyclient")
                return
            if transferred_bytes > self.egress_policy.max_bytes:
                violations.append("snapshot byte limit exceeded")
                route.abort("blockedbyclient")
                return
            route.fulfill(response=response, body=body)

        try:
            with pw_sync.sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(service_workers="block")
                    page = context.new_page()
                    page.route("**/*", _route_request)
                    navigation = page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=int(self.egress_policy.backend_timeout_seconds * 1000),
                    )
                    if violations:
                        return False, violations[0]
                    self._last_provenance = {
                        "resolved_url": page.url,
                        "status_code": navigation.status if navigation is not None else None,
                        "mime_type": "text/html",
                    }
                    content = page.content()
                finally:
                    browser.close()
            if not content or len(content) < 100:
                return False, "playwright produced empty page"
            data = content.encode("utf-8")
            if len(data) > self.egress_policy.max_bytes:
                return False, "snapshot too large"
            out_path.write_bytes(data)
            self._last_provenance["artifact_path"] = str(out_path)
            return True, str(out_path)
        except Exception as exc:
            return False, f"playwright failed: {exc}"

    def _snapshot_python(self, url: str, out_path: Path) -> Tuple[bool, str]:
        """Pure-Python fallback: inline CSS, images, and basic fonts."""
        from bookmark_organizer_pro.services.egress import public_egress as requests

        bs4 = _try_import("bs4")
        if bs4 is None:
            return False, "requests/bs4 not available"
        deadline = time.monotonic() + self.egress_policy.backend_timeout_seconds
        resp, current_url, error = self._fetch_response(
            requests, url, deadline, self.egress_policy.max_bytes,
        )
        if resp is None:
            return False, f"fetch failed: {error}"
        try:
            raw = self._read_bounded(resp, self.egress_policy.max_bytes)
            if raw is None:
                return False, "snapshot too large"
            declared_mime = resp.headers.get("content-type", "")
            response_encoding = resp.encoding or "utf-8"
        finally:
            resp.close()
        detected, error = classify_snapshot_payload(raw, declared_mime)
        if detected is None:
            return False, error
        self._last_provenance = {
            "resolved_url": current_url,
            "status_code": getattr(resp, "status_code", None),
            "mime_type": detected.mime_type,
        }
        if detected.representation == "binary":
            artifact_path = out_path.with_suffix(detected.extension)
            try:
                artifact_path.write_bytes(raw)
            except OSError as exc:
                return False, f"write failed: {exc}"
            self._last_provenance["artifact_path"] = str(artifact_path)
            return True, str(artifact_path)

        html = raw.decode(response_encoding, errors="replace")

        soup = bs4.BeautifulSoup(html, "html.parser")
        base = current_url

        # Inline external stylesheets
        for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
            href = link.get("href")
            if not href:
                continue
            css_url = urljoin(base, href)
            css = self._fetch_text(requests, css_url, deadline)
            if css is None:
                continue
            style = soup.new_tag("style")
            style.string = css
            link.replace_with(style)

        # Inline images
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src or src.startswith("data:"):
                continue
            data_url = self._fetch_data_url(requests, urljoin(base, src), deadline)
            if data_url:
                img["src"] = data_url

        # Strip scripts (snapshot is a static record)
        for tag in soup.find_all("script"):
            tag.decompose()

        import html as _html
        safe_url = _html.escape(url, quote=True)
        banner_html = (
            f'<div style="background:#1a1a2e;color:#eee;padding:8px 16px;'
            f'font:12px/1.4 system-ui;position:sticky;top:0;z-index:99999;">'
            f'Snapshot of <a style="color:#58a6ff" href="{safe_url}">{safe_url}</a> '
            f'on {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>'
        )
        if soup.body:
            soup.body.insert(0, bs4.BeautifulSoup(banner_html, "html.parser"))

        try:
            data = str(soup).encode("utf-8")
            if len(data) > self.egress_policy.max_bytes:
                return False, "snapshot too large"
            out_path.write_bytes(data)
            self._last_provenance["artifact_path"] = str(out_path)
        except OSError as exc:
            return False, f"write failed: {exc}"
        return True, str(out_path)

    _MAX_TEXT_BYTES = 2_000_000

    def _fetch_response(self, requests, url: str, deadline: float, max_bytes: int):
        """Fetch one URL with bounded, policy-checked redirects."""
        current_url = url
        try:
            for redirect_count in range(self.egress_policy.max_redirects + 1):
                allowed, reason = self.egress_policy.check_url(current_url)
                if not allowed:
                    return None, current_url, reason
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, current_url, "snapshot time limit exceeded"
                response = requests.get(
                    current_url,
                    headers={"User-Agent": "Mozilla/5.0 (BookmarkOrganizerPro/6.0)"},
                    timeout=min(self.egress_policy.request_timeout_seconds, remaining),
                    stream=True,
                    allow_redirects=False,
                )
                if response.status_code not in (301, 302, 303, 307, 308):
                    response.raise_for_status()
                    try:
                        content_len = int(response.headers.get("content-length", 0) or 0)
                    except (TypeError, ValueError):
                        content_len = 0
                    if content_len > max_bytes:
                        response.close()
                        return None, current_url, "response byte limit exceeded"
                    return response, current_url, ""
                location = response.headers.get("Location", "")
                response.close()
                if not location:
                    return None, current_url, "redirect with no Location header"
                if redirect_count >= self.egress_policy.max_redirects:
                    return None, current_url, "redirect limit exceeded"
                current_url = urljoin(current_url, location)
        except Exception as exc:
            return None, current_url, str(exc)
        return None, current_url, "redirect limit exceeded"

    @staticmethod
    def _read_bounded(response, max_bytes: int) -> bytes | None:
        chunks = bytearray()
        for chunk in response.iter_content(chunk_size=65_536):
            if not chunk:
                continue
            chunks.extend(chunk)
            if len(chunks) > max_bytes:
                return None
        return bytes(chunks)

    def _fetch_text(self, requests, url: str, deadline: float | None = None) -> Optional[str]:
        deadline = deadline or (time.monotonic() + self.egress_policy.backend_timeout_seconds)
        response, _final_url, _error = self._fetch_response(
            requests, url, deadline, self._MAX_TEXT_BYTES,
        )
        if response is None:
            return None
        try:
            data = self._read_bounded(response, self._MAX_TEXT_BYTES)
            if data is None:
                return None
            return data.decode(response.encoding or "utf-8", errors="replace")
        finally:
            response.close()

    def _fetch_data_url(self, requests, url: str, deadline: float | None = None) -> Optional[str]:
        deadline = deadline or (time.monotonic() + self.egress_policy.backend_timeout_seconds)
        response, _final_url, _error = self._fetch_response(
            requests, url, deadline, self._MAX_TEXT_BYTES,
        )
        if response is None:
            return None
        try:
            data = self._read_bounded(response, self._MAX_TEXT_BYTES)
            if data is None:
                return None
            mime = response.headers.get(
                "content-type", "application/octet-stream",
            ).split(";")[0].strip()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
        finally:
            response.close()
