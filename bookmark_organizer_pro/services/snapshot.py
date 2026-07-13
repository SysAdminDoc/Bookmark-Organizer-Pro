"""Single-file HTML snapshot archiver.

Produces a self-contained HTML snapshot per bookmark. Prefers the `monolith`
Rust binary when available (best fidelity, embeds all assets); falls back to
SingleFile-CLI (Node), then to a built-in BeautifulSoup-based bundler that
inlines stylesheets, images, and fonts as data URIs.

Stored under SNAPSHOTS_DIR/{id}.html. Records snapshot metadata back onto
the Bookmark.
"""

from __future__ import annotations

import base64
import html as html_lib
import importlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
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
    """Capture a self-contained HTML snapshot of a page."""

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
        out_path = self.snapshots_dir / f"{bookmark.id}.html"
        attempts: list[SnapshotBackendAttempt] = []
        for backend in (self._snapshot_monolith, self._snapshot_singlefile,
                        self._snapshot_playwright, self._snapshot_python):
            backend_name = self._backend_label(backend.__name__)
            self._last_provenance = {"resolved_url": bookmark.url, "status_code": None}
            try:
                ok, msg = backend(bookmark.url, out_path)
            except Exception as exc:
                log.debug(f"Snapshot backend {backend.__name__} crashed: {exc}")
                attempts.append(SnapshotBackendAttempt(backend_name, False, f"crashed: {exc}"))
                continue
            attempts.append(SnapshotBackendAttempt(backend_name, ok, str(msg)))
            if ok:
                size = out_path.stat().st_size if out_path.exists() else 0
                bookmark.snapshot_path = str(out_path)
                bookmark.snapshot_size = size
                bookmark.snapshot_at = datetime.now().isoformat()
                bookmark.modified_at = bookmark.snapshot_at
                self.history_store.record(
                    bookmark.id,
                    out_path,
                    source_url=bookmark.url,
                    resolved_url=str(self._last_provenance.get("resolved_url") or bookmark.url),
                    status_code=self._last_provenance.get("status_code"),
                    backend=backend_name,
                    captured_at=bookmark.snapshot_at,
                )
                self.failure_store.clear_for_bookmark(bookmark)
                job.succeed(bytes_processed=size, backend=backend_name)
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
        out_path = self.snapshots_dir / f"{bookmark.id}.html"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{bookmark.id}.", suffix=".tmp", dir=self.snapshots_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, out_path)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise

        now = datetime.now().isoformat()
        bookmark.snapshot_path = str(out_path)
        bookmark.snapshot_size = len(rendered)
        bookmark.snapshot_at = now
        bookmark.modified_at = now
        resources = _browser_resource_diagnostics(resource_summary)
        raw_summary = resource_summary if isinstance(resource_summary, dict) else {}
        raw_status = raw_summary.get("status_code")
        try:
            status_code = int(raw_status) if raw_status is not None else None
        except (TypeError, ValueError):
            status_code = None
        self.history_store.record(
            bookmark.id,
            out_path,
            source_url=source_url,
            resolved_url=str(raw_summary.get("resolved_url") or source_url),
            status_code=status_code,
            backend="browser-extension",
            captured_at=now,
        )
        return {
            "stored": True,
            "path": str(out_path),
            "size": len(rendered),
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
        path = self.snapshots_dir / f"{bookmark.id}.html"
        try:
            if path.exists():
                path.unlink()
            bookmark.snapshot_path = ""
            bookmark.snapshot_size = 0
            bookmark.snapshot_at = ""
            return True
        except OSError as exc:
            log.warning(f"Could not delete snapshot: {exc}")
            return False

    def has_snapshot(self, bookmark: Bookmark) -> bool:
        if not bookmark.snapshot_path:
            return False
        return Path(bookmark.snapshot_path).exists()

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
        self._last_provenance = {
            "resolved_url": current_url,
            "status_code": getattr(resp, "status_code", None),
        }
        try:
            raw = self._read_bounded(resp, self.egress_policy.max_bytes)
            if raw is None:
                return False, "snapshot too large"
            html = raw.decode(resp.encoding or "utf-8", errors="replace")
        finally:
            resp.close()

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
