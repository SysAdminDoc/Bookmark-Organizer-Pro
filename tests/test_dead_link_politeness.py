"""Dead-link scanning must be polite: cap per-host concurrency, honour
Retry-After, and never report a rate-limited host as dead."""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.dead_link_scanner import (
    DeadLinkScanner,
    _retry_after_seconds,
)


class _FakeServer:
    """Records concurrency per host and replies with scripted statuses."""

    def __init__(self, script):
        self.script = dict(script)
        self.lock = threading.Lock()
        self.active = {}
        self.peak = {}
        self.calls = []

    def check(self, bookmark):
        from urllib.parse import urlsplit

        host = urlsplit(bookmark.url).hostname or ""
        with self.lock:
            self.active[host] = self.active.get(host, 0) + 1
            self.peak[host] = max(self.peak.get(host, 0), self.active[host])
            self.calls.append(bookmark.url)
            attempt = sum(1 for url in self.calls if url == bookmark.url)
        try:
            statuses = self.script.get(bookmark.url, [200])
            status = statuses[min(attempt - 1, len(statuses) - 1)]
            if status in (429, 503):
                bookmark.custom_data["retry_after"] = "1"
            else:
                bookmark.custom_data.pop("retry_after", None)
            return status < 400, status
        finally:
            with self.lock:
                self.active[host] -= 1


def _scanner(bookmarks, server, tmp, **kwargs):
    slept = []
    scanner = DeadLinkScanner(
        get_bookmarks=lambda: bookmarks,
        results_file=Path(tmp) / "dead_links.json",
        sleep=slept.append,
        **kwargs,
    )
    scanner.checker._check_url = server.check
    return scanner, slept


def _bookmark(index, url):
    return Bookmark(id=index, url=url, title=f"Bookmark {index}")


class TestDeadLinkPoliteness(unittest.TestCase):
    def test_rate_limited_hosts_are_not_reported_as_dead(self):
        bookmarks = [_bookmark(i, f"https://slow.test/{i}") for i in range(4)]
        server = _FakeServer({b.url: [429] for b in bookmarks})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, slept = _scanner(bookmarks, server, tmp)
            records = scanner.scan_now()

        self.assertEqual([r.error for r in records], ["rate-limited"] * 4)
        self.assertEqual(scanner._progress.broken, 0, "429 must not count as broken")
        self.assertEqual(scanner._progress.rate_limited, 4)
        self.assertTrue(slept, "the scanner must back off before retrying")

    def test_a_rate_limited_bookmark_is_not_marked_broken_in_the_library(self):
        """`is_valid` drives find_broken_links, `is:broken`, and the broken
        quick filter, so a host that never answered must not set it."""
        bookmark = _bookmark(1, "https://slow.test/page")
        bookmark.is_valid = True
        server = _FakeServer({bookmark.url: [429]})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner([bookmark], server, tmp)
            scanner.scan_now()

        self.assertTrue(bookmark.is_valid, "a rate-limited link must not be marked dead")
        self.assertIn("rate_limited_at", bookmark.custom_data)

    def test_a_cached_rescan_still_records_a_scan_time(self):
        bookmark = _bookmark(1, "https://cached.test/page")
        server = _FakeServer({bookmark.url: [200]})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner([bookmark], server, tmp)
            scanner.scan_now()
            first = scanner._last_scan
            scanner.scan_now(cache_ttl_hours=24)

        self.assertIsNotNone(scanner._last_scan)
        self.assertGreaterEqual(scanner._last_scan, first)

    def test_a_host_that_recovers_after_backoff_is_healthy(self):
        bookmark = _bookmark(1, "https://flaky.test/page")
        server = _FakeServer({bookmark.url: [429, 200]})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner([bookmark], server, tmp)
            records = scanner.scan_now()

        self.assertEqual(records, [])
        self.assertTrue(bookmark.is_valid)
        self.assertEqual(bookmark.http_status, 200)

    def test_real_failures_are_still_reported(self):
        gone = _bookmark(1, "https://gone.test/page")
        fine = _bookmark(2, "https://gone.test/ok")
        server = _FakeServer({gone.url: [404], fine.url: [200]})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner([gone, fine], server, tmp)
            records = scanner.scan_now()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].url, gone.url)
        self.assertEqual(records[0].error, "HTTP 404")

    def test_per_host_concurrency_is_capped(self):
        same_host = [_bookmark(i, f"https://busy.test/{i}") for i in range(12)]
        server = _FakeServer({b.url: [200] for b in same_host})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner(same_host, server, tmp, max_workers=8, per_host_workers=2)
            scanner.scan_now()

        self.assertLessEqual(server.peak.get("busy.test", 0), 2)

    def test_separate_hosts_still_run_in_parallel(self):
        spread = [_bookmark(i, f"https://host{i}.test/page") for i in range(6)]
        server = _FakeServer({b.url: [200] for b in spread})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner(spread, server, tmp, max_workers=6, per_host_workers=2)
            scanner.scan_now()

        self.assertEqual(len(server.calls), 6)
        for host, peak in server.peak.items():
            self.assertLessEqual(peak, 2, host)

    def test_cached_verdicts_skip_rechecking_within_the_ttl(self):
        bookmark = _bookmark(1, "https://cached.test/page")
        server = _FakeServer({bookmark.url: [200]})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner([bookmark], server, tmp)
            scanner.scan_now()
            self.assertEqual(len(server.calls), 1)

            scanner.scan_now(cache_ttl_hours=24)
            self.assertEqual(len(server.calls), 1, "a fresh verdict must not be rechecked")
            self.assertEqual(scanner._progress.cached, 1)

            # An expired verdict is checked again.
            scanner._verdicts[bookmark.url]["checked_at"] = (
                datetime.now() - timedelta(hours=48)
            ).isoformat()
            scanner.scan_now(cache_ttl_hours=24)
            self.assertEqual(len(server.calls), 2)

    def test_rate_limited_results_are_never_cached(self):
        bookmark = _bookmark(1, "https://limited.test/page")
        server = _FakeServer({bookmark.url: [429]})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner([bookmark], server, tmp)
            scanner.scan_now()
            self.assertNotIn(bookmark.url, scanner._verdicts)

    def test_retry_after_parsing(self):
        self.assertEqual(_retry_after_seconds("5", 0), 5.0)
        self.assertEqual(_retry_after_seconds("", 0), 1.0)
        self.assertEqual(_retry_after_seconds("", 3), 8.0)
        self.assertEqual(_retry_after_seconds("99999", 0), 30.0)
        self.assertEqual(_retry_after_seconds("not-a-date", 1), 2.0)
        # HTTP-date form
        future = datetime.now().astimezone() + timedelta(seconds=10)
        stamp = future.strftime("%a, %d %b %Y %H:%M:%S %z")
        self.assertGreater(_retry_after_seconds(stamp, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
