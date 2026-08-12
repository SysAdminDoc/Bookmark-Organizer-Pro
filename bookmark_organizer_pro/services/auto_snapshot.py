"""Scheduled auto-snapshot service.

Users mark bookmarks for periodic re-capture to detect silent edits.
Runs as a background daemon thread, re-snapshots at configurable intervals.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Set

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.snapshot import (
    SnapshotBackendAttempt,
    SnapshotFailureStore,
)

SCHEDULE_FILE = DATA_DIR / "snapshot_schedule.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class SnapshotScheduler:
    """Background scheduler for periodic bookmark re-snapshots."""

    def __init__(self, snapshot_fn: Callable[[Bookmark], tuple],
                 get_bookmark_fn: Callable[[int], Optional[Bookmark]],
                 interval_hours: int = 24,
                 failure_store: SnapshotFailureStore | None = None,
                 *,
                 clock: Callable[[], datetime] | None = None,
                 wait_fn: Callable[[float], bool] | None = None,
                 initial_delay_seconds: float = 300.0):
        self._snapshot_fn = snapshot_fn
        self._get_bookmark = get_bookmark_fn
        self._interval = self._bounded_interval(interval_hours)
        self._failure_store = failure_store or SnapshotFailureStore()
        self._scheduled_ids: Set[int] = set()
        self._lock = threading.RLock()
        self._pass_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._clock = clock or _utc_now
        self._wait = wait_fn or self._stop.wait
        self._initial_delay_seconds = max(0.0, min(86_400.0, float(initial_delay_seconds)))
        self._enabled = False
        self._load()

    @staticmethod
    def _bounded_interval(hours: int) -> int:
        try:
            return max(1, min(24 * 30, int(hours)))
        except (TypeError, ValueError):
            return 24

    def _load(self):
        if not SCHEDULE_FILE.exists():
            return
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("snapshot schedule must be an object")
            with self._lock:
                ids = data.get("bookmark_ids", [])
                loaded_ids = set()
                for bookmark_id in ids if isinstance(ids, list) else []:
                    try:
                        parsed_id = int(bookmark_id)
                    except (TypeError, ValueError):
                        continue
                    if parsed_id >= 0:
                        loaded_ids.add(parsed_id)
                self._scheduled_ids = loaded_ids
                if "interval_hours" in data:
                    self._interval = self._bounded_interval(data.get("interval_hours"))
                self._enabled = bool(data.get("enabled", False))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            log.warning(f"Could not load snapshot schedule: {exc}")

    def _save(self):
        with self._lock:
            payload = {"bookmark_ids": sorted(self._scheduled_ids),
                       "interval_hours": self._interval,
                       "enabled": self._enabled}
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=SCHEDULE_FILE.parent, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, SCHEDULE_FILE)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def add(self, bookmark_id: int):
        with self._lock:
            self._scheduled_ids.add(bookmark_id)
        self._save()

    def remove(self, bookmark_id: int):
        with self._lock:
            self._scheduled_ids.discard(bookmark_id)
        self._save()

    def list_scheduled(self) -> List[int]:
        with self._lock:
            return sorted(self._scheduled_ids)

    def is_scheduled(self, bookmark_id: int) -> bool:
        with self._lock:
            return bookmark_id in self._scheduled_ids

    @property
    def interval_hours(self) -> int:
        return self._interval

    def set_interval(self, hours: int):
        self._interval = self._bounded_interval(hours)
        self._save()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool):
        with self._lock:
            self._enabled = bool(enabled)
        self._save()

    def run_once(self, *, now: datetime | None = None) -> Dict[str, int]:
        """Run one snapshot pass over all scheduled bookmarks. Returns stats."""
        if not self._pass_lock.acquire(blocking=False):
            return {
                "success": 0, "failed": 0, "skipped": 0, "deferred": 0,
                "total": 0, "coalesced": 1,
            }
        try:
            return self._run_once(now=now)
        finally:
            self._pass_lock.release()

    def _run_once(self, *, now: datetime | None = None) -> Dict[str, int]:
        with self._lock:
            ids = list(self._scheduled_ids)

        success = 0
        failed = 0
        skipped = 0
        deferred = 0
        current = _as_utc(now or self._clock()) or _utc_now()

        for bm_id in ids:
            bm = self._get_bookmark(bm_id)
            if bm is None:
                skipped += 1
                continue

            failure = self._failure_store.get_for_bookmark(bm)
            if failure is not None:
                if not failure.retry_eligible:
                    skipped += 1
                    continue
                retry_at = _as_utc(failure.next_retry_at)
                if retry_at is not None and retry_at > current:
                    deferred += 1
                    skipped += 1
                    continue

            last = _as_utc(bm.snapshot_at)
            if last is not None and current - last < timedelta(hours=self._interval):
                skipped += 1
                continue

            try:
                ok, msg = self._snapshot_fn(bm)
                if ok:
                    success += 1
                    self._failure_store.clear_for_bookmark(bm)
                else:
                    failed += 1
                    self._record_failure(
                        bm,
                        str(msg),
                        previous=failure,
                    )
                    log.debug(f"Auto-snapshot failed for {bm.url}: {msg}")
            except Exception as exc:
                failed += 1
                self._record_failure(
                    bm,
                    f"Auto-snapshot error: {exc}",
                    previous=failure,
                )
                log.warning(f"Auto-snapshot error for {bm.url}: {exc}")

        return {
            "success": success, "failed": failed, "skipped": skipped,
            "deferred": deferred, "total": len(ids), "coalesced": 0,
        }

    def _record_failure(
        self,
        bookmark: Bookmark,
        error: str,
        *,
        previous,
    ) -> None:
        latest = self._failure_store.get_for_bookmark(bookmark)
        retry_eligible = latest.retry_eligible if latest is not None else True
        attempts = (
            latest.attempts
            if latest is not None and latest.attempts
            else (SnapshotBackendAttempt("auto-snapshot", False, str(error)),)
        )
        retry_count = (previous.retry_count if previous is not None else 0) + 1
        next_retry_at = ""
        if retry_eligible:
            delay = min(6 * 60 * 60, 5 * 60 * (2 ** min(retry_count - 1, 8)))
            next_retry_at = (
                _as_utc(self._clock()) or _utc_now()
            ) + timedelta(seconds=delay)
            next_retry_at = next_retry_at.isoformat()
        self._failure_store.record_failure(
            bookmark,
            str(latest.error if latest is not None and latest.error else error),
            attempts,
            retry_eligible=retry_eligible,
            retry_count=retry_count if retry_eligible else 0,
            next_retry_at=next_retry_at,
        )

    def start(self):
        if not self.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="AutoSnapshot", daemon=True)
        self._thread.start()
        log.info(f"Auto-snapshot scheduler started (interval: {self._interval}h)")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self):
        if self._wait(self._initial_delay_seconds):
            return
        while not self._stop.is_set():
            try:
                stats = self.run_once(now=self._clock())
                log.info(f"Auto-snapshot pass: {stats}")
            except Exception as exc:
                log.warning(f"Auto-snapshot pass failed: {exc}")
            if self._wait(self._interval * 3600):
                break
