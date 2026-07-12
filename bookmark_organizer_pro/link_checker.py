"""Background link checker with threading, redirect detection, and per-domain rate limiting."""

import importlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from .constants import APP_VERSION
from .models import Bookmark
from .url_utils import URLUtilities

_USER_AGENT = f"BookmarkOrganizerPro/{APP_VERSION} LinkChecker"


class LinkChecker:
    """Background link checker with threading and per-domain rate limiting."""

    def __init__(self, callback: Callable = None, max_workers: int = 10,
                 job_ledger=None):
        from .services.job_ledger import JobLedger

        self.callback = callback
        try:
            self.max_workers = max(1, min(32, int(max_workers)))
        except (TypeError, ValueError):
            self.max_workers = 10
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False
        self._checked = 0
        self._total = 0
        self._lock = threading.Lock()
        self._domain_locks: Dict[str, threading.Lock] = {}
        self._domain_last_request: Dict[str, float] = {}
        self.job_ledger = job_ledger or JobLedger()

    def check_links(self, bookmarks: List[Bookmark],
                   progress_callback: Callable = None):
        """Start checking links in background"""
        if self._running:
            return

        bookmarks = list(bookmarks or [])
        self._running = True
        self._checked = 0
        self._total = len(bookmarks)
        self._domain_locks.clear()
        self._domain_last_request.clear()

        thread = threading.Thread(
            target=self._worker,
            args=(bookmarks, progress_callback),
            daemon=True
        )
        thread.start()

    def _worker(self, bookmarks: List[Bookmark], progress_callback: Callable):
        """Worker thread"""
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                self._executor = executor
                futures = {
                    executor.submit(self._check_url, bm): bm
                    for bm in bookmarks
                }

                for future in as_completed(futures):
                    if not self._running:
                        break

                    bookmark = futures[future]
                    with self._lock:
                        try:
                            is_valid, status_code = future.result()
                            bookmark.is_valid = is_valid
                            bookmark.http_status = status_code
                            bookmark.last_checked = datetime.now().isoformat()
                        except Exception:
                            bookmark.is_valid = False
                            bookmark.http_status = 0
                        self._checked += 1
                        checked = self._checked
                        total = self._total
                    if progress_callback:
                        progress_callback(checked, total, bookmark)
        finally:
            self._running = False
            self._executor = None
            if self.callback:
                self.callback()

    def _rate_limit(self, url: str):
        """Per-domain rate limiting: max 1 request/second/domain."""
        try:
            domain = urlparse(url).hostname or ""
        except Exception:
            domain = ""
        if not domain:
            return
        # setdefault is atomic in CPython, avoiding the defaultdict race
        lock = self._domain_locks.setdefault(domain, threading.Lock())
        with lock:
            last = self._domain_last_request.get(domain, 0)
            elapsed = time.monotonic() - last
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            self._domain_last_request[domain] = time.monotonic()

    def _check_url(self, bookmark: Bookmark) -> Tuple[bool, int]:
        job = self.job_ledger.start(
            "link_check", bookmark_id=bookmark.id,
            url_or_domain=bookmark.url, backend="requests",
        )
        valid, status = self._perform_check_url(bookmark)
        if status:
            job.succeed()
        else:
            job.fail("Link check did not receive an HTTP response", retryable=True)
        return valid, status

    def _perform_check_url(self, bookmark: Bookmark) -> Tuple[bool, int]:
        """Check a single URL. Detects redirects; returns (is_valid, status_code).
        Redirect metadata is stored on bookmark.custom_data under the lock."""
        try:
            requests = importlib.import_module('requests')
            headers = {'User-Agent': _USER_AGENT}
            current_url = bookmark.url
            redirects = []
            response = None

            seen_urls = {current_url}
            for _ in range(6):
                if not URLUtilities._is_safe_url(current_url):
                    return False, 0

                self._rate_limit(current_url)

                response = requests.head(
                    current_url, timeout=10,
                    allow_redirects=False, headers=headers,
                )

                if response.status_code in (405, 403):
                    response.close()
                    self._rate_limit(current_url)
                    response = requests.get(
                        current_url, timeout=10,
                        allow_redirects=False, stream=True, headers=headers,
                    )

                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('Location', '')
                    response.close()
                    if not location:
                        break
                    next_url = urljoin(current_url, location)
                    if next_url in seen_urls:
                        break
                    if not URLUtilities._is_safe_url(next_url):
                        return False, 0
                    seen_urls.add(next_url)
                    redirects.append(next_url)
                    current_url = next_url
                    continue
                break

            status_code = response.status_code if response is not None else 0
            if response is not None:
                response.close()

            if status_code in (301, 302, 303, 307, 308):
                return False, status_code

            with self._lock:
                if redirects and current_url != bookmark.url:
                    bookmark.custom_data['redirect_url'] = current_url
                    bookmark.custom_data['redirect_count'] = len(redirects)
                    bookmark.custom_data['redirect_chain'] = ' -> '.join(redirects[:5])
                elif 'redirect_url' in bookmark.custom_data:
                    bookmark.custom_data.pop('redirect_url', None)
                    bookmark.custom_data.pop('redirect_count', None)
                    bookmark.custom_data.pop('redirect_chain', None)

            return status_code < 400, status_code
        except Exception as e:
            exc_type = type(e).__name__
            if 'Timeout' in exc_type:
                return False, 408
            elif 'SSLError' in exc_type:
                return False, 495
            elif 'ConnectionError' in exc_type:
                return False, 0
            return False, 0

    def get_redirected_bookmarks(self, bookmarks: List[Bookmark]) -> List[Tuple[Bookmark, str]]:
        """Get bookmarks that have been redirected to a new URL."""
        return [(bm, bm.custom_data['redirect_url'])
                for bm in bookmarks
                if 'redirect_url' in bm.custom_data]

    @staticmethod
    def fix_redirect(bookmark: Bookmark) -> bool:
        """Update a bookmark's URL to its redirect destination."""
        new_url = bookmark.custom_data.get('redirect_url')
        if not new_url:
            return False
        bookmark.url = new_url
        bookmark.custom_data.pop('redirect_url', None)
        bookmark.custom_data.pop('redirect_count', None)
        bookmark.custom_data.pop('redirect_chain', None)
        bookmark.modified_at = datetime.now().isoformat()
        return True

    def stop(self):
        """Stop the checker"""
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=False)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def progress(self) -> Tuple[int, int]:
        return self._checked, self._total
