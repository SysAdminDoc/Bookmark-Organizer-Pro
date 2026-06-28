"""Core bookmark manager and import/export operations."""

from __future__ import annotations

import contextlib
import csv
import html as html_module
import json
import os
import tempfile
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - exercised when optional dependency is unavailable
    BeautifulSoup = None

from bookmark_organizer_pro.constants import APP_VERSION, MASTER_BOOKMARKS_FILE
from bookmark_organizer_pro.core import CategoryManager, SQLiteStorageManager, StorageManager
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.search import SearchEngine
from bookmark_organizer_pro.utils import (
    calculate_health_score,
    fetch_page_metadata,
    merge_duplicate_bookmarks,
    normalize_url,
    safe_int,
    validate_url,
    wayback_check,
    wayback_save,
)
from bookmark_organizer_pro.utils.runtime import csv_safe_cell as _csv_safe_cell

from .tags import TagManager


class BookmarkManager:
    """
        Central manager for all bookmark operations.
        
        Coordinates between storage, categories, tags, and search
        to provide a unified API for bookmark management.
        
        Attributes:
            bookmarks: Dict mapping IDs to Bookmark objects
            category_manager: CategoryManager instance
            tag_manager: TagManager instance
            storage: StorageManager instance
            search_engine: SearchEngine instance
            pattern_engine: PatternEngine instance
        
        Methods:
            add_bookmark(url, title, category, tags): Add new bookmark
            update_bookmark(id, **kwargs): Update bookmark
            delete_bookmark(id): Delete bookmark
            delete_bookmarks(ids): Bulk delete
            get_bookmark(id): Get by ID
            get_all_bookmarks(): Get all bookmarks
            get_by_category(category): Filter by category
            get_by_tag(tag): Filter by tag
            search(query): Search bookmarks
            import_bookmarks(filepath): Import from file
            export_bookmarks(filepath, format): Export to file
            validate_urls(bookmarks): Check URL validity
            get_statistics(): Get bookmark statistics
            get_category_counts(): Get counts per category
        
        Events:
            Emits callbacks on add, update, delete operations
        """
    
    SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}

    def __init__(self, category_manager: CategoryManager,
                 tag_manager: TagManager,
                 filepath: Path = MASTER_BOOKMARKS_FILE,
                 storage_backend: Optional[str] = None):
        self.category_manager = category_manager
        self.tag_manager = tag_manager
        self.storage_backend = self._resolve_storage_backend(filepath, storage_backend)
        self.filepath = self._resolve_storage_path(filepath, self.storage_backend)
        self.storage = self._create_storage(self.filepath, self.storage_backend)
        self.bookmarks: Dict[int, Bookmark] = OrderedDict()
        self._lock = threading.RLock()
        self.search_engine = SearchEngine()
        self._load_bookmarks()

    @classmethod
    def _resolve_storage_backend(cls, filepath: Path, requested: Optional[str] = None) -> str:
        backend = (requested or os.getenv("BOOKMARK_STORAGE_BACKEND", "")).strip().lower()
        if backend in {"sqlite", "sqlite3"}:
            return "sqlite"
        if backend == "json":
            return "json"
        if backend:
            log.warning(f"Unknown bookmark storage backend {backend!r}; using JSON")
            return "json"
        suffix = Path(filepath).suffix.lower()
        return "sqlite" if suffix in cls.SQLITE_SUFFIXES else "json"

    @classmethod
    def _resolve_storage_path(cls, filepath: Path, backend: str) -> Path:
        path = Path(filepath)
        if backend == "sqlite" and path.suffix.lower() not in cls.SQLITE_SUFFIXES:
            return path.with_suffix(".sqlite")
        return path

    @staticmethod
    def _create_storage(filepath: Path, backend: str):
        if backend == "sqlite":
            return SQLiteStorageManager(filepath)
        return StorageManager(filepath)

    def _assign_unique_id(self, bookmark: Bookmark):
        """Ensure an incoming bookmark cannot overwrite an existing ID."""
        while bookmark.id in self.bookmarks:
            old_id = bookmark.id
            bookmark.id = int.from_bytes(os.urandom(8), 'big')
            log.warning(f"Regenerated duplicate bookmark id {old_id}")

    def _coerce_bookmark_id(self, bookmark_id) -> Optional[int]:
        """Normalize user/UI supplied bookmark IDs before dictionary lookup."""
        try:
            value = int(bookmark_id)
            return value if value >= 0 else None
        except (TypeError, ValueError):
            return None

    def _load_bookmarks(self):
        """Load all bookmarks from storage"""
        with self._lock:
            self.bookmarks.clear()
            for bm in self.storage.load():
                self._assign_unique_id(bm)
                self.bookmarks[bm.id] = bm

    def reload(self):
        """Reload bookmarks from disk"""
        self._load_bookmarks()

    # --- Safepoints / backups (disaster recovery) ----------------------------

    def create_safepoint(self, label: str = "manual") -> Optional[str]:
        """Capture a preserved snapshot for recovery (startup, pre-import, etc.).

        Returns the safepoint name or None. No-ops gracefully on storage
        backends that don't support it.
        """
        fn = getattr(self.storage, "create_safepoint", None)
        if callable(fn):
            try:
                return fn(label)
            except Exception as exc:
                log.warning(f"Safepoint failed: {exc}")
        return None

    def list_backups(self) -> List[Tuple[str, datetime, int]]:
        """Available backups + safepoints (name, mtime, size), newest first."""
        fn = getattr(self.storage, "get_backups", None)
        return fn() if callable(fn) else []

    def restore_backup(self, name: str) -> bool:
        """Restore a backup/safepoint by name and reload into memory."""
        fn = getattr(self.storage, "restore_backup", None)
        if not callable(fn):
            return False
        with self._lock:
            if not fn(name):
                return False
            self._load_bookmarks()
        return True

    # --- File-change watching (R-74) ----------------------------------------

    def start_file_watcher(self, interval: float = 5.0,
                           on_reload: callable = None):
        """Poll the bookmark file's mtime and reload on external changes.

        ``on_reload`` is called (no args) after a successful reload so the
        GUI can refresh its views.
        """
        self._watch_mtime = self._get_mtime()
        self._watch_callback = on_reload
        self._watch_interval = interval
        self._watch_stop = threading.Event()
        self._watch_thread = threading.Thread(
            target=self._file_watch_loop, daemon=True
        )
        self._watch_thread.start()

    def stop_file_watcher(self):
        stop = getattr(self, "_watch_stop", None)
        if stop:
            stop.set()

    def _get_mtime(self) -> float:
        try:
            return self.filepath.stat().st_mtime
        except OSError:
            return 0.0

    def _file_watch_loop(self):
        while not self._watch_stop.wait(self._watch_interval):
            current = self._get_mtime()
            if current != self._watch_mtime and current > 0:
                self._watch_mtime = current
                log.info("Bookmark file changed externally — reloading")
                self._load_bookmarks()
                cb = self._watch_callback
                if cb:
                    try:
                        cb()
                    except Exception:
                        pass

    def save_bookmarks(self):
        """Save all bookmarks to storage (thread-safe — holds lock through write)."""
        with self._lock:
            if getattr(self, "_batch_depth", 0) > 0:
                self._batch_dirty = True
                return
            snapshot = list(self.bookmarks.values())
            self._save_snapshot(snapshot)

    def _save_snapshot(self, snapshot: List[Bookmark]):
        """Persist a snapshot unless the current batch should coalesce saves.

        Caller must hold self._lock when batch state is relevant.
        """
        if getattr(self, "_batch_depth", 0) > 0:
            self._batch_dirty = True
            return
        self.storage.save([bm.to_dict() for bm in snapshot])

    @contextlib.contextmanager
    def batch(self):
        """Suppress per-mutation saves; flush once on exit.

        Usage::

            with manager.batch():
                for url in urls:
                    manager.add_bookmark_clean(url=url, ...)
            # single save happens here
        """
        with self._lock:
            self._batch_depth = getattr(self, "_batch_depth", 0) + 1
            self._batch_dirty = getattr(self, "_batch_dirty", False)
        try:
            yield
        finally:
            with self._lock:
                self._batch_depth -= 1
                if self._batch_depth == 0 and self._batch_dirty:
                    self._batch_dirty = False
                    snapshot = list(self.bookmarks.values())
                    self.storage.save([bm.to_dict() for bm in snapshot])

    def add_bookmark(self, bookmark: Bookmark, save: bool = True) -> Bookmark:
        """Add a new bookmark. Set save=False for batch operations."""
        with self._lock:
            self._assign_unique_id(bookmark)
            self.bookmarks[bookmark.id] = bookmark
            if save:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return bookmark
    
    def update_bookmark(self, bookmark_or_id, **kwargs) -> Optional[Bookmark]:
        """Update a bookmark's attributes. Can accept Bookmark object or bookmark_id."""
        # Handle both Bookmark object and ID
        if isinstance(bookmark_or_id, Bookmark):
            bookmark = bookmark_or_id
            bookmark.modified_at = datetime.now().isoformat()
            with self._lock:
                if bookmark.id is None:
                    bookmark.id = int.from_bytes(os.urandom(8), 'big')
                self.bookmarks[bookmark.id] = bookmark
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
            return bookmark

        # Legacy: ID with kwargs
        bookmark_id = self._coerce_bookmark_id(bookmark_or_id)
        if bookmark_id is None:
            return None
        with self._lock:
            bm = self.bookmarks.get(bookmark_id)
            if bm:
                for key, value in kwargs.items():
                    if hasattr(bm, key):
                        setattr(bm, key, value)
                bm.modified_at = datetime.now().isoformat()
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return bm
    
    def delete_bookmark(self, bookmark_id: int) -> bool:
        """Delete a bookmark"""
        bookmark_id = self._coerce_bookmark_id(bookmark_id)
        if bookmark_id is None:
            return False
        with self._lock:
            if bookmark_id in self.bookmarks:
                del self.bookmarks[bookmark_id]
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
                return True
        return False
    
    def get_bookmark(self, bookmark_id: int) -> Optional[Bookmark]:
        """Get a bookmark by ID"""
        bookmark_id = self._coerce_bookmark_id(bookmark_id)
        if bookmark_id is None:
            return None
        return self.bookmarks.get(bookmark_id)
    
    def import_html_file(self, filepath: str, source_name: str = "") -> Tuple[int, int]:
        """Import bookmarks from HTML file"""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            log.error(f"Error reading file {filepath}: {e}")
            return 0, 0

        soup_class = BeautifulSoup
        if soup_class is None:
            try:
                from bs4 import BeautifulSoup as soup_class
            except Exception as exc:
                log.error(f"HTML import requires BeautifulSoup: {exc}")
                return 0, 0

        soup = soup_class(content, 'html.parser')
        added = duplicates = 0
        existing_urls = {normalize_url(bm.url) for bm in self._iter_snapshot()}
        source = source_name or Path(filepath).name

        for a_tag in soup.find_all('a'):
            href = str(a_tag.get('href', '') or '').strip()
            valid_url, error = validate_url(href)
            if not valid_url or not href.startswith(('http://', 'https://')):
                if href:
                    log.warning(f"Skipping invalid imported URL '{href[:80]}': {error}")
                continue

            normalized = normalize_url(href)
            if normalized in existing_urls:
                duplicates += 1
                continue

            title = html_module.unescape(a_tag.get_text(strip=True) or href)
            category = self.category_manager.categorize_url(href, title)

            try:
                bm = Bookmark(
                    id=None,
                    title=title[:500],
                    url=href,
                    add_date=str(a_tag.get('add_date', '') or ''),
                    icon=str(a_tag.get('icon', '') or ''),
                    category=category,
                    source_file=source
                )
            except ValueError as exc:
                log.warning(f"Skipping invalid imported bookmark '{href[:80]}': {exc}")
                continue
            self.add_bookmark(bm, save=False)
            existing_urls.add(normalized)
            added += 1

        if added > 0:
            self.save_bookmarks()

        return added, duplicates
    
    def import_json_file(self, filepath: str) -> Tuple[int, int]:
        """Import bookmarks from JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            log.error(f"Error reading JSON file {filepath}: {e}")
            return 0, 0

        added = duplicates = 0
        existing_urls = {normalize_url(bm.url) for bm in self._iter_snapshot()}

        bookmarks_data = data.get("bookmarks", data.get("data", [])) if isinstance(data, dict) else data
        if not isinstance(bookmarks_data, list):
            log.error(f"Invalid JSON structure in {filepath}")
            return 0, 0

        for item in bookmarks_data:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            valid_url, error = validate_url(url)
            if not valid_url:
                log.warning(f"Skipping invalid bookmark URL '{url[:80]}': {error}")
                continue
            normalized = normalize_url(url)
            if normalized in existing_urls:
                duplicates += 1
                continue

            try:
                bm = Bookmark.from_dict(item)
                self.add_bookmark(bm, save=False)
                existing_urls.add(normalized)
                added += 1
            except Exception as e:
                log.warning(f"Skipping invalid bookmark '{url[:80]}': {e}")

        if added > 0:
            self.save_bookmarks()

        return added, duplicates
    
    def get_bookmarks_by_category(self, category: str, 
                                   include_children: bool = True) -> List[Bookmark]:
        """Get bookmarks in a category"""
        results = []
        for bm in self._iter_snapshot():
            if bm.category == category:
                results.append(bm)
            elif include_children and bm.parent_category == category:
                results.append(bm)
        return results

    def get_bookmarks_by_tag(self, tag: str) -> List[Bookmark]:
        """Get bookmarks with a specific tag"""
        tag_lower = str(tag or "").strip().lower()
        if not tag_lower:
            return []
        return [bm for bm in self._iter_snapshot()
                if any(tag_lower == str(t).lower() for t in bm.tags)]
    
    def _iter_snapshot(self) -> List[Bookmark]:
        """Return a thread-safe snapshot for read-only iteration.

        Readers must never iterate ``self.bookmarks`` directly: a concurrent
        mutating thread (AI categorization, file-watcher reload, merge/trash)
        can change the dict size mid-iteration and raise ``RuntimeError`` or
        yield a torn view. Snapshotting the values under the lock avoids both.
        """
        with self._lock:
            return list(self.bookmarks.values())

    def get_all_bookmarks(self) -> List[Bookmark]:
        """Get all bookmarks"""
        return self._iter_snapshot()

    def get_pinned_bookmarks(self) -> List[Bookmark]:
        """Get pinned bookmarks"""
        return [bm for bm in self._iter_snapshot() if bm.is_pinned]

    def get_archived_bookmarks(self) -> List[Bookmark]:
        """Get archived bookmarks"""
        return [bm for bm in self._iter_snapshot() if bm.is_archived]

    def get_recent_bookmarks(self, days: int = 7) -> List[Bookmark]:
        """Get recently added bookmarks"""
        try:
            days = max(0, int(days))
        except (TypeError, ValueError):
            days = 7
        cutoff = datetime.now() - timedelta(days=days)
        results = []
        for bm in self._iter_snapshot():
            try:
                created = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                if created.replace(tzinfo=None) > cutoff:
                    results.append(bm)
            except Exception:
                pass
        return sorted(results, key=lambda x: x.created_at, reverse=True)

    def get_stale_bookmarks(self, days: int = 90) -> List[Bookmark]:
        """Get bookmarks not visited in the given number of days."""
        return [bm for bm in self._iter_snapshot() if bm.age_days > days or bm.is_stale]

    def get_frequently_visited(self, limit: int = 20) -> List[Bookmark]:
        """Get most frequently visited bookmarks"""
        try:
            limit = max(0, int(limit))
        except (TypeError, ValueError):
            limit = 20
        visited = [
            bm for bm in self._iter_snapshot()
            if safe_int(getattr(bm, "visit_count", 0), 0) > 0
        ]
        return sorted(
            visited,
            key=lambda x: safe_int(getattr(x, "visit_count", 0), 0),
            reverse=True,
        )[:limit]

    def get_category_counts(self) -> Dict[str, int]:
        """Get bookmark count per category"""
        counts = {cat: 0 for cat in self.category_manager.categories}
        for bm in self._iter_snapshot():
            counts[bm.category] = counts.get(bm.category, 0) + 1
        return counts

    def get_tag_counts(self) -> Dict[str, int]:
        """Get bookmark count per tag"""
        counts: Dict[str, int] = {}
        for bm in self._iter_snapshot():
            for tag in bm.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts
    
    def search_bookmarks(self, query: str, category: str = None) -> List[Bookmark]:
        """Search bookmarks with advanced query"""
        if category:
            bookmarks = self.get_bookmarks_by_category(category)
        else:
            bookmarks = self.get_all_bookmarks()
        
        results = self.search_engine.search(bookmarks, query)
        return [bm for bm, score in results]
    
    def find_duplicates(self) -> Dict[str, List[Bookmark]]:
        """Find duplicate bookmarks using normalized URLs.

        Uses academic-grade URL canonicalization: strips tracking params,
        normalizes scheme/host/port/path, removes fragments, sorts query params.
        """
        url_map: Dict[str, List[Bookmark]] = {}
        for bm in self._iter_snapshot():
            canonical = normalize_url(bm.url)
            url_map.setdefault(canonical, []).append(bm)

        return {url: bms for url, bms in url_map.items() if len(bms) > 1}

    def merge_duplicates(self, dry_run: bool = False) -> Tuple[int, int]:
        """Find and merge duplicate bookmarks, keeping the best data from each.

        Returns (groups_merged, bookmarks_removed).
        If dry_run=True, returns counts without modifying data.
        """
        dupes = self.find_duplicates()
        groups_merged = 0
        bookmarks_removed = 0

        if dry_run:
            for bm_list in dupes.values():
                if len(bm_list) >= 2:
                    groups_merged += 1
                    bookmarks_removed += len(bm_list) - 1
            return groups_merged, bookmarks_removed

        # Mutating the dict (keeper update + removals) must happen under the
        # lock so a concurrent reader/watcher can't observe a half-merged state
        # or raise "dictionary changed size during iteration".
        with self._lock:
            for canonical_url, bm_list in dupes.items():
                if len(bm_list) < 2:
                    continue

                merged_data = merge_duplicate_bookmarks(bm_list)
                # Keep the first bookmark, update it with merged data, delete the rest
                keeper = bm_list[0]
                for key, value in merged_data.items():
                    if key != 'id' and hasattr(keeper, key):
                        setattr(keeper, key, value)
                keeper.modified_at = datetime.now().isoformat()
                self.bookmarks[keeper.id] = keeper

                for bm in bm_list[1:]:
                    self.bookmarks.pop(bm.id, None)

                groups_merged += 1
                bookmarks_removed += len(bm_list) - 1

            if groups_merged > 0:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)

        return groups_merged, bookmarks_removed

    def get_health_scores(self) -> List[Tuple[Bookmark, int]]:
        """Get health scores for all bookmarks, sorted worst-first."""
        scored = [(bm, calculate_health_score(bm)) for bm in self._iter_snapshot()]
        return sorted(scored, key=lambda x: x[1])

    def fetch_metadata_for_bookmark(self, bookmark_id: int) -> bool:
        """Fetch and update title/description/favicon from the live URL.

        Returns True if any field was updated.
        """
        bm = self.bookmarks.get(bookmark_id)
        if not bm:
            return False

        meta = fetch_page_metadata(bm.url)
        updated = False

        if meta['title'] and (not bm.title or bm.title == bm.url):
            bm.title = meta['title']
            updated = True

        if meta['description'] and not bm.description:
            bm.description = meta['description']
            updated = True

        if meta['favicon_url'] and not bm.favicon_url:
            bm.favicon_url = meta['favicon_url']
            updated = True

        if updated:
            bm.modified_at = datetime.now().isoformat()
            self.save_bookmarks()

        return updated

    def check_wayback(self, bookmark_id: int) -> Optional[str]:
        """Check if a bookmark has a Wayback Machine snapshot.

        Returns the archive URL or None.
        """
        bm = self.bookmarks.get(bookmark_id)
        if not bm:
            return None
        return wayback_check(bm.url)

    def save_to_wayback(self, bookmark_id: int) -> Optional[str]:
        """Submit a bookmark to the Wayback Machine for archival.

        Returns the archive URL or None.
        """
        bm = self.bookmarks.get(bookmark_id)
        if not bm:
            return None
        return wayback_save(bm.url)
    
    # ── Soft Delete / Trash (inspired by LinkAce) ─────────────────────────
    def soft_delete_bookmark(self, bookmark_id: int) -> bool:
        """Move a bookmark to trash instead of permanent deletion.

        Sets is_archived=True and adds a '_deleted_at' timestamp to custom_data.
        Use restore_from_trash() to recover, or empty_trash() to purge.
        """
        with self._lock:
            bm = self.bookmarks.get(bookmark_id)
            if not bm:
                return False
            bm.is_archived = True
            bm.custom_data['_deleted_at'] = datetime.now().isoformat()
            bm.modified_at = datetime.now().isoformat()
            snapshot = list(self.bookmarks.values())
            self._save_snapshot(snapshot)
        return True

    def restore_from_trash(self, bookmark_id: int) -> bool:
        """Restore a bookmark from trash."""
        with self._lock:
            bm = self.bookmarks.get(bookmark_id)
            if not bm:
                return False
            bm.is_archived = False
            bm.custom_data.pop('_deleted_at', None)
            bm.modified_at = datetime.now().isoformat()
            snapshot = list(self.bookmarks.values())
            self._save_snapshot(snapshot)
        return True

    def get_trash(self) -> List[Bookmark]:
        """Get all bookmarks in the trash."""
        return [bm for bm in self._iter_snapshot()
                if bm.is_archived and '_deleted_at' in bm.custom_data]

    def empty_trash(self) -> int:
        """Permanently delete all bookmarks in the trash."""
        with self._lock:
            trash_ids = [bm.id for bm in self.bookmarks.values()
                         if bm.is_archived and '_deleted_at' in bm.custom_data]
            for bid in trash_ids:
                self.bookmarks.pop(bid, None)
            if trash_ids:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return len(trash_ids)

    # ── Random Bookmark Rediscovery (inspired by Buku) ──────────────────
    def get_random_bookmark(self, exclude_trash: bool = True) -> Optional[Bookmark]:
        """Get a random bookmark for rediscovery.

        Excludes archived/trashed bookmarks by default.
        """
        import random
        candidates = [bm for bm in self._iter_snapshot()
                      if not (exclude_trash and bm.is_archived)]
        return random.choice(candidates) if candidates else None

    # ── Batch Metadata Refresh (inspired by Buku's multi-threaded refresh) ──
    def batch_refresh_metadata(self, bookmark_ids: List[int] = None,
                                max_workers: int = 5,
                                progress_callback: Callable = None) -> int:
        """Re-fetch titles and descriptions for multiple bookmarks.

        If bookmark_ids is None, refreshes all bookmarks.
        Returns count of bookmarks updated.
        """
        try:
            max_workers = max(1, min(32, int(max_workers)))
        except (TypeError, ValueError):
            max_workers = 5

        if bookmark_ids is None:
            targets = list(self.bookmarks.values())
        else:
            normalized_ids = []
            for bid in bookmark_ids:
                try:
                    normalized_ids.append(int(bid))
                except (TypeError, ValueError):
                    continue
            targets = [self.bookmarks[bid] for bid in normalized_ids if bid in self.bookmarks]

        if not targets:
            return 0

        updated = 0
        total = len(targets)

        def refresh_one(bm):
            meta = fetch_page_metadata(bm.url, timeout=8)
            return bm.id, meta

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(refresh_one, bm): bm for bm in targets}
            done = 0
            for future in as_completed(futures):
                done += 1
                try:
                    bm_id, meta = future.result()
                    with self._lock:
                        bm = self.bookmarks.get(bm_id)
                        if bm:
                            changed = False
                            if meta['title'] and (not bm.title or bm.title == bm.url):
                                bm.title = meta['title']
                                changed = True
                            if meta['description'] and not bm.description:
                                bm.description = meta['description']
                                changed = True
                            if meta['favicon_url'] and not bm.favicon_url:
                                bm.favicon_url = meta['favicon_url']
                                changed = True
                            if changed:
                                bm.modified_at = datetime.now().isoformat()
                                updated += 1
                except Exception as exc:
                    bm = futures[future]
                    log.warning(f"Metadata refresh failed for bookmark {bm.id} ({bm.url[:60]}): {exc}")
                if progress_callback:
                    try:
                        progress_callback(done, total)
                    except Exception:
                        pass

        if updated > 0:
            with self._lock:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return updated

    # ── Auto-Clean URLs on Add (inspired by Shaarli) ────────────────────
    def add_bookmark_clean(self, url: str, title: str = "",
                           category: str = "", tags: List[str] = None,
                           **kwargs) -> Optional[Bookmark]:
        """Add a bookmark with automatic URL cleaning and categorization.

        Strips tracking parameters, normalizes URL, auto-categorizes if no
        category given, and checks for duplicates.
        """
        # Clean the URL
        url = str(url or "").strip()
        valid_url, error = validate_url(url)
        if not valid_url or not url.startswith(('http://', 'https://')):
            log.warning(f"Rejected invalid bookmark URL '{str(url)[:80]}': {error}")
            return None

        clean = normalize_url(url)
        # But keep the original scheme if user explicitly used http
        if url.startswith('http://') and clean.startswith('https://'):
            clean = 'http://' + clean[8:]

        canonical = normalize_url(url)

        # Auto-categorize before taking the lock (category_manager has its own
        # lock; doing it here keeps the critical section short).
        if not category:
            category = self.category_manager.categorize_url(clean, title)

        # Hold the lock across the duplicate scan AND the insert so two threads
        # adding the same URL concurrently can't both pass the scan and create a
        # duplicate (the scan and add_bookmark were previously separate critical
        # sections — a TOCTOU window). add_bookmark re-enters the reentrant lock.
        with self._lock:
            for bm in self.bookmarks.values():
                if normalize_url(bm.url) == canonical:
                    return bm  # Already exists — return existing rather than creating duplicate

            bm = Bookmark(
                id=None, url=clean, title=title or clean,
                category=category, tags=tags or [], **kwargs
            )
            if bm.read_later and bm.read_later_position == 0:
                from bookmark_organizer_pro.services.read_later import ReadLaterQueue
                ReadLaterQueue.enqueue(bm, all_bookmarks=self.bookmarks.values())
            return self.add_bookmark(bm)

    def find_broken_links(self) -> List[Bookmark]:
        """Get bookmarks marked as broken"""
        return [bm for bm in self._iter_snapshot() if not bm.is_valid]

    def find_by_url(self, url: str) -> Optional[Bookmark]:
        """Find a bookmark by its URL"""
        if not url:
            return None

        # Normalize URL for comparison
        normalized = normalize_url(url)

        for bm in self._iter_snapshot():
            bm_url = normalize_url(bm.url)
            if bm_url == normalized:
                return bm

        return None
    
    def url_exists(self, url: str) -> bool:
        """Check if a URL already exists in bookmarks"""
        return self.find_by_url(url) is not None
    
    def get_domain_stats(self) -> List[Tuple[str, int]]:
        """Get bookmark count per domain"""
        domain_counts: Dict[str, int] = {}
        for bm in self._iter_snapshot():
            domain = bm.domain
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        return sorted(domain_counts.items(), key=lambda x: -x[1])
    
    def clean_tracking_params(self) -> int:
        """Clean tracking parameters from all URLs"""
        with self._lock:
            cleaned = 0
            for bm in self.bookmarks.values():
                clean_url = bm.clean_url()
                if clean_url != bm.url:
                    bm.url = clean_url
                    bm.modified_at = datetime.now().isoformat()
                    cleaned += 1
            if cleaned > 0:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return cleaned
    
    def merge_tags(self, source_tag: str, target_tag: str) -> int:
        """Merge one tag into another across all bookmarks"""
        source_tag = str(source_tag or "").strip()
        target_tag = str(target_tag or "").strip()
        if not source_tag or not target_tag:
            return 0
        source_key = source_tag.lower()
        target_key = target_tag.lower()
        if source_key == target_key:
            return 0

        with self._lock:
            count = 0
            for bm in self.bookmarks.values():
                existing_tags = list(bm.tags)
                if any(str(tag).lower() == source_key for tag in existing_tags):
                    bm.tags = [tag for tag in existing_tags if str(tag).lower() != source_key]
                    if not any(str(tag).lower() == target_key for tag in bm.tags):
                        bm.tags.append(target_tag)
                    bm.modified_at = datetime.now().isoformat()
                    count += 1
            if count > 0:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return count
    
    def export_html(self, filepath: str, category: str = None):
        """Export bookmarks to HTML format"""
        if category:
            by_category = {category: self.get_bookmarks_by_category(category)}
        else:
            by_category: Dict[str, List[Bookmark]] = {}
            for bm in self._iter_snapshot():
                by_category.setdefault(bm.category, []).append(bm)
        
        # Sort categories
        uncategorized = [c for c in by_category if "Uncategorized" in c]
        regular = sorted([c for c in by_category if "Uncategorized" not in c])
        categories = regular + uncategorized

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write('<!DOCTYPE NETSCAPE-Bookmark-file-1>\n')
            f.write('<!-- Exported by Bookmark Organizer Pro v4 -->\n')
            f.write('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n')
            f.write('<TITLE>Bookmarks</TITLE>\n<H1>Bookmarks</H1>\n<DL><p>\n')
            
            for cat in categories:
                bookmarks = by_category.get(cat, [])
                if not bookmarks:
                    continue
                
                f.write(f'    <DT><H3>{self._escape_html(cat)}</H3>\n    <DL><p>\n')
                for bm in bookmarks:
                    attrs = f'HREF="{self._escape_html(bm.url)}"'
                    if bm.add_date:
                        attrs += f' ADD_DATE="{self._escape_html(bm.add_date)}"'
                    if bm.icon:
                        attrs += f' ICON="{self._escape_html(bm.icon)}"'
                    if bm.tags:
                        attrs += f' TAGS="{self._escape_html(",".join(bm.tags))}"'
                    f.write(f'        <DT><A {attrs}>{self._escape_html(bm.title)}</A>\n')
                f.write('    </DL><p>\n')
            
            f.write('</DL><p>\n')
    
    def export_json(self, filepath: str):
        """Export bookmarks to JSON format"""
        data = {
            "version": 4,
            "exported_at": datetime.now().isoformat(),
            "app_version": APP_VERSION,
            "categories": {name: cat.to_dict()
                          for name, cat in self.category_manager.categories.items()},
            "tags": [tag.to_dict() for tag in self.tag_manager.tags.values()],
            "bookmarks": [bm.to_dict() for bm in self._iter_snapshot()]
        }
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=filepath.parent, suffix='.tmp', text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, filepath)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    def export_csv(self, filepath: str):
        """Export bookmarks to CSV format"""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Title', 'URL', 'Category', 'Tags', 'Notes',
                           'Created', 'Visits', 'Is Pinned'])
            for bm in self._iter_snapshot():
                writer.writerow([
                    _csv_safe_cell(bm.title),
                    _csv_safe_cell(bm.url),
                    _csv_safe_cell(bm.category),
                    _csv_safe_cell(','.join(bm.tags)),
                    _csv_safe_cell(bm.notes),
                    bm.created_at,
                    bm.visit_count,
                    bm.is_pinned
                ])
    
    def export_markdown(self, filepath: str):
        """Export bookmarks to Markdown format"""
        by_category: Dict[str, List[Bookmark]] = {}
        for bm in self._iter_snapshot():
            by_category.setdefault(bm.category, []).append(bm)

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('# Bookmarks\n\n')
            f.write(f'Exported: {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n')
            f.write(f'Total: {len(self.bookmarks)} bookmarks\n\n---\n\n')
            
            for cat in sorted(by_category.keys()):
                bookmarks = by_category[cat]
                f.write(f'## {self._markdown_text(cat)}\n\n')
                for bm in bookmarks:
                    tags_str = (
                        ' '.join(f'`{self._markdown_text(t)}`' for t in bm.tags)
                        if bm.tags else ''
                    )
                    f.write(
                        f'- [{self._markdown_text(bm.title)}]'
                        f'({self._markdown_url(bm.url)})'
                    )
                    if tags_str:
                        f.write(f' {tags_str}')
                    f.write('\n')
                    if bm.notes:
                        notes = self._markdown_text(bm.notes).replace('\n', '\n  > ')
                        f.write(f'  > {notes}\n')
                f.write('\n')
    
    def export_txt(self, filepath: str, include_titles: bool = True):
        """Export bookmarks to text format"""
        by_category: Dict[str, List[Bookmark]] = {}
        for bm in self._iter_snapshot():
            by_category.setdefault(bm.category, []).append(bm)

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            for cat in sorted(by_category.keys()):
                f.write(f"=== {cat} ===\n\n")
                for bm in by_category[cat]:
                    if include_titles:
                        f.write(f"{bm.title}\n{bm.url}\n\n")
                    else:
                        f.write(f"{bm.url}\n")
                f.write("\n")
    
    def export_urls_only(self, filepath: str):
        """Export just URLs"""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            for bm in self._iter_snapshot():
                f.write(bm.url + '\n')
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters"""
        text = str(text or "")
        return (text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace('"', "&quot;"))

    def _markdown_text(self, text) -> str:
        """Escape Markdown syntax that can break exports."""
        text = str(text or "")
        return (
            text.replace("\\", "\\\\")
                .replace("[", "\\[")
                .replace("]", "\\]")
                .replace("`", "\\`")
                .replace("*", "\\*")
                .replace("_", "\\_")
                .replace("#", "\\#")
                .replace("|", "\\|")
        )

    def _markdown_url(self, url) -> str:
        """Escape URL delimiters for inline Markdown links."""
        return str(url or "").replace("\\", "%5C").replace("(", "\\(").replace(")", "\\)")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        snapshot = self._iter_snapshot()
        total = len(snapshot)
        category_counts = self.get_category_counts()
        tag_counts = self.get_tag_counts()
        domain_stats = self.get_domain_stats()[:10]
        duplicates = self.find_duplicates()

        # Calculate age distribution
        age_dist = {"<7 days": 0, "7-30 days": 0, "1-6 months": 0, ">6 months": 0}
        for bm in snapshot:
            age = bm.age_days
            if age < 7:
                age_dist["<7 days"] += 1
            elif age < 30:
                age_dist["7-30 days"] += 1
            elif age < 180:
                age_dist["1-6 months"] += 1
            else:
                age_dist[">6 months"] += 1
        
        return {
            "total_bookmarks": total,
            "total_categories": len(self.category_manager.categories),
            "total_tags": len(tag_counts),
            "category_counts": category_counts,
            "tag_counts": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:20]),
            "top_domains": domain_stats,
            "duplicate_groups": len(duplicates),
            "duplicate_bookmarks": sum(len(bms) - 1 for bms in duplicates.values()),
            "uncategorized": category_counts.get("Uncategorized / Needs Review", 0),
            "pinned": len(self.get_pinned_bookmarks()),
            "archived": len(self.get_archived_bookmarks()),
            "stale": len(self.get_stale_bookmarks()),
            "broken": len(self.find_broken_links()),
            "age_distribution": age_dist,
            "with_notes": sum(1 for bm in snapshot if bm.notes),
            "with_tags": sum(1 for bm in snapshot if bm.tags),
        }
