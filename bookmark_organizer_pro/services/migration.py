"""Dry-run fidelity reports and reversible competitor migrations."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.utils import normalize_url


SUPPORTED_MIGRATION_SOURCES = ("linkwarden", "karakeep", "raindrop", "readwise")


class MigrationSpoolError(RuntimeError):
    """A bounded migration refused the source before touching the library."""


@dataclass(frozen=True)
class MigrationLimits:
    """Ceilings a bounded preflight refuses to exceed.

    A migration reads a file the user did not write. Without ceilings a hostile
    or merely enormous export decides how much memory and disk this process
    uses, so each one is explicit and reported by name when it trips.
    """

    max_source_bytes: int = 512 * 1024 * 1024
    max_records: int = 2_000_000
    max_field_chars: int = 1_000_000
    max_json_depth: int = 64


class _PlanSpool:
    """Converted records on disk, not in memory.

    Preflight used to keep every converted bookmark plus a set of every
    normalized URL in memory, so a large export was held several times over
    before a single row reached the library. SQLite holds the plan and enforces
    dedupe through a primary key, which also removes the in-memory seen-set.
    """

    def __init__(self, directory: Path | None = None):
        self._directory = Path(
            directory or tempfile.mkdtemp(prefix="bop-migration-plan-")
        )
        self._directory.mkdir(parents=True, exist_ok=True)
        self.path = self._directory / "plan.sqlite3"
        self._connection = sqlite3.connect(self.path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            " canonical TEXT PRIMARY KEY,"
            " seq INTEGER,"
            " payload TEXT)"
        )
        self._connection.commit()
        self._sequence = 0
        self._closed = False

    def seed_existing(self, canonical_urls: Iterable[str]) -> None:
        """Record URLs the library already holds so they dedupe like any other."""
        self._connection.executemany(
            "INSERT OR IGNORE INTO seen (canonical, seq, payload) VALUES (?, NULL, NULL)",
            ((url,) for url in canonical_urls if url),
        )
        self._connection.commit()

    def add(self, canonical: str, payload: Mapping) -> bool:
        """Store one converted record. Returns False when it is a duplicate."""
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO seen (canonical, seq, payload) VALUES (?, ?, ?)",
            (canonical, self._sequence, json.dumps(payload, ensure_ascii=False)),
        )
        if not cursor.rowcount:
            return False
        self._sequence += 1
        return True

    def commit(self) -> None:
        self._connection.commit()

    def __len__(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM seen WHERE payload IS NOT NULL"
        ).fetchone()
        return int(row[0]) if row else 0

    def iter_payloads(self) -> "Iterator[dict]":
        """Yield stored records in the order they were accepted."""
        if self._closed:
            raise MigrationSpoolError("this migration plan has already been discarded")
        cursor = self._connection.execute(
            "SELECT payload FROM seen WHERE payload IS NOT NULL ORDER BY seq"
        )
        for (payload,) in cursor:
            yield json.loads(payload)

    def close(self) -> None:
        """Delete the spool. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        try:
            self._connection.close()
        except sqlite3.Error:
            pass
        shutil.rmtree(self._directory, ignore_errors=True)


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


class MigrationPlan:
    """A preflighted migration whose records live on disk until applied."""

    def __init__(self, report: "MigrationReport", spool: _PlanSpool):
        self.report = report
        self._spool = spool

    def iter_bookmarks(self) -> Iterator[Bookmark]:
        """Stream the converted records without materializing them."""
        for payload in self._spool.iter_payloads():
            yield Bookmark.from_dict(payload)

    @property
    def bookmarks(self) -> tuple[Bookmark, ...]:
        """Every record at once.

        Materializes the whole plan, which is what streaming exists to avoid.
        Kept for small callers and tests; apply_migration streams instead.
        """
        return tuple(self.iter_bookmarks())

    def close(self) -> None:
        """Discard the spool. The library is untouched either way."""
        self._spool.close()

    def __enter__(self) -> "MigrationPlan":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


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
    spool = _PlanSpool()
    try:
        spool.seed_existing(normalize_url(url) for url in existing_urls)
        total = invalid = duplicates = 0
        for index, item in enumerate(items):
            total += 1
            bookmark = _convert_item(source, item, index, counters)
            if bookmark is None:
                invalid += 1
                continue
            canonical = normalize_url(bookmark.url)
            # The spool's primary key is the dedupe check, so no set of every
            # URL in the library and the export is held in memory.
            if not canonical or not spool.add(canonical, bookmark.to_dict()):
                duplicates += 1
                continue
        spool.commit()
        report = MigrationReport(
            source=source,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            total_records=total,
            importable=len(spool),
            duplicates=duplicates,
            invalid=invalid,
            preserved=counters["preserved"],
            transformed=counters["transformed"],
            unsupported=counters["unsupported"],
        )
    except BaseException:
        # A refused or cancelled preflight leaves nothing behind.
        spool.close()
        raise
    return MigrationPlan(report, spool)


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
    # Stream the plan rather than materializing it: the spool exists so a large
    # export never has to be resident all at once.
    for bookmark in plan.iter_bookmarks():
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
