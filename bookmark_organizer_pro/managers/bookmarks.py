"""Core bookmark manager and import/export operations."""

from __future__ import annotations

import bisect
import contextlib
import copy
import csv
import json
import os
import tempfile
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from bookmark_organizer_pro.constants import APP_VERSION, MASTER_BOOKMARKS_FILE
from bookmark_organizer_pro.core import CategoryManager, SQLiteStorageManager, StorageManager
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.search import SearchEngine
from bookmark_organizer_pro.services.extraction_templates import (
    format_structured_value,
    structured_metadata_fields,
    structured_metadata_payload,
)
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


@dataclass(frozen=True)
class TrashPurgeResult:
    """Outcome of one recovery-backed permanent trash purge."""

    requested_ids: tuple[int, ...] = ()
    purged_ids: tuple[int, ...] = ()
    failed_ids: tuple[int, ...] = ()
    recovery_bundle: str = ""
    errors: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return bool(self.requested_ids) and not self.failed_ids and not self.errors

    @property
    def purged_count(self) -> int:
        return len(self.purged_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "requested_ids": list(self.requested_ids),
            "purged_ids": list(self.purged_ids),
            "failed_ids": list(self.failed_ids),
            "purged_count": self.purged_count,
            "recovery_bundle": self.recovery_bundle,
            "errors": list(self.errors),
        }


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
        self._committed_bookmarks: Dict[int, Bookmark] = OrderedDict()
        self._batch_depth = 0
        self._batch_dirty = False
        self._batch_failed = False
        # normalized URL -> bookmark ids, in insertion order. Without it every
        # duplicate check re-normalizes the whole library, which is ~0.4s per
        # lookup at 50k bookmarks and happens twice on each extension save.
        self._url_index: Dict[str, List[int]] = {}
        self._url_key: Dict[int, str] = {}
        self._url_rank: Dict[int, int] = {}
        self._url_rank_next = 0
        self._url_index_ready = False
        self.search_engine = SearchEngine()
        from bookmark_organizer_pro.services.reader_progress import ReaderProgressStore

        self.reader_progress_store = ReaderProgressStore(
            path=self.filepath.parent / "reader_progress.json",
        )
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

    def _assign_unique_id(self, bookmark: Bookmark, existing: Optional[Dict[int, Bookmark]] = None):
        """Ensure an incoming bookmark cannot overwrite an existing ID."""
        existing = self.bookmarks if existing is None else existing
        while bookmark.id in existing:
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
            loaded = self.storage.load()
            if self.recovery_required:
                return
            self._storage_revision = getattr(self.storage, "revision", 0)
            self.bookmarks.clear()
            for bm in loaded:
                self._assign_unique_id(bm)
                self.bookmarks[bm.id] = bm
            self.reader_progress_store.apply_to_bookmarks(self.bookmarks.values())
            self._committed_bookmarks = copy.deepcopy(self.bookmarks)
            self._rebuild_url_index()

    def _restore_committed_state(self) -> None:
        """Restore the last successfully persisted in-memory representation."""
        self.bookmarks = copy.deepcopy(self._committed_bookmarks)
        self._invalidate_url_index()

    # ---- normalized URL index ---------------------------------------------
    # Every method below assumes the caller already holds ``self._lock``.

    def _rebuild_url_index(self) -> None:
        index: Dict[str, List[int]] = {}
        keys: Dict[int, str] = {}
        rank: Dict[int, int] = {}
        for bookmark_id, bookmark in self.bookmarks.items():
            if bookmark.is_deleted:
                continue
            rank[bookmark_id] = len(rank)
            key = normalize_url(bookmark.url)
            if key:
                index.setdefault(key, []).append(bookmark_id)
                keys[bookmark_id] = key
        self._url_index = index
        self._url_key = keys
        self._url_rank = rank
        self._url_rank_next = len(rank)
        self._url_index_ready = True

    def _invalidate_url_index(self) -> None:
        """Force a rebuild; used when the whole mapping is swapped out."""
        self._url_index = {}
        self._url_key = {}
        self._url_rank = {}
        self._url_rank_next = 0
        self._url_index_ready = False

    def _index_bookmark(self, bookmark: Bookmark) -> None:
        """(Re)index one bookmark under its current URL.

        The previous key comes from ``_url_key`` rather than from the stored
        object, because a caller can hand us the very object already in
        ``self.bookmarks`` after mutating its URL, in which case the old URL
        is already gone and re-deriving it would leave a phantom entry.
        """
        if not self._url_index_ready:
            return
        bookmark_id = bookmark.id
        if bookmark.is_deleted:
            previous = self._url_key.get(bookmark_id)
            if previous is not None:
                self._drop_index_entry(bookmark_id, previous)
            self._url_rank.pop(bookmark_id, None)
            return
        key = normalize_url(bookmark.url)
        previous = self._url_key.get(bookmark_id)
        if previous == key:
            return
        if previous is not None:
            self._drop_index_entry(bookmark_id, previous)
        if not key:
            return
        if bookmark_id not in self._url_rank:
            self._url_rank[bookmark_id] = self._url_rank_next
            self._url_rank_next += 1
        ids = self._url_index.setdefault(key, [])
        # Keep each key's ids in library order so a duplicate resolves to the
        # same row a full scan would have returned.
        position = bisect.bisect_left(
            [self._url_rank.get(i, 0) for i in ids], self._url_rank[bookmark_id],
        )
        ids.insert(position, bookmark_id)
        self._url_key[bookmark_id] = key

    def _drop_index_entry(self, bookmark_id: int, key: str) -> None:
        ids = self._url_index.get(key)
        if ids and bookmark_id in ids:
            ids.remove(bookmark_id)
        if ids is not None and not ids:
            self._url_index.pop(key, None)
        self._url_key.pop(bookmark_id, None)

    def _unindex_bookmark(self, bookmark_id: int) -> None:
        if not self._url_index_ready:
            return
        key = self._url_key.get(bookmark_id)
        if key is not None:
            self._drop_index_entry(bookmark_id, key)
        self._url_rank.pop(bookmark_id, None)

    def _lookup_by_normalized_url(self, normalized: str) -> Optional[Bookmark]:
        """First live bookmark for a normalized URL, matching scan order."""
        if not self._url_index_ready:
            self._rebuild_url_index()
        for bookmark_id in self._url_index.get(normalized, []):
            bookmark = self.bookmarks.get(bookmark_id)
            if bookmark is not None and not bookmark.is_deleted:
                return bookmark
        return None

    def _mapping_from_snapshot(self, snapshot: List[Bookmark]) -> Dict[int, Bookmark]:
        """Validate stable bookmark identity and rebuild an ordered snapshot map."""
        mapping: Dict[int, Bookmark] = OrderedDict()
        for bookmark in snapshot:
            bookmark_id = self._coerce_bookmark_id(bookmark.id)
            if bookmark_id is None:
                raise ValueError("bookmark id must be a non-negative integer")
            if bookmark_id in mapping:
                raise ValueError(f"duplicate bookmark id {bookmark_id}")
            mapping[bookmark_id] = bookmark
        if list(mapping) != list(self.bookmarks):
            raise ValueError("bookmark IDs are immutable; use add/delete instead of re-keying an update")
        return mapping

    def _record_committed_state(self, mapping: Dict[int, Bookmark], revision: int) -> None:
        self.bookmarks = mapping
        self._storage_revision = revision
        self._committed_bookmarks = copy.deepcopy(mapping)
        if hasattr(self, "_watch_revision"):
            self._watch_revision = revision
        if hasattr(self, "_watch_mtime"):
            self._watch_mtime = self._get_mtime()

    @property
    def storage_status(self):
        """Backend storage status; JSON exposes absent/valid-empty/corrupt states."""
        return getattr(self.storage, "status", None)

    @property
    def recovery_required(self) -> bool:
        status = self.storage_status
        return bool(status and status.recovery_required)

    @property
    def recovery_message(self) -> str:
        status = self.storage_status
        if not status or not status.recovery_required:
            return ""
        return (
            f"Library recovery required for {status.path}: {status.error}. "
            "Restore a verified backup or salvage complete records before editing."
        )

    def _ensure_storage_writable(self) -> None:
        check = getattr(self.storage, "assert_writable", None)
        if callable(check):
            check()

    def _sync_before_write(self) -> None:
        """Reload a newer persisted revision before applying a local mutation."""
        self._ensure_storage_writable()
        get_revision = getattr(self.storage, "current_revision", None)
        if not callable(get_revision):
            return
        persisted = get_revision()
        loaded = getattr(self, "_storage_revision", 0)
        if persisted != loaded:
            log.info(
                f"Library advanced from revision {loaded} to {persisted}; "
                "reloading before write"
            )
            self._load_bookmarks()

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

    def salvage_corrupt_file(self) -> Tuple[int, str]:
        """Explicitly salvage complete records while preserving the damaged source."""
        salvage = getattr(self.storage, "salvage", None)
        commit = getattr(self.storage, "commit_salvage", None)
        if not callable(salvage) or not callable(commit):
            return 0, ""
        with self._lock:
            bookmarks = salvage()
            preserved_path = commit(bookmarks)
            self._load_bookmarks()
        return len(bookmarks), preserved_path

    # --- File-change watching (R-74) ----------------------------------------

    def start_file_watcher(
        self,
        interval: float = 5.0,
        on_reload: callable = None,
        callback_scheduler: callable = None,
    ):
        """Poll the bookmark file's mtime and reload on external changes.

        ``on_reload`` is called (no args) after a successful reload so the
        GUI can refresh its views.
        """
        self.stop_file_watcher()
        self._watch_mtime = self._get_mtime()
        self._watch_revision = getattr(self, "_storage_revision", 0)
        self._watch_callback = on_reload
        self._watch_scheduler = callback_scheduler
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
        thread = getattr(self, "_watch_thread", None)
        if thread and thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=max(getattr(self, "_watch_interval", 0.1) * 2, 0.2))

    def _get_mtime(self) -> float:
        try:
            return self.filepath.stat().st_mtime
        except OSError:
            return 0.0

    def _file_watch_loop(self):
        while not self._watch_stop.wait(self._watch_interval):
            current = self._get_mtime()
            get_revision = getattr(self.storage, "current_revision", None)
            try:
                revision = get_revision() if callable(get_revision) else None
            except Exception as exc:
                log.warning(f"Could not poll library revision: {exc}")
                continue
            revision_changed = revision is not None and revision != self._watch_revision
            if revision_changed or (current != self._watch_mtime and current > 0):
                self._watch_mtime = current
                self._watch_revision = revision
                log.info("Bookmark file changed externally — reloading")
                self._load_bookmarks()
                cb = self._watch_callback
                if cb:
                    try:
                        scheduler = self._watch_scheduler
                        scheduler(cb) if scheduler else cb()
                    except Exception as exc:
                        log.warning(f"Library reload callback failed: {exc}")

    def save_bookmarks(self):
        """Save all bookmarks to storage (thread-safe — holds lock through write)."""
        with self._lock:
            try:
                self._ensure_storage_writable()
            except Exception:
                self._restore_committed_state()
                raise
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
        try:
            mapping = self._mapping_from_snapshot(snapshot)
            revision = self.storage.save(
                [bm.to_dict() for bm in mapping.values()],
                expected_revision=getattr(self, "_storage_revision", 0),
            )
        except Exception:
            self._restore_committed_state()
            raise
        self._record_committed_state(mapping, revision)

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
            outermost = self._batch_depth == 0
            if outermost:
                self._sync_before_write()
                self._batch_snapshot = copy.deepcopy(self.bookmarks)
                self._batch_revision = getattr(self, "_storage_revision", 0)
                self._batch_dirty = False
                self._batch_failed = False
            self._batch_depth += 1
            try:
                yield
            except BaseException:
                self._batch_failed = True
                raise
            finally:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    snapshot_before = self._batch_snapshot
                    revision_before = self._batch_revision
                    try:
                        if self._batch_failed:
                            self.bookmarks = snapshot_before
                            self._invalidate_url_index()
                            self._storage_revision = revision_before
                        elif self._batch_dirty:
                            snapshot = list(self.bookmarks.values())
                            mapping = self._mapping_from_snapshot(snapshot)
                            revision = self.storage.save(
                                [bm.to_dict() for bm in mapping.values()],
                                expected_revision=revision_before,
                            )
                            self._record_committed_state(mapping, revision)
                    except Exception:
                        self.bookmarks = snapshot_before
                        self._invalidate_url_index()
                        self._storage_revision = revision_before
                        raise
                    finally:
                        self._batch_dirty = False
                        self._batch_failed = False
                        del self._batch_snapshot
                        del self._batch_revision

    def add_bookmark(self, bookmark: Bookmark, save: bool = True) -> Bookmark:
        """Add a new bookmark. Set save=False for batch operations."""
        if save and self._batch_depth == 0:
            self._sync_before_write()
        with self._lock:
            self._assign_unique_id(bookmark)
            self.bookmarks[bookmark.id] = bookmark
            self._index_bookmark(bookmark)
            if save:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return bookmark
    
    def update_bookmark(self, bookmark_or_id, **kwargs) -> Optional[Bookmark]:
        """Update a bookmark's attributes. Can accept Bookmark object or bookmark_id."""
        if self._batch_depth == 0:
            self._sync_before_write()
        # Handle both Bookmark object and ID
        if isinstance(bookmark_or_id, Bookmark):
            bookmark = bookmark_or_id
            with self._lock:
                identity_key = next(
                    (key for key, value in self.bookmarks.items() if value is bookmark),
                    None,
                )
                requested_id = self._coerce_bookmark_id(bookmark.id)
                if identity_key is not None and requested_id != identity_key:
                    if self._batch_depth == 0:
                        self._restore_committed_state()
                    raise ValueError("bookmark IDs are immutable")
                bookmark_id = identity_key if identity_key is not None else requested_id
                if bookmark_id is None or bookmark_id not in self.bookmarks:
                    return None
                if self.bookmarks[bookmark_id].is_deleted:
                    return None
                updated = copy.deepcopy(bookmark)
                updated.id = bookmark_id
                updated.modified_at = datetime.now().isoformat()
                self.bookmarks[bookmark_id] = updated
                self._index_bookmark(updated)
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
            return updated

        # Legacy: ID with kwargs
        bookmark_id = self._coerce_bookmark_id(bookmark_or_id)
        if bookmark_id is None:
            return None
        with self._lock:
            bm = self.bookmarks.get(bookmark_id)
            if bm and not bm.is_deleted:
                if "id" in kwargs:
                    requested_id = self._coerce_bookmark_id(kwargs["id"])
                    if requested_id != bookmark_id:
                        raise ValueError("bookmark IDs are immutable")
                for key, value in kwargs.items():
                    if key != "id" and hasattr(bm, key):
                        setattr(bm, key, value)
                bm.modified_at = datetime.now().isoformat()
                self._index_bookmark(bm)
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return bm
    
    def delete_bookmark(self, bookmark_id: int) -> bool:
        """Move a live bookmark to persistent trash without touching artifacts."""
        return self.move_to_trash(bookmark_id)

    def discard_uncommitted_bookmark(self, bookmark_id: int) -> bool:
        """Remove a row created by a failed transaction before it became user data."""
        if self._batch_depth == 0:
            self._sync_before_write()
        bookmark_id = self._coerce_bookmark_id(bookmark_id)
        if bookmark_id is None:
            return False
        with self._lock:
            if bookmark_id in self.bookmarks:
                del self.bookmarks[bookmark_id]
                self._unindex_bookmark(bookmark_id)
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
                try:
                    self.reader_progress_store.reset(bookmark_id)
                except Exception as exc:
                    log.warning("Could not remove reader progress for %s: %s", bookmark_id, exc)
                return True
        return False
    
    def get_bookmark(
        self,
        bookmark_id: int,
        *,
        include_deleted: bool = False,
    ) -> Optional[Bookmark]:
        """Get a bookmark by ID, hiding persistent trash by default."""
        return self.get_bookmark_record(bookmark_id, include_deleted=include_deleted)

    def get_bookmark_record(
        self,
        bookmark_id: int,
        *,
        include_deleted: bool = False,
    ) -> Optional[Bookmark]:
        """Get one bookmark record, optionally including persistent trash."""
        bookmark_id = self._coerce_bookmark_id(bookmark_id)
        if bookmark_id is None:
            return None
        bookmark = self.bookmarks.get(bookmark_id)
        if bookmark is None or (bookmark.is_deleted and not include_deleted):
            return None
        return bookmark
    
    def import_html_file(self, filepath: str, source_name: str = "") -> Tuple[int, int]:
        """Import bookmarks from a Netscape HTML file.

        Routed through the same parser the desktop uses so both surfaces read
        the enclosing folder as the category and the TAGS attribute as tags.
        """
        from bookmark_organizer_pro.importers import NetscapeBookmarkImporter

        parsed = NetscapeBookmarkImporter.import_from_netscape(
            filepath, categorize=self.category_manager.categorize_url
        )
        added = duplicates = 0
        existing_urls = {normalize_url(bm.url) for bm in self._iter_snapshot()}
        source = source_name or Path(filepath).name

        for parsed_bookmark in parsed:
            href = parsed_bookmark.url
            valid_url, error = validate_url(href)
            if not valid_url or not href.startswith(('http://', 'https://')):
                if href:
                    log.warning(f"Skipping invalid imported URL '{href[:80]}': {error}")
                continue

            normalized = normalize_url(href)
            if normalized in existing_urls:
                duplicates += 1
                continue

            try:
                bm = Bookmark(
                    id=None,
                    title=(parsed_bookmark.title or href)[:500],
                    url=href,
                    category=parsed_bookmark.category,
                    tags=list(parsed_bookmark.tags),
                    source_file=source
                )
            except ValueError as exc:
                log.warning(f"Skipping invalid imported bookmark '{href[:80]}': {exc}")
                continue
            if parsed_bookmark.created_at:
                bm.created_at = parsed_bookmark.created_at
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
    
    def _iter_snapshot(self, *, include_deleted: bool = False) -> List[Bookmark]:
        """Return a thread-safe snapshot for read-only iteration.

        Readers must never iterate ``self.bookmarks`` directly: a concurrent
        mutating thread (AI categorization, file-watcher reload, merge/trash)
        can change the dict size mid-iteration and raise ``RuntimeError`` or
        yield a torn view. Snapshotting the values under the lock avoids both.
        """
        with self._lock:
            values = list(self.bookmarks.values())
        if include_deleted:
            return values
        return [bookmark for bookmark in values if not bookmark.is_deleted]

    def get_all_bookmarks(self, *, include_deleted: bool = False) -> List[Bookmark]:
        """Get live bookmarks, or every persisted record when explicitly requested."""
        return self._iter_snapshot(include_deleted=include_deleted)

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

        self._ensure_storage_writable()

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
                    self._trash_bookmark_locked(bm)
                # The keeper's URL can change during the merge, so rebuild
                # rather than trying to patch each entry.
                self._invalidate_url_index()

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
        self._ensure_storage_writable()
        bm = self.get_bookmark(bookmark_id)
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
        bm = self.get_bookmark(bookmark_id)
        if not bm:
            return None
        return wayback_check(bm.url)

    def save_to_wayback(self, bookmark_id: int) -> Optional[str]:
        """Submit a bookmark to the Wayback Machine for archival.

        Returns the archive URL or None.
        """
        bm = self.get_bookmark(bookmark_id)
        if not bm:
            return None
        return wayback_save(bm.url)
    
    # ── Persistent trash ---------------------------------------------------
    def _trash_bookmark_locked(self, bookmark: Bookmark) -> bool:
        if bookmark.is_deleted:
            return False
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        bookmark.deleted_at = now
        bookmark.custom_data.pop("_deleted_at", None)
        bookmark.modified_at = now
        self._unindex_bookmark(int(bookmark.id))
        return True

    def move_to_trash(self, bookmark_id: int) -> bool:
        """Persist a deletion timestamp while preserving state and artifacts."""
        if self._batch_depth == 0:
            self._sync_before_write()
        bookmark_id = self._coerce_bookmark_id(bookmark_id)
        if bookmark_id is None:
            return False
        with self._lock:
            bookmark = self.bookmarks.get(bookmark_id)
            if bookmark is None or not self._trash_bookmark_locked(bookmark):
                return False
            self._save_snapshot(list(self.bookmarks.values()))
        return True

    def soft_delete_bookmark(self, bookmark_id: int) -> bool:
        """Compatibility alias for the persistent trash contract."""
        return self.move_to_trash(bookmark_id)

    def restore_from_trash(self, bookmark_id: int) -> bool:
        """Restore one trashed bookmark without changing its archive state."""
        if self._batch_depth == 0:
            self._sync_before_write()
        bookmark_id = self._coerce_bookmark_id(bookmark_id)
        if bookmark_id is None:
            return False
        with self._lock:
            bookmark = self.bookmarks.get(bookmark_id)
            if bookmark is None or not bookmark.is_deleted:
                return False
            normalized = normalize_url(bookmark.url)
            existing = self._lookup_by_normalized_url(normalized)
            if existing is not None and existing.id != bookmark_id:
                return False
            bookmark.deleted_at = ""
            bookmark.custom_data.pop("_deleted_at", None)
            bookmark.modified_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            self._index_bookmark(bookmark)
            self._save_snapshot(list(self.bookmarks.values()))
        return True

    def get_trash(self) -> List[Bookmark]:
        """Return trashed records newest first."""
        trashed = [
            bookmark
            for bookmark in self._iter_snapshot(include_deleted=True)
            if bookmark.is_deleted
        ]
        return sorted(trashed, key=lambda item: (item.deleted_at, int(item.id)), reverse=True)

    def _owned_artifact_paths(self, bookmark: Bookmark, root: Path) -> tuple[Path, ...]:
        """Resolve every existing local artifact owned by one bookmark."""
        root = root.resolve()
        candidates: set[Path] = set()
        for field_name in (
            "snapshot_path",
            "extracted_text_path",
            "youtube_transcript_path",
            "screenshot_path",
        ):
            value = str(getattr(bookmark, field_name, "") or "").strip()
            if value:
                candidates.add(Path(value).expanduser())
        snapshots_root = root / "snapshots"
        bookmark_id = str(int(bookmark.id))
        if snapshots_root.is_dir():
            candidates.update(path for path in snapshots_root.glob(f"{bookmark_id}.*") if path.is_file())
            history_root = snapshots_root / bookmark_id
            if history_root.is_dir():
                candidates.update(path for path in history_root.rglob("*") if path.is_file())
        resolved: set[Path] = set()
        for candidate in candidates:
            try:
                path = candidate.resolve(strict=False)
                if not path.exists():
                    continue
                if not path.is_file() or not path.is_relative_to(root):
                    raise ValueError(f"owned artifact is outside local library storage: {candidate}")
            except (OSError, RuntimeError) as exc:
                raise ValueError(f"owned artifact path cannot be verified: {candidate}: {exc}") from exc
            resolved.add(path)
        return tuple(sorted(resolved, key=lambda path: path.as_posix()))

    def purge_trash(
        self,
        bookmark_ids: Iterable[int] | None = None,
        *,
        recovery_dir: str | Path | None = None,
        recovery_bundle_factory: Callable | None = None,
        recovery_coverage_verifier: Callable | None = None,
    ) -> TrashPurgeResult:
        """Permanently purge trash only after a complete bundle is verified."""
        if self._batch_depth:
            raise RuntimeError("Trash cannot be purged inside a bookmark batch")
        self._sync_before_write()
        with self._lock:
            trash = {int(bookmark.id): bookmark for bookmark in self.get_trash()}
            if bookmark_ids is None:
                requested = tuple(trash)
            else:
                normalized = {
                    value
                    for raw in bookmark_ids
                    if (value := self._coerce_bookmark_id(raw)) is not None
                }
                requested = tuple(sorted(normalized))
            targets = {bookmark_id: trash[bookmark_id] for bookmark_id in requested if bookmark_id in trash}
            missing = tuple(sorted(set(requested) - set(targets)))
            if not targets:
                errors = ("No matching trashed bookmarks were found",) if requested else ()
                return TrashPurgeResult(
                    requested_ids=requested,
                    failed_ids=missing,
                    errors=errors,
                )

            root = self.filepath.parent.resolve()
            try:
                artifacts = {
                    bookmark_id: self._owned_artifact_paths(bookmark, root)
                    for bookmark_id, bookmark in targets.items()
                }
            except ValueError as exc:
                return TrashPurgeResult(
                    requested_ids=requested,
                    failed_ids=tuple(sorted(targets)),
                    errors=(str(exc),),
                )

            remaining_references: set[Path] = set()
            for bookmark in self.bookmarks.values():
                if int(bookmark.id) in targets:
                    continue
                for field_name in (
                    "snapshot_path",
                    "extracted_text_path",
                    "youtube_transcript_path",
                    "screenshot_path",
                ):
                    value = str(getattr(bookmark, field_name, "") or "").strip()
                    if not value:
                        continue
                    try:
                        remaining_references.add(Path(value).expanduser().resolve(strict=False))
                    except (OSError, RuntimeError):
                        continue
            artifacts = {
                bookmark_id: tuple(path for path in paths if path not in remaining_references)
                for bookmark_id, paths in artifacts.items()
            }
            coverage_paths = {
                path.relative_to(root).as_posix()
                for paths in artifacts.values()
                for path in paths
            }
            for sidecar in (
                "reader_annotations.json",
                "reader_progress.json",
                "snapshot_history.json",
                "snapshot_failures.json",
            ):
                if (root / sidecar).is_file():
                    coverage_paths.add(sidecar)

            if recovery_bundle_factory is None or recovery_coverage_verifier is None:
                from bookmark_organizer_pro.services.recovery_bundle import (
                    create_recovery_bundle,
                    verify_recovery_bundle_coverage,
                )

                recovery_bundle_factory = recovery_bundle_factory or create_recovery_bundle
                recovery_coverage_verifier = (
                    recovery_coverage_verifier or verify_recovery_bundle_coverage
                )
            destination_root = Path(recovery_dir) if recovery_dir is not None else root / "backups" / "trash"
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            destination = destination_root / f"trash_purge_{stamp}.zip"
            try:
                destination_root.mkdir(parents=True, exist_ok=True)
                bundle = Path(recovery_bundle_factory(destination, data_dir=root)).resolve()
                recovery_coverage_verifier(
                    bundle,
                    bookmark_ids=targets,
                    relative_paths=coverage_paths,
                )
            except Exception as exc:
                return TrashPurgeResult(
                    requested_ids=requested,
                    failed_ids=tuple(sorted(set(targets) | set(missing))),
                    recovery_bundle=str(destination) if destination.is_file() else "",
                    errors=(f"Recovery bundle verification failed: {exc}",),
                )

            from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore
            from bookmark_organizer_pro.services.snapshot import SnapshotFailureStore
            from bookmark_organizer_pro.services.snapshot_history import SnapshotHistoryStore

            annotations_path = root / "reader_annotations.json"
            progress_path = root / "reader_progress.json"
            history_path = root / "snapshot_history.json"
            failures_path = root / "snapshot_failures.json"
            try:
                annotations = (
                    ReaderAnnotationStore(annotations_path)
                    if annotations_path.is_file()
                    else None
                )
                history = (
                    SnapshotHistoryStore(root / "snapshots")
                    if history_path.is_file()
                    else None
                )
                failures = (
                    SnapshotFailureStore(failures_path)
                    if failures_path.is_file()
                    else None
                )
            except Exception as exc:
                return TrashPurgeResult(
                    requested_ids=requested,
                    failed_ids=tuple(sorted(set(targets) | set(missing))),
                    recovery_bundle=str(bundle),
                    errors=(f"Trash metadata could not be opened safely: {exc}",),
                )
            purged: list[int] = []
            failed: list[int] = list(missing)
            errors: list[str] = []
            for bookmark_id, bookmark in targets.items():
                try:
                    for path in artifacts[bookmark_id]:
                        path.unlink(missing_ok=True)
                    if annotations is not None:
                        annotations.delete_for_bookmark(bookmark_id)
                    if progress_path.is_file():
                        self.reader_progress_store.reset(bookmark_id)
                    if history is not None:
                        history.clear_bookmark(bookmark_id)
                    if failures is not None:
                        failures.clear_for_bookmark(bookmark)
                except Exception as exc:
                    failed.append(bookmark_id)
                    errors.append(f"Bookmark {bookmark_id} artifact purge failed: {exc}")
                    continue
                self.bookmarks.pop(bookmark_id, None)
                self._unindex_bookmark(bookmark_id)
                purged.append(bookmark_id)
            if purged:
                try:
                    self._save_snapshot(list(self.bookmarks.values()))
                except Exception as exc:
                    failed.extend(purged)
                    errors.append(f"Purged bookmark records could not be committed: {exc}")
                    purged = []
            return TrashPurgeResult(
                requested_ids=requested,
                purged_ids=tuple(sorted(purged)),
                failed_ids=tuple(sorted(set(failed))),
                recovery_bundle=str(bundle),
                errors=tuple(errors),
            )

    def empty_trash(self) -> int:
        """Compatibility wrapper around recovery-backed purge-all."""
        return self.purge_trash().purged_count

    # ── Random Bookmark Rediscovery (inspired by Buku) ──────────────────
    def get_random_bookmark(self, exclude_trash: bool = True) -> Optional[Bookmark]:
        """Get a random bookmark for rediscovery.

        Trash is always hidden; archived bookmarks are excluded by default.
        """
        import random
        candidates = [
            bm for bm in self._iter_snapshot()
            if not (exclude_trash and bm.is_archived)
        ]
        return random.choice(candidates) if candidates else None

    # ── Batch Metadata Refresh (inspired by Buku's multi-threaded refresh) ──
    def batch_refresh_metadata(self, bookmark_ids: List[int] = None,
                                max_workers: int = 5,
                                progress_callback: Callable = None) -> int:
        """Re-fetch titles and descriptions for multiple bookmarks.

        If bookmark_ids is None, refreshes all bookmarks.
        Returns count of bookmarks updated.
        """
        self._ensure_storage_writable()
        try:
            max_workers = max(1, min(32, int(max_workers)))
        except (TypeError, ValueError):
            max_workers = 5

        if bookmark_ids is None:
            targets = self._iter_snapshot()
        else:
            normalized_ids = []
            for bid in bookmark_ids:
                try:
                    normalized_ids.append(int(bid))
                except (TypeError, ValueError):
                    continue
            targets = [
                self.bookmarks[bid]
                for bid in normalized_ids
                if bid in self.bookmarks and not self.bookmarks[bid].is_deleted
            ]

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
            existing = self._lookup_by_normalized_url(canonical)
            if existing is not None:
                return existing  # Already exists — return it rather than creating a duplicate

            bm = Bookmark(
                id=None, url=clean, title=title or clean,
                category=category, tags=tags or [], **kwargs
            )
            if bm.read_later and bm.read_later_position == 0:
                from bookmark_organizer_pro.services.read_later import ReadLaterQueue
                ReadLaterQueue.enqueue(bm, all_bookmarks=self._iter_snapshot())
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
        if not normalized:
            return None

        with self._lock:
            return self._lookup_by_normalized_url(normalized)
    
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
        self._ensure_storage_writable()
        with self._lock:
            cleaned = 0
            for bm in self.bookmarks.values():
                if bm.is_deleted:
                    continue
                clean_url = bm.clean_url()
                if clean_url != bm.url:
                    bm.url = clean_url
                    bm.modified_at = datetime.now().isoformat()
                    # clean_url() and normalize_url() disagree about blank
                    # query values, so a cleaned URL can land under a different
                    # index key. Reindex here or the bookmark becomes invisible
                    # to the duplicate check and can be added again.
                    self._index_bookmark(bm)
                    cleaned += 1
            if cleaned > 0:
                snapshot = list(self.bookmarks.values())
                self._save_snapshot(snapshot)
        return cleaned
    
    def merge_tags(self, source_tag: str, target_tag: str) -> int:
        """Merge one tag into another across all bookmarks"""
        self._ensure_storage_writable()
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
                if bm.is_deleted:
                    continue
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
            f.write(f'<!-- Exported by Bookmark Organizer Pro v{APP_VERSION} -->\n')
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
                    fields = structured_metadata_fields(bm)
                    if fields:
                        template = structured_metadata_payload(bm).get("template", "")
                        label = f"Structured metadata ({template})" if template else "Structured metadata"
                        f.write(f'  - {self._markdown_text(label)}:\n')
                        for key, value in sorted(fields.items()):
                            f.write(
                                f'    - {self._markdown_text(key)}: '
                                f'{self._markdown_text(format_structured_value(value))}\n'
                            )
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
        """Get comprehensive statistics from one consistent snapshot."""
        snapshot = self._iter_snapshot()
        total = len(snapshot)
        category_counts = {cat: 0 for cat in self.category_manager.categories}
        tag_counts: Dict[str, int] = {}
        domain_counts: Dict[str, int] = {}
        duplicate_candidates: Dict[str, List[Bookmark]] = {}
        age_dist = {"<7 days": 0, "7-30 days": 0, "1-6 months": 0, ">6 months": 0}
        pinned = archived = stale = broken = with_notes = with_tags = 0

        for bm in snapshot:
            category_counts[bm.category] = category_counts.get(bm.category, 0) + 1
            for tag in bm.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

            domain = bm.domain
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
            duplicate_candidates.setdefault(normalize_url(bm.url), []).append(bm)

            age = bm.age_days
            if age < 7:
                age_dist["<7 days"] += 1
            elif age < 30:
                age_dist["7-30 days"] += 1
            elif age < 180:
                age_dist["1-6 months"] += 1
            else:
                age_dist[">6 months"] += 1

            pinned += bool(bm.is_pinned)
            archived += bool(bm.is_archived)
            stale += age > 90 or bm.is_stale
            broken += not bm.is_valid
            with_notes += bool(bm.notes)
            with_tags += bool(bm.tags)

        duplicates = [bms for bms in duplicate_candidates.values() if len(bms) > 1]
        domain_stats = sorted(domain_counts.items(), key=lambda item: -item[1])[:10]
        
        return {
            "total_bookmarks": total,
            "total_categories": len(self.category_manager.categories),
            "total_tags": len(tag_counts),
            "category_counts": category_counts,
            "tag_counts": dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:20]),
            "top_domains": domain_stats,
            "duplicate_groups": len(duplicates),
            "duplicate_bookmarks": sum(len(bms) - 1 for bms in duplicates),
            "uncategorized": category_counts.get("Uncategorized / Needs Review", 0),
            "pinned": pinned,
            "archived": archived,
            "stale": stale,
            "broken": broken,
            "age_distribution": age_dist,
            "with_notes": with_notes,
            "with_tags": with_tags,
        }
