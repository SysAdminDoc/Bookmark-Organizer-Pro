"""Background link checker with threading and redirect detection."""

import importlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from .models import Bookmark


class LinkChecker:
    """Background link checker with threading"""

    def __init__(self, callback: Callable = None, max_workers: int = 10):
        self.callback = callback
        self.max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running = False
        self._checked = 0
        self._total = 0
        self._lock = threading.Lock()

    def check_links(self, bookmarks: List[Bookmark],
                   progress_callback: Callable = None):
        """Start checking links in background"""
        if self._running:
            return

        self._running = True
        self._checked = 0
        self._total = len(bookmarks)

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
                        if progress_callback:
                            progress_callback(self._checked, self._total, bookmark)
        finally:
            self._running = False
            self._executor = None
            if self.callback:
                self.callback()

    def _check_url(self, bookmark: Bookmark) -> Tuple[bool, int]:
        """Check a single URL. Detects redirects and stores final URL."""
        try:
            requests = importlib.import_module('requests')
            response = requests.head(
                bookmark.url,
                timeout=10,
                allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )

            if response.history and response.url != bookmark.url:
                bookmark.custom_data['redirect_url'] = response.url
                bookmark.custom_data['redirect_count'] = len(response.history)
                bookmark.custom_data['redirect_chain'] = (
                    ' -> '.join(r.url for r in response.history[:5])
                )
            elif 'redirect_url' in bookmark.custom_data:
                bookmark.custom_data.pop('redirect_url', None)
                bookmark.custom_data.pop('redirect_count', None)
                bookmark.custom_data.pop('redirect_chain', None)

            return response.status_code < 400, response.status_code
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
