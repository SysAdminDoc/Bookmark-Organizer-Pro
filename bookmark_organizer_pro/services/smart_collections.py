"""Smart Collections — saved filter rules that auto-populate.

A SmartCollection is a named set of filter criteria (tags, domains, date
ranges, content types, keywords) that dynamically matches bookmarks. Unlike
static categories, smart collections update automatically when bookmarks
change. Powered by the same StructuredQuery evaluation used by nl_query.py.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark

SMART_COLLECTIONS_FILE = DATA_DIR / "smart_collections.json"


@dataclass
class SmartCollectionFilter:
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    content_types: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    after: str = ""
    before: str = ""
    read_later_only: bool = False
    has_snapshot: bool = False


@dataclass
class SmartCollection:
    id: str
    name: str
    icon: str = ""
    filters: SmartCollectionFilter = field(default_factory=SmartCollectionFilter)
    created_at: str = ""
    modified_at: str = ""

    def matches(self, bookmark: Bookmark) -> bool:
        f = self.filters

        if f.tags:
            bm_tags = {t.lower() for t in bookmark.tags}
            if not any(t.lower() in bm_tags for t in f.tags):
                return False

        if f.categories:
            cat_lower = bookmark.category.lower()
            parent_lower = bookmark.parent_category.lower()
            if not any(c.lower() == cat_lower or c.lower() == parent_lower for c in f.categories):
                return False

        if f.domains:
            domain = bookmark.domain.lower()
            if not any(d.lower() in domain for d in f.domains):
                return False

        if f.content_types:
            if bookmark.content_type.lower() not in {ct.lower() for ct in f.content_types}:
                return False

        if f.keywords:
            haystack = f"{bookmark.title} {bookmark.url} {bookmark.description} {bookmark.notes}".lower()
            if not any(kw.lower() in haystack for kw in f.keywords):
                return False

        if f.after:
            try:
                cutoff = datetime.fromisoformat(f.after.replace("Z", "+00:00")).replace(tzinfo=None)
                created = datetime.fromisoformat(bookmark.created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                if created < cutoff:
                    return False
            except (ValueError, TypeError):
                pass

        if f.before:
            try:
                cutoff = datetime.fromisoformat(f.before.replace("Z", "+00:00")).replace(tzinfo=None)
                created = datetime.fromisoformat(bookmark.created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                if created > cutoff:
                    return False
            except (ValueError, TypeError):
                pass

        if f.read_later_only and not bookmark.read_later:
            return False

        if f.has_snapshot and not bookmark.snapshot_path:
            return False

        return True

    def evaluate(self, bookmarks: List[Bookmark]) -> List[Bookmark]:
        return [bm for bm in bookmarks if self.matches(bm)]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "icon": self.icon,
            "filters": asdict(self.filters),
            "created_at": self.created_at, "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SmartCollection":
        filters_data = d.get("filters", {})
        filters = SmartCollectionFilter(
            tags=filters_data.get("tags", []),
            categories=filters_data.get("categories", []),
            domains=filters_data.get("domains", []),
            content_types=filters_data.get("content_types", []),
            keywords=filters_data.get("keywords", []),
            after=str(filters_data.get("after") or ""),
            before=str(filters_data.get("before") or ""),
            read_later_only=bool(filters_data.get("read_later_only")),
            has_snapshot=bool(filters_data.get("has_snapshot")),
        )
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex),
            name=str(d.get("name") or "Untitled"),
            icon=str(d.get("icon") or ""),
            filters=filters,
            created_at=str(d.get("created_at") or datetime.now().isoformat()),
            modified_at=str(d.get("modified_at") or datetime.now().isoformat()),
        )


class SmartCollectionManager:
    """CRUD + evaluation for smart collections."""

    def __init__(self, filepath: Path = SMART_COLLECTIONS_FILE):
        self.filepath = Path(filepath)
        self._lock = threading.RLock()
        self._collections: Dict[str, SmartCollection] = {}
        self._load()

    def _load(self):
        if not self.filepath.exists():
            return
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(f"Could not load smart collections: {exc}")
            return
        with self._lock:
            self._collections = {}
            for d in data if isinstance(data, list) else []:
                try:
                    sc = SmartCollection.from_dict(d)
                    self._collections[sc.id] = sc
                except Exception as exc:
                    log.warning(f"Bad smart collection entry: {exc}")

    def _save(self):
        with self._lock:
            payload = [sc.to_dict() for sc in self._collections.values()]
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.filepath.parent, suffix=".tmp", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.filepath)
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise

    def create(self, name: str, filters: SmartCollectionFilter,
               icon: str = "") -> SmartCollection:
        now = datetime.now().isoformat()
        sc = SmartCollection(
            id=uuid.uuid4().hex, name=name, icon=icon,
            filters=filters, created_at=now, modified_at=now,
        )
        with self._lock:
            self._collections[sc.id] = sc
        self._save()
        return sc

    def delete(self, collection_id: str) -> bool:
        with self._lock:
            if collection_id not in self._collections:
                return False
            del self._collections[collection_id]
        self._save()
        return True

    def get(self, collection_id: str) -> Optional[SmartCollection]:
        with self._lock:
            return self._collections.get(collection_id)

    def list_all(self) -> List[SmartCollection]:
        with self._lock:
            return list(self._collections.values())

    def evaluate(self, collection_id: str,
                 bookmarks: List[Bookmark]) -> List[Bookmark]:
        with self._lock:
            sc = self._collections.get(collection_id)
        if sc is None:
            return []
        return sc.evaluate(bookmarks)

    def evaluate_all(self, bookmarks: List[Bookmark]) -> Dict[str, List[Bookmark]]:
        with self._lock:
            collections = list(self._collections.values())
        return {
            sc.id: sc.evaluate(bookmarks)
            for sc in collections
        }
