"""Dry-run fidelity reports and reversible competitor migrations."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.utils import normalize_url


SUPPORTED_MIGRATION_SOURCES = ("linkwarden", "karakeep", "raindrop", "readwise")


@dataclass(frozen=True)
class MigrationReport:
    source: str
    source_sha256: str
    total_records: int
    importable: int
    duplicates: int
    invalid: int
    preserved: Mapping[str, int] = field(default_factory=dict)
    transformed: Mapping[str, int] = field(default_factory=dict)
    unsupported: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "source_sha256": self.source_sha256,
            "total_records": self.total_records,
            "importable": self.importable,
            "duplicates": self.duplicates,
            "invalid": self.invalid,
            "preserved": dict(sorted(self.preserved.items())),
            "transformed": dict(sorted(self.transformed.items())),
            "unsupported": dict(sorted(self.unsupported.items())),
        }


@dataclass(frozen=True)
class MigrationPlan:
    bookmarks: tuple[Bookmark, ...]
    report: MigrationReport


@dataclass(frozen=True)
class MigrationResult:
    added: int
    duplicates: int
    safepoint: str
    report: MigrationReport


def _items_from_json(path: Path, source: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError(f"{source} export must contain a JSON object or list")
    keys = {
        "linkwarden": ("links", "bookmarks", "data"),
        "karakeep": ("bookmarks", "links", "data", "items"),
    }[source]
    for key in keys:
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        if isinstance(items, dict):
            nested = items.get("bookmarks") or items.get("links") or items.get("items")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    raise ValueError(f"{source} export does not contain a supported bookmark list")


def _items_from_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _pick(item: Mapping, *keys, default=""):
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _tags(value) -> list[str]:
    if isinstance(value, list):
        output = []
        for item in value:
            if isinstance(item, dict):
                item = _pick(item, "name", "label", "title")
            text = str(item or "").strip()
            if text:
                output.append(text)
        return output
    text = str(value or "")
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]


def _category(value) -> tuple[str, str]:
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        parent = _pick(value, "parentName", "parent", default="")
        name = _pick(value, "name", "title", "label", default="")
        if isinstance(parent, dict):
            parent = _pick(parent, "name", "title")
        return str(name or "Uncategorized / Needs Review"), str(parent or "")
    text = str(value or "").strip()
    if "/" in text:
        parent, name = (part.strip() for part in text.rsplit("/", 1))
        return name, parent
    return text or "Uncategorized / Needs Review", ""


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "archived"}


def _known_keys(source: str) -> set[str]:
    common = {
        "id", "url", "link", "title", "name", "description", "excerpt", "note", "notes",
        "tags", "tagNames", "createdAt", "created_at", "created", "saved_at", "Saved date",
        "updatedAt", "updated_at", "modified_at", "collection", "collections", "folder", "list",
        "lists", "isArchived", "archived", "is_archived", "isRead", "read", "read_later",
        "sourceId", "source_id", "URL", "Title", "Tags", "Document note", "Note", "Category",
        "highlights", "Highlights", "document_id", "Document ID", "status", "type",
    }
    if source == "karakeep":
        common |= {"favourited", "isFavorite", "content", "assets", "summary"}
    if source == "linkwarden":
        common |= {"preview", "image", "readDuration", "collectionId"}
    return common


def _convert_item(source: str, item: Mapping, index: int, counters: dict[str, Counter]):
    url = str(_pick(item, "url", "link", "URL") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    title = str(_pick(item, "title", "name", "Title", default=url))
    tags_value = _pick(item, "tags", "tagNames", "Tags", default=[])
    collection = _pick(item, "collection", "collections", "folder", "list", "lists", "Category")
    category, parent_category = _category(collection)
    notes = str(_pick(item, "note", "notes", "Document note", "Note", default=""))
    description = str(_pick(item, "description", "excerpt", "summary", default=""))
    created = str(_pick(item, "createdAt", "created_at", "created", "saved_at", "Saved date", default=""))
    modified = str(_pick(item, "updatedAt", "updated_at", "modified_at", default=created))
    source_id = str(_pick(item, "id", "sourceId", "source_id", "document_id", "Document ID", default=""))
    archived_key = next((key for key in ("isArchived", "archived", "is_archived", "status") if key in item), "")
    read_key = next((key for key in ("isRead", "read", "read_later") if key in item), "")
    archived_value = item.get(archived_key) if archived_key else ""
    read_value = item.get(read_key) if read_key else ""

    for field_name, value in {
        "url": url, "title": title, "tags": tags_value, "notes": notes,
        "dates": created or modified, "folders_or_lists": collection,
        "archive_state": archived_value if archived_key else "",
        "read_state": read_value if read_key else "",
    }.items():
        if value not in (None, "", [], {}) or (
            field_name == "archive_state" and archived_key
        ) or (field_name == "read_state" and read_key):
            counters["preserved"][field_name] += 1
    if collection not in (None, "", [], {}):
        counters["transformed"]["folders_or_lists_to_category"] += 1
    if source_id:
        counters["transformed"]["source_id_to_custom_data"] += 1
    for key, value in item.items():
        if key not in _known_keys(source) and value not in (None, "", [], {}):
            counters["unsupported"][str(key)] += 1
    for key in ("highlights", "Highlights"):
        value = item.get(key)
        if value not in (None, "", [], {}):
            count = len(value) if isinstance(value, list) else 1
            counters["unsupported"]["highlights_without_text_offsets"] += count
    for key in ("assets", "content", "preview", "image", "cover", "readDuration"):
        if item.get(key) not in (None, "", [], {}):
            counters["unsupported"][key] += 1

    custom_data = {
        "migration": {
            "source": source,
            "source_id": source_id or f"row-{index + 1}",
            "archived": _truth(archived_value) if archived_key else None,
            "read": _truth(read_value) if read_key and read_key != "read_later" else None,
        }
    }
    read_later = _truth(read_value) if read_key == "read_later" else (
        not _truth(read_value) if read_key else False
    )
    return Bookmark(
        id=None,
        url=url,
        title=title,
        category=category,
        parent_category=parent_category,
        tags=_tags(tags_value),
        notes=notes,
        description=description,
        created_at=created,
        modified_at=modified,
        add_date=created,
        is_archived=_truth(archived_value),
        read_later=read_later,
        source_file=f"{source}-migration",
        custom_data=custom_data,
    )


def preflight_migration(
    source: str,
    path: str | Path,
    *,
    existing_urls: Iterable[str] = (),
) -> MigrationPlan:
    """Parse a competitor export without mutating the library."""
    source = str(source).strip().lower()
    if source not in SUPPORTED_MIGRATION_SOURCES:
        raise ValueError(f"unsupported migration source: {source}")
    source_path = Path(path)
    raw = source_path.read_bytes()
    items = _items_from_json(source_path, source) if source in {"linkwarden", "karakeep"} else _items_from_csv(source_path)
    counters = {name: Counter() for name in ("preserved", "transformed", "unsupported")}
    existing = {normalize_url(url) for url in existing_urls}
    seen = set(existing)
    bookmarks = []
    invalid = duplicates = 0
    for index, item in enumerate(items):
        bookmark = _convert_item(source, item, index, counters)
        if bookmark is None:
            invalid += 1
            continue
        canonical = normalize_url(bookmark.url)
        if not canonical or canonical in seen:
            duplicates += 1
            continue
        seen.add(canonical)
        bookmarks.append(bookmark)
    report = MigrationReport(
        source=source,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        total_records=len(items),
        importable=len(bookmarks),
        duplicates=duplicates,
        invalid=invalid,
        preserved=counters["preserved"],
        transformed=counters["transformed"],
        unsupported=counters["unsupported"],
    )
    return MigrationPlan(tuple(bookmarks), report)


def apply_migration(manager, plan: MigrationPlan) -> MigrationResult:
    """Apply a preflighted plan once, guarded by a restorable safepoint."""
    safepoint = manager.create_safepoint(f"pre-{plan.report.source}-migration")
    if not safepoint:
        manager.save_bookmarks()
        safepoint = manager.create_safepoint(f"pre-{plan.report.source}-migration")
    if not safepoint:
        raise RuntimeError("could not create a pre-migration safepoint")
    existing = {normalize_url(bookmark.url) for bookmark in manager.get_all_bookmarks()}
    added = duplicates = 0
    for bookmark in plan.bookmarks:
        canonical = normalize_url(bookmark.url)
        if canonical in existing:
            duplicates += 1
            continue
        manager.add_bookmark(bookmark, save=False)
        existing.add(canonical)
        added += 1
    if added:
        manager.save_bookmarks()
    return MigrationResult(added, duplicates, str(safepoint), plan.report)
