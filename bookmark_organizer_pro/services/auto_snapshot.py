"""Scheduled auto-snapshot service.

Users mark bookmarks for periodic re-capture to detect silent edits.
Runs as a background daemon thread, re-snapshots at configurable intervals.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark

SCHEDULE_FILE = DATA_DIR / "snapshot_schedule.json"


class SnapshotScheduler:
    """Background scheduler for periodic bookmark re-snapshots."""

    def __init__(self, snapshot_fn: Callable[[Bookmark], tuple],
                 get_bookmark_fn: Callable[[int], Optional[Bookmark]],
                 interval_hours: int = 24):
        self._snapshot_fn = snapshot_fn
        self._get_bookmark = get_bookmark_fn
        self._interval = interval_hours
        self._scheduled_ids: Set[int] = set()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._load()

    def _load(self):
        if not SCHEDULE_FILE.exists():
            return
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            with self._lock:
                self._scheduled_ids = set(data.get("bookmark_ids", []))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(f"Could not load snapshot schedule: {exc}")

    def _save(self):
        with self._lock:
            payload = {"bookmark_ids": sorted(self._scheduled_ids),
                       "interval_hours": self._interval}
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
        self._interval = max(1, hours)
        self._save()

    def run_once(self) -> Dict[str, int]:
        """Run one snapshot pass over all scheduled bookmarks. Returns stats."""
        with self._lock:
            ids = list(self._scheduled_ids)

        success = 0
        failed = 0
        skipped = 0

        for bm_id in ids:
            bm = self._get_bookmark(bm_id)
            if bm is None:
                skipped += 1
                continue
            if bm.snapshot_at:
                try:
                    last = datetime.fromisoformat(bm.snapshot_at.replace("Z", "+00:00"))
                    if (datetime.now() - last.replace(tzinfo=None)) < timedelta(hours=self._interval):
                        skipped += 1
                        continue
                except (ValueError, TypeError):
                    pass

            try:
                ok, msg = self._snapshot_fn(bm)
                if ok:
                    success += 1
                else:
                    failed += 1
                    log.debug(f"Auto-snapshot failed for {bm.url}: {msg}")
            except Exception as exc:
                failed += 1
                log.warning(f"Auto-snapshot error for {bm.url}: {exc}")

        return {"success": success, "failed": failed, "skipped": skipped, "total": len(ids)}

    def start(self):
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
        if self._stop.wait(timeout=300):
            return
        while not self._stop.is_set():
            try:
                stats = self.run_once()
                log.info(f"Auto-snapshot pass: {stats}")
            except Exception as exc:
                log.warning(f"Auto-snapshot pass failed: {exc}")
            if self._stop.wait(timeout=self._interval * 3600):
                break
