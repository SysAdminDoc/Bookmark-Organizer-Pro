"""Dead-link scanning must be polite: cap per-host concurrency, honour
Retry-After, and never report a rate-limited host as dead."""

from __future__ import annotations

import argparse
import contextlib
import shutil
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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

    def test_a_cancelled_scan_stops_early_and_keeps_finished_verdicts(self):
        bookmarks = [_bookmark(i, f"https://host{i}.test/page") for i in range(8)]
        server = _FakeServer({b.url: [200] for b in bookmarks})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, _slept = _scanner(bookmarks, server, tmp, max_workers=1)
            # Cancel only after the first result has been applied.
            scanner.scan_now(should_cancel=lambda: scanner._progress.done >= 1)

        self.assertLess(scanner._progress.done, len(bookmarks))
        self.assertGreaterEqual(scanner._progress.done, 1)
        checked = [b for b in bookmarks if b.last_checked]
        self.assertTrue(
            checked, "a cancelled scan must keep the verdicts it already had",
        )
        for bookmark in checked:
            self.assertEqual(bookmark.http_status, 200)
        self.assertIsNone(
            scanner._last_scan,
            "a partial scan must not be recorded as a completed pass",
        )

    def test_cancelling_does_not_wait_out_a_long_retry_after(self):
        """The backoff used to sleep the full Retry-After before noticing, so
        cancelling a rate-limited scan froze the UI for minutes."""
        bookmarks = [_bookmark(i, f"https://slow.test/{i}") for i in range(6)]
        server = _FakeServer({b.url: [429] for b in bookmarks})

        with tempfile.TemporaryDirectory() as tmp:
            scanner, slept = _scanner(bookmarks, server, tmp, max_workers=2)
            scanner.scan_now(should_cancel=lambda: True)

        # Every sleep is a short poll slice, never a whole Retry-After.
        from bookmark_organizer_pro.services.dead_link_scanner import CANCEL_POLL_SECONDS

        self.assertTrue(
            all(delay <= CANCEL_POLL_SECONDS for delay in slept),
            f"cancelled scan slept in long blocks: {sorted(set(slept))[-5:]}",
        )

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


class _StubWidget:
    """Stands in for the Tk widgets the link-check status bar builds."""

    def __init__(self, *args, **kwargs):
        self.destroyed = False
        self.text = kwargs.get("text", "")

    def pack(self, *args, **kwargs):
        return None

    def pack_propagate(self, *args, **kwargs):
        return None

    def place(self, *args, **kwargs):
        return None

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = kwargs["text"]

    def destroy(self):
        self.destroyed = True


class _StubTheme:
    bg_dark = "#000000"
    bg_tertiary = "#111111"
    text_muted = "#888888"
    accent_primary = "#00ff00"
    accent_error = "#ff0000"


class _FakeApp:
    """The slice of the app coordinator that `_check_all_links` touches."""

    def __init__(self, manager):
        self.bookmark_manager = manager
        self.root = object()
        self.status_bar = object()
        self.statuses = []
        self.toasts = []
        self.finished = threading.Event()

    def _set_status(self, message):
        self.statuses.append(message)

    def _toast(self, message, tone="info"):
        self.toasts.append((message, tone))

    def _show_toast(self, message, tone="info"):
        self.toasts.append((message, tone))

    def _post_to_ui(self, callback):
        callback()

    def _refresh_all(self):
        # `_finish` always refreshes, so this is the completion signal.
        self.finished.set()


class TestLinkCheckEntryPoints(unittest.TestCase):
    """`bop check` and the Tools menu must use the polite scanner.

    Both used to run their own bare HEAD loop that recorded a 429 as
    `is_valid=False`, which surfaces the bookmark as dead in
    `find_broken_links`, `is:broken`, the broken quick filter, and the
    dashboard Dead Links badge.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="bop_link_check_")
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

        from bookmark_organizer_pro.core.category_manager import CategoryManager
        from bookmark_organizer_pro.managers import BookmarkManager, TagManager

        root = Path(self._tmp)
        self.manager = BookmarkManager(
            CategoryManager(filepath=root / "categories.json"),
            TagManager(filepath=root / "tags.json"),
            filepath=root / "bookmarks.json",
        )
        self.limited = self.manager.add_bookmark_clean(
            url="https://limited.test/page", title="Rate limited", category="Testing",
        )
        self.healthy = self.manager.add_bookmark_clean(
            url="https://healthy.test/page", title="Healthy", category="Testing",
        )
        self.limited.is_valid = True
        self.healthy.is_valid = True

        self.server = _FakeServer({
            self.limited.url: [429],
            self.healthy.url: [200],
        })

    def _patched_scanner(self):
        """Route every scanner check at this server, without real backoff sleeps."""
        from bookmark_organizer_pro.link_checker import LinkChecker

        server = self.server
        results_file = Path(self._tmp) / "dead_links.json"

        # `results_file=DEAD_LINKS_FILE` is a default argument bound when the
        # class was defined, so patching the module constant would NOT redirect
        # it and the scan would write to the real user data directory. Wrap the
        # constructor instead.
        def scoped_scanner(*args, **kwargs):
            kwargs.setdefault("results_file", results_file)
            return DeadLinkScanner(*args, **kwargs)

        return [
            patch.object(LinkChecker, "_check_url", lambda _self, bm: server.check(bm)),
            patch(
                "bookmark_organizer_pro.services.dead_link_scanner._default_sleep",
                lambda _seconds: None,
            ),
            patch(
                "bookmark_organizer_pro.services.dead_link_scanner.DeadLinkScanner",
                scoped_scanner,
            ),
        ]

    def _assert_rate_limited_survived(self):
        # Prove the scan actually ran: without this, an entry point that
        # silently did nothing would satisfy every assertion below.
        self.assertEqual(
            sorted({self.limited.url, self.healthy.url}),
            sorted(set(self.server.calls)),
            "both bookmarks must have been checked",
        )
        self.assertEqual(self.healthy.http_status, 200)
        self.assertTrue(
            self.limited.is_valid,
            "a rate-limited host must not be recorded as a dead link",
        )
        self.assertIn("rate_limited_at", self.limited.custom_data)
        self.assertNotIn(
            self.limited.id,
            [bm.id for bm in self.manager.find_broken_links()],
            "a rate-limited bookmark must not surface as broken",
        )
        self.assertLessEqual(
            self.server.peak.get("limited.test", 0), 2,
            "per-host concurrency must stay capped",
        )

    def test_cli_check_leaves_rate_limited_links_alone(self):
        from bookmark_organizer_pro.cli import BookmarkCLI

        cli = BookmarkCLI.__new__(BookmarkCLI)
        cli.bookmark_manager = self.manager

        stdout = sys.stdout
        sys.stdout = captured = StringIO()
        try:
            with contextlib.ExitStack() as stack:
                for patcher in self._patched_scanner():
                    stack.enter_context(patcher)
                cli._cmd_check(argparse.Namespace())
        finally:
            sys.stdout = stdout

        output = captured.getvalue()
        self._assert_rate_limited_survived()
        self.assertIn("Found 0 broken links", output)
        self.assertIn("rate limited", output)

    def test_tools_menu_check_leaves_rate_limited_links_alone(self):
        from bookmark_organizer_pro.app_mixins import tools as tools_mixin

        app = _FakeApp(self.manager)

        with contextlib.ExitStack() as stack:
            for patcher in self._patched_scanner():
                stack.enter_context(patcher)
            stack.enter_context(patch.object(tools_mixin.tk, "Frame", _StubWidget))
            stack.enter_context(patch.object(tools_mixin.tk, "Label", _StubWidget))
            stack.enter_context(patch.object(tools_mixin, "get_theme", _StubTheme))
            stack.enter_context(
                patch.object(tools_mixin, "make_keyboard_activatable", lambda *a, **k: None)
            )
            stack.enter_context(patch.object(tools_mixin, "Tooltip", lambda *a, **k: None))
            tools_mixin.ToolsActionsMixin._check_all_links(app)
            self.assertTrue(app.finished.wait(timeout=30), "link check never finished")

        self._assert_rate_limited_survived()
        self.assertTrue(
            any("0 broken" in str(message) for message, _tone in app.toasts),
            f"expected a zero-broken summary, got {app.toasts}",
        )


if __name__ == "__main__":
    unittest.main()
