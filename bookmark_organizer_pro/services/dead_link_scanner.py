"""Scheduled dead-link scanner.

Periodically scans bookmarks for HTTP errors / dropped DNS / redirects, and
records findings to a JSON queue (`dead_links.json`). Runs in a daemon
thread; designed for desktop use without polluting the UI thread.

Only LinkAce among self-hosted competitors ships scheduled link monitoring;
this module brings BOP up to parity.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from bookmark_organizer_pro.constants import DEAD_LINKS_FILE
from bookmark_organizer_pro.link_checker import LinkChecker
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


@dataclass
class DeadLinkRecord:
    bookmark_id: int
    url: str
    status: int
    error: str
    redirect_to: str = ""
    detected_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanProgress:
    total: int = 0
    done: int = 0
    broken: int = 0
    redirected: int = 0
    rate_limited: int = 0
    cached: int = 0


# A server asking us to slow down is not a dead link. Reporting 429/503 as
# broken is how a large library produces a page of false positives.
RATE_LIMIT_STATUSES = frozenset({429, 503})

MAX_RATE_LIMIT_RETRIES = 2
MAX_BACKOFF_SECONDS = 30.0


def _default_sleep(seconds: float) -> None:
    import time as _time

    _time.sleep(max(0.0, float(seconds)))


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        return (urlsplit(str(url)).hostname or "").lower()
    except ValueError:
        return ""


def _retry_after_seconds(raw: str, attempt: int) -> float:
    """Seconds to wait, from a Retry-After header or exponential backoff."""
    text = str(raw or "").strip()
    if text:
        try:
            return max(0.0, min(MAX_BACKOFF_SECONDS, float(text)))
        except ValueError:
            try:
                from email.utils import parsedate_to_datetime

                target = parsedate_to_datetime(text)
                if target is not None:
                    if target.tzinfo is not None:
                        from datetime import timezone as _tz

                        delta = (target - datetime.now(_tz.utc)).total_seconds()
                    else:
                        delta = (target - datetime.now()).total_seconds()
                    return max(0.0, min(MAX_BACKOFF_SECONDS, delta))
            except (TypeError, ValueError):
                pass
    return min(MAX_BACKOFF_SECONDS, 2.0 ** attempt)


class _HostGate:
    """Caps concurrent requests per host and holds a per-host backoff clock."""

    def __init__(self, per_host: int = 2):
        self.per_host = max(1, int(per_host))
        self._lock = threading.Lock()
        self._slots: Dict[str, threading.Semaphore] = {}
        self._ready_at: Dict[str, float] = {}

    def _slot(self, host: str) -> threading.Semaphore:
        with self._lock:
            if host not in self._slots:
                self._slots[host] = threading.Semaphore(self.per_host)
            return self._slots[host]

    def penalize(self, host: str, seconds: float) -> None:
        import time as _time

        with self._lock:
            self._ready_at[host] = max(self._ready_at.get(host, 0.0), _time.monotonic() + seconds)

    def acquire(self, host: str, sleep: Callable[[float], None]) -> threading.Semaphore:
        import time as _time

        slot = self._slot(host)
        slot.acquire()
        while True:
            with self._lock:
                wait = self._ready_at.get(host, 0.0) - _time.monotonic()
            if wait <= 0:
                return slot
            sleep(min(wait, MAX_BACKOFF_SECONDS))


class DeadLinkScanner:
    """Background dead-link scanner with persistent results queue."""

    def __init__(self, get_bookmarks: Callable[[], Iterable[Bookmark]],
                 results_file: Path = DEAD_LINKS_FILE,
                 max_workers: int = 8,
                 per_host_workers: int = 2,
                 sleep: Optional[Callable[[float], None]] = None):
        self.get_bookmarks = get_bookmarks
        self.results_file = Path(results_file)
        self.checker = LinkChecker(callback=None, max_workers=max_workers)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_scan: Optional[datetime] = None
        self._progress = ScanProgress()
        self._gate = _HostGate(per_host_workers)
        # Injectable so tests exercise backoff without real delays.
        self._sleep = sleep or _default_sleep
        self._verdicts: Dict[str, dict] = {}
        self._results: Dict[str, dict] = {
            record.url: record.to_dict() for record in self._load_records()
        }

    def _check_with_backoff(self, bm: Bookmark):
        """Check one URL, pausing for hosts that ask us to slow down.

        Returns (is_valid, status_code, rate_limited).
        """
        host = _host_of(bm.url)
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            slot = self._gate.acquire(host, self._sleep)
            try:
                is_valid, status_code = self.checker._check_url(bm)
            finally:
                slot.release()
            if status_code not in RATE_LIMIT_STATUSES:
                return is_valid, status_code, False
            delay = _retry_after_seconds(bm.custom_data.get("retry_after", ""), attempt)
            self._gate.penalize(host, delay)
            if attempt >= MAX_RATE_LIMIT_RETRIES or self._stop.is_set():
                break
            self._sleep(delay)
        return False, status_code, True

    # ---- single scan -------------------------------------------------------
    def scan_now(self, progress_callback: Optional[Callable[[ScanProgress], None]] = None,
                 only_unchecked_for_hours: int = 0,
                 cache_ttl_hours: float = 0) -> List[DeadLinkRecord]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        bookmarks = list(self.get_bookmarks())
        if only_unchecked_for_hours > 0:
            cutoff = datetime.now() - timedelta(hours=only_unchecked_for_hours)
            bookmarks = [
                b for b in bookmarks
                if not b.last_checked or _isoparse(b.last_checked) < cutoff
            ]

        cached_hits = 0
        if cache_ttl_hours > 0:
            fresh_after = datetime.now() - timedelta(hours=cache_ttl_hours)
            pending = []
            for bookmark in bookmarks:
                verdict = self._verdicts.get(bookmark.url)
                if verdict and _isoparse(str(verdict.get("checked_at", ""))) >= fresh_after:
                    bookmark.is_valid = bool(verdict.get("is_valid"))
                    bookmark.http_status = int(verdict.get("status") or 0)
                    cached_hits += 1
                    continue
                pending.append(bookmark)
            bookmarks = pending
        records: List[DeadLinkRecord] = []
        progress = ScanProgress(total=len(bookmarks), cached=cached_hits)
        with self._lock:
            self._progress = progress

        if not bookmarks:
            self._persist(records)
            return records

        now = datetime.now().isoformat()
        with ThreadPoolExecutor(max_workers=self.checker.max_workers) as ex:
            futures = {ex.submit(self._check_with_backoff, bm): bm for bm in bookmarks}
            for fut in as_completed(futures):
                bm = futures[fut]
                rate_limited = False
                try:
                    is_valid, status_code, rate_limited = fut.result()
                except Exception as exc:
                    is_valid, status_code = False, 0
                    log.debug(f"check failed for {bm.url}: {exc}")
                with self._lock:
                    bm.last_checked = now
                    bm.is_valid = is_valid
                    bm.http_status = status_code
                    redirect = str(bm.custom_data.get("redirect_url", "") or "")
                    if not rate_limited:
                        self._verdicts[bm.url] = {
                            "is_valid": is_valid, "status": status_code, "checked_at": now,
                        }
                progress.done += 1
                if rate_limited:
                    # Unknown, not dead: the host never gave us an answer.
                    progress.rate_limited += 1
                    records.append(DeadLinkRecord(
                        bookmark_id=bm.id, url=bm.url, status=status_code,
                        error="rate-limited", redirect_to=redirect,
                        detected_at=now,
                    ))
                elif not is_valid:
                    progress.broken += 1
                    records.append(DeadLinkRecord(
                        bookmark_id=bm.id, url=bm.url, status=status_code,
                        error=f"HTTP {status_code}", redirect_to=redirect,
                        detected_at=now,
                    ))
                elif redirect and redirect != bm.url:
                    progress.redirected += 1
                    records.append(DeadLinkRecord(
                        bookmark_id=bm.id, url=bm.url, status=status_code,
                        error="redirect", redirect_to=redirect,
                        detected_at=now,
                    ))
                if progress_callback:
                    try:
                        progress_callback(progress)
                    except Exception:
                        pass

        with self._lock:
            self._last_scan = datetime.now()
        self._persist(records)
        if progress_callback:
            try:
                progress_callback(progress)
            except Exception:
                pass
        return records

    # ---- background loop ---------------------------------------------------
    def start(self, interval_hours: int = 24):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, args=(interval_hours,),
            name="DeadLinkScanner", daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self, interval_hours: int):
        wait_seconds = max(60, interval_hours * 3600)
        # First-pass after a short delay so app startup isn't slammed
        if self._stop.wait(timeout=120):
            return
        while not self._stop.is_set():
            try:
                self.scan_now(only_unchecked_for_hours=interval_hours)
            except Exception as exc:
                log.warning(f"Dead-link scan failed: {exc}")
            if self._stop.wait(timeout=wait_seconds):
                break

    # ---- persistence -------------------------------------------------------
    def _persist(self, records: Iterable[DeadLinkRecord]):
        existing = self._load_records()
        # Merge by bookmark_id (latest wins)
        merged = {r.bookmark_id: r for r in existing}
        for r in records:
            merged[r.bookmark_id] = r
        merged_records = list(merged.values())
        import tempfile, os
        try:
            fd, tmp = tempfile.mkstemp(
                dir=self.results_file.parent, suffix=".tmp", text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump([r.to_dict() for r in merged_records], f, indent=2)
                os.replace(tmp, self.results_file)
                self._results = {r.url: r.to_dict() for r in merged_records}
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise
        except OSError as exc:
            log.warning(f"Could not persist dead-link records: {exc}")

    def _save_results(self):
        """Compatibility persistence for callers that still populate _results."""
        records: List[DeadLinkRecord] = []
        for value in self._results.values():
            if isinstance(value, DeadLinkRecord):
                records.append(value)
                continue
            if not isinstance(value, dict) or "bookmark_id" not in value:
                continue
            try:
                records.append(DeadLinkRecord(
                    bookmark_id=int(value.get("bookmark_id")),
                    url=str(value.get("url", "")),
                    status=int(value.get("status", 0) or 0),
                    error=str(value.get("error", "")),
                    redirect_to=str(value.get("redirect_to", "")),
                    detected_at=str(value.get("detected_at") or value.get("checked_at") or ""),
                ))
            except (TypeError, ValueError):
                continue
        self._persist(records)

    def _load_records(self) -> List[DeadLinkRecord]:
        if not self.results_file.exists():
            return []
        try:
            data = json.loads(self.results_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        out = []
        for d in data if isinstance(data, list) else []:
            try:
                out.append(DeadLinkRecord(**d))
            except TypeError:
                continue
        return out

    def list_dead_links(self) -> List[DeadLinkRecord]:
        return self._load_records()

    def clear(self):
        try:
            if self.results_file.exists():
                self.results_file.unlink()
        except OSError:
            pass

    @property
    def last_scan(self) -> Optional[datetime]:
        return self._last_scan


def _isoparse(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.min
