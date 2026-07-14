"""Smart Collections — saved filter rules that auto-populate.

A SmartCollection is a named set of filter criteria (tags, domains, date
ranges, content types, keywords) that dynamically matches bookmarks. Unlike
static categories, smart collections update automatically when bookmarks
change. Powered by the same StructuredQuery evaluation used by nl_query.py.
"""

from __future__ import annotations

from copy import deepcopy
import ipaddress
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentStore,
    require_list_document,
)

SMART_COLLECTIONS_FILE = DATA_DIR / "smart_collections.json"
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LIST_FILTER_FIELDS = ("tags", "categories", "domains", "content_types", "keywords")


def _parse_datetime(value: str, field_name: str) -> datetime | None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO-8601 date or timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_domain(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("domains entries must be strings")
    domain = value.strip().lower().rstrip(".")
    if not domain or any(character in domain for character in "/@"):
        raise ValueError(f"Invalid domain filter: {value!r}")
    try:
        return ipaddress.ip_address(domain.strip("[]")).compressed
    except ValueError:
        pass
    if ":" in domain:
        raise ValueError(f"Invalid domain filter: {value!r}")
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"Invalid domain filter: {value!r}") from exc
    if len(domain) > 253 or any(not _DOMAIN_LABEL.fullmatch(label) for label in domain.split(".")):
        raise ValueError(f"Invalid domain filter: {value!r}")
    return domain


def _domain_matches(host: str, expected: str) -> bool:
    try:
        normalized_host = _normalize_domain(host)
        normalized_expected = _normalize_domain(expected)
    except ValueError:
        return False
    return normalized_host == normalized_expected or normalized_host.endswith(
        f".{normalized_expected}"
    )


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


def validate_smart_collection_filter(filters: SmartCollectionFilter) -> SmartCollectionFilter:
    """Return a normalized filter or raise before it can broaden a saved view."""
    if not isinstance(filters, SmartCollectionFilter):
        raise ValueError("filters must be a SmartCollectionFilter")
    normalized: dict = {}
    for field_name in _LIST_FILTER_FIELDS:
        values = getattr(filters, field_name)
        if not isinstance(values, list):
            raise ValueError(f"{field_name} must be a list of strings")
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} entries must be non-empty strings")
            item = _normalize_domain(value) if field_name == "domains" else value.strip()
            identity = item.casefold()
            if identity not in seen:
                cleaned.append(item)
                seen.add(identity)
        normalized[field_name] = cleaned
    for field_name in ("read_later_only", "has_snapshot"):
        value = getattr(filters, field_name)
        if not isinstance(value, bool):
            raise ValueError(f"{field_name} must be a boolean")
        normalized[field_name] = value
    after = filters.after.strip() if isinstance(filters.after, str) else filters.after
    before = filters.before.strip() if isinstance(filters.before, str) else filters.before
    after_dt = _parse_datetime(after, "after")
    before_dt = _parse_datetime(before, "before")
    if after_dt is not None and before_dt is not None and after_dt > before_dt:
        raise ValueError("after must not be later than before")
    normalized["after"] = after
    normalized["before"] = before
    return SmartCollectionFilter(**normalized)


@dataclass(frozen=True)
class SmartCollectionDiagnostic:
    index: int
    collection_id: str
    name: str
    error: str

    @property
    def message(self) -> str:
        label = self.name or self.collection_id or f"entry {self.index + 1}"
        return f"Skipped invalid smart collection {label!r}: {self.error}"


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
            if not any(_domain_matches(domain, expected) for expected in f.domains):
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
                cutoff = _parse_datetime(f.after, "after")
                created = _parse_datetime(bookmark.created_at, "bookmark.created_at")
                if cutoff is None or created is None:
                    return False
                if created < cutoff:
                    return False
            except ValueError:
                return False

        if f.before:
            try:
                cutoff = _parse_datetime(f.before, "before")
                created = _parse_datetime(bookmark.created_at, "bookmark.created_at")
                if cutoff is None or created is None:
                    return False
                if created > cutoff:
                    return False
            except ValueError:
                return False

        if f.read_later_only and not bookmark.read_later:
            return False

        if f.has_snapshot and not bookmark.snapshot_path:
            return False

        return True

    def evaluate(self, bookmarks: List[Bookmark]) -> List[Bookmark]:
        return [bm for bm in bookmarks if self.matches(bm)]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "filters": asdict(self.filters),
            "created_at": self.created_at,
            "modified_at": self.modified_at,
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
        self._store = AtomicDocumentStore(
            self.filepath,
            schema="bookmark-organizer-pro/smart-collections",
            default_factory=list,
            validator=require_list_document,
        )
        self._revision = 0
        self._collections: Dict[str, SmartCollection] = {}
        self._committed_collections: Dict[str, SmartCollection] = {}
        self._quarantined_entries: list[dict] = []
        self._committed_quarantined_entries: list[dict] = []
        self._diagnostics: list[SmartCollectionDiagnostic] = []
        self._load()

    @property
    def storage_status(self):
        return self._store.status

    @property
    def diagnostics(self) -> list[SmartCollectionDiagnostic]:
        with self._lock:
            return list(self._diagnostics)

    def _load(self):
        data = self._store.load()
        self._revision = self._store.revision
        with self._lock:
            self._collections = {}
            self._quarantined_entries = []
            self._diagnostics = []
            for index, d in enumerate(data if isinstance(data, list) else []):
                try:
                    if not isinstance(d, dict):
                        raise ValueError("entry must be an object")
                    raw_filters = d.get("filters", {})
                    if not isinstance(raw_filters, dict):
                        raise ValueError("filters must be an object")
                    for field_name in _LIST_FILTER_FIELDS:
                        value = raw_filters.get(field_name, [])
                        if not isinstance(value, list):
                            raise ValueError(f"{field_name} must be a list of strings")
                    for field_name in ("read_later_only", "has_snapshot"):
                        value = raw_filters.get(field_name, False)
                        if not isinstance(value, bool):
                            raise ValueError(f"{field_name} must be a boolean")
                    sc = SmartCollection.from_dict(d)
                    sc.filters = validate_smart_collection_filter(sc.filters)
                    if sc.id in self._collections:
                        raise ValueError(f"duplicate collection ID: {sc.id}")
                    self._collections[sc.id] = sc
                except Exception as exc:
                    raw = deepcopy(d) if isinstance(d, dict) else {"value": deepcopy(d)}
                    self._quarantined_entries.append(raw)
                    diagnostic = SmartCollectionDiagnostic(
                        index=index,
                        collection_id=str(d.get("id") or "") if isinstance(d, dict) else "",
                        name=str(d.get("name") or "") if isinstance(d, dict) else "",
                        error=str(exc),
                    )
                    self._diagnostics.append(diagnostic)
                    log.warning(diagnostic.message)
            self._committed_collections = deepcopy(self._collections)
            self._committed_quarantined_entries = deepcopy(self._quarantined_entries)

    def _save(self):
        with self._lock:
            payload = [sc.to_dict() for sc in self._collections.values()]
            payload.extend(deepcopy(self._quarantined_entries))
            try:
                revision = self._store.save(payload, expected_revision=self._revision)
            except Exception:
                self._collections = deepcopy(self._committed_collections)
                self._quarantined_entries = deepcopy(self._committed_quarantined_entries)
                raise
            self._revision = revision
            self._committed_collections = deepcopy(self._collections)
            self._committed_quarantined_entries = deepcopy(self._quarantined_entries)

    def create(self, name: str, filters: SmartCollectionFilter, icon: str = "") -> SmartCollection:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Smart collection name is required")
        filters = validate_smart_collection_filter(filters)
        now = datetime.now(timezone.utc).isoformat()
        sc = SmartCollection(
            id=uuid.uuid4().hex,
            name=name.strip(),
            icon=str(icon or "").strip(),
            filters=filters,
            created_at=now,
            modified_at=now,
        )
        with self._lock:
            self._collections[sc.id] = sc
            self._save()
            return deepcopy(sc)

    def update(
        self,
        collection_id: str,
        *,
        name: str | None = None,
        filters: SmartCollectionFilter | None = None,
        icon: str | None = None,
    ) -> Optional[SmartCollection]:
        with self._lock:
            current = self._collections.get(collection_id)
            if current is None:
                return None
            candidate = deepcopy(current)
            if name is not None:
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("Smart collection name is required")
                candidate.name = name.strip()
            if filters is not None:
                candidate.filters = validate_smart_collection_filter(filters)
            if icon is not None:
                candidate.icon = str(icon).strip()
            candidate.modified_at = datetime.now(timezone.utc).isoformat()
            self._collections[collection_id] = candidate
            self._save()
            return deepcopy(candidate)

    def delete(self, collection_id: str) -> bool:
        with self._lock:
            if collection_id not in self._collections:
                return False
            del self._collections[collection_id]
            self._save()
            return True

    def get(self, collection_id: str) -> Optional[SmartCollection]:
        with self._lock:
            collection = self._collections.get(collection_id)
            return deepcopy(collection) if collection is not None else None

    def list_all(self) -> List[SmartCollection]:
        with self._lock:
            return deepcopy(list(self._collections.values()))

    def list_collections(self) -> List[SmartCollection]:
        """Compatibility alias used by the desktop report surface."""
        return self.list_all()

    def resolve(self, collection_id: str) -> Optional[SmartCollection]:
        """Resolve an exact ID or one unambiguous displayed prefix."""
        with self._lock:
            if collection_id in self._collections:
                return deepcopy(self._collections[collection_id])
            matches = [
                collection for key, collection in self._collections.items()
                if key.startswith(collection_id)
            ]
            return deepcopy(matches[0]) if len(matches) == 1 else None

    def evaluate(self, collection_id: str, bookmarks: List[Bookmark]) -> List[Bookmark]:
        with self._lock:
            sc = deepcopy(self._collections.get(collection_id))
        if sc is None:
            return []
        return sc.evaluate(bookmarks)

    def evaluate_all(self, bookmarks: List[Bookmark]) -> Dict[str, List[Bookmark]]:
        with self._lock:
            collections = deepcopy(list(self._collections.values()))
        return {sc.id: sc.evaluate(bookmarks) for sc in collections}
