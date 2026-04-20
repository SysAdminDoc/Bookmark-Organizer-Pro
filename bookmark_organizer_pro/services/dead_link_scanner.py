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
import time
from dataclasses import asdict, dataclass, field
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


class DeadLinkScanner:
    """Background dead-link scanner with persistent results queue."""

    def __init__(self, get_bookmarks: Callable[[], Iterable[Bookmark]],
                 results_file: Path = DEAD_LINKS_FILE,
                 max_workers: int = 8):
        self.get_bookmarks = get_bookmarks
        self.results_file = Path(results_file)
        self.checker = LinkChecker(callback=None, max_workers=max_workers)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_scan: Optional[datetime] = None
        self._progress = ScanProgress()

    # ---- single scan -------------------------------------------------------
    def scan_now(self, progress_callback: Optional[Callable[[ScanProgress], None]] = None,
                 only_unchecked_for_hours: int = 0) -> List[DeadLinkRecord]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        bookmarks = list(self.get_bookmarks())
        if only_unchecked_for_hours > 0:
            cutoff = datetime.now() - timedelta(hours=only_unchecked_for_hours)
            bookmarks = [
                b for b in bookmarks
                if not b.last_checked or _isoparse(b.last_checked) < cutoff
            ]
        records: List[DeadLinkRecord] = []
        progress = ScanProgress(total=len(bookmarks))
        with self._lock:
            self._progress = progress

        if not bookmarks:
            self._persist(records)
            return records

        now = datetime.now().isoformat()
        with ThreadPoolExecutor(max_workers=self.checker.max_workers) as ex:
            futures = {ex.submit(self.checker._check_url, bm): bm for bm in bookmarks}
            for fut in as_completed(futures):
                bm = futures[fut]
                try:
                    is_valid, status_code = fut.result()
                except Exception as exc:
                    is_valid, status_code = False, 0
                    log.debug(f"check failed for {bm.url}: {exc}")
                bm.last_checked = now
                bm.is_valid = is_valid
                bm.http_status = status_code
                progress.done += 1
                redirect = str(bm.custom_data.get("redirect_url", "") or "")
                if not is_valid:
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
        try:
            self.results_file.write_text(
                json.dumps([r.to_dict() for r in merged.values()], indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning(f"Could not persist dead-link records: {exc}")

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
