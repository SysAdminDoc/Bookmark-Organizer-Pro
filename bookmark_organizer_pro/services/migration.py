"""Dry-run fidelity reports and reversible competitor migrations."""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
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

    Each one is checked as the source streams past, so an export that trips a
    ceiling is refused partway through rather than after it has been read.
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
        # This database is scratch: it is deleted on close and never survives a
        # run, so paying for durability on every write buys nothing and made a
        # large export spend most of its time in fsync.
        self._connection.execute("PRAGMA synchronous=OFF")
        # Two tables, deliberately. Keeping the record body in the same table
        # as the TEXT primary key made every insert rewrite index pages around
        # a multi-kilobyte payload, and the cost grew with the rows already
        # stored: a 250 MB export with long notes spent minutes there. The
        # dedupe index now holds only URLs, and bodies append to a rowid table.
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            " canonical TEXT PRIMARY KEY,"
            " seq INTEGER)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS payloads ("
            " seq INTEGER PRIMARY KEY,"
            " payload TEXT NOT NULL)"
        )
        # Candidate containers from a JSON export, kept only long enough to
        # rank them. Dropped before conversion begins.
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS raw ("
            " seq INTEGER PRIMARY KEY,"
            " prefix TEXT NOT NULL,"
            " payload TEXT NOT NULL)"
        )
        self._connection.commit()
        self._sequence = 0
        self._raw_sequence = 0
        self._closed = False
        # Cursors handed to callers. A generator suspended over one keeps the
        # database file open on Windows, and rmtree then fails silently and
        # leaves the spool behind, which is the leak this class exists to
        # avoid. They are closed explicitly before the connection is.
        self._cursors: list[sqlite3.Cursor] = []

    def seed_existing(self, canonical_urls: Iterable[str]) -> None:
        """Record URLs the library already holds so they dedupe like any other."""
        self._connection.executemany(
            "INSERT OR IGNORE INTO seen (canonical, seq) VALUES (?, NULL)",
            ((url,) for url in canonical_urls if url),
        )
        self._connection.commit()

    def add(self, canonical: str, payload: Mapping) -> bool:
        """Store one converted record. Returns False when it is a duplicate."""
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO seen (canonical, seq) VALUES (?, ?)",
            (canonical, self._sequence),
        )
        if not cursor.rowcount:
            return False
        self._connection.execute(
            "INSERT INTO payloads (seq, payload) VALUES (?, ?)",
            (self._sequence, json.dumps(payload, ensure_ascii=False)),
        )
        self._sequence += 1
        return True

    def add_raw(self, prefix: str, payload: Mapping) -> None:
        """Keep one candidate-container record until the ranking is decided."""
        self._connection.execute(
            "INSERT INTO raw (seq, prefix, payload) VALUES (?, ?, ?)",
            (self._raw_sequence, prefix, json.dumps(payload, ensure_ascii=False)),
        )
        self._raw_sequence += 1

    def raw_prefixes(self) -> dict[str, int]:
        """How many records each candidate container held."""
        return {
            str(prefix): int(count)
            for prefix, count in self._connection.execute(
                "SELECT prefix, COUNT(*) FROM raw GROUP BY prefix"
            )
        }

    def iter_raw(self, prefix: str) -> "Iterator[dict]":
        """Yield one container's records in document order."""
        cursor = self._connection.execute(
            "SELECT payload FROM raw WHERE prefix = ? ORDER BY seq", (prefix,)
        )
        self._cursors.append(cursor)
        try:
            for (payload,) in cursor:
                yield json.loads(payload)
        finally:
            self._release(cursor)

    def discard_raw(self) -> None:
        """Drop the candidate containers once their records are converted."""
        self._connection.execute("DELETE FROM raw")
        self._connection.commit()

    def commit(self) -> None:
        self._connection.commit()

    def __len__(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM payloads").fetchone()
        return int(row[0]) if row else 0

    def iter_payloads(self) -> "Iterator[dict]":
        """Yield stored records in the order they were accepted."""
        if self._closed:
            raise MigrationSpoolError("this migration plan has already been discarded")
        cursor = self._connection.execute(
            "SELECT payload FROM payloads ORDER BY seq"
        )
        self._cursors.append(cursor)
        try:
            for (payload,) in cursor:
                yield json.loads(payload)
        finally:
            self._release(cursor)

    def _release(self, cursor: sqlite3.Cursor) -> None:
        with contextlib.suppress(sqlite3.Error, ValueError):
            cursor.close()
        with contextlib.suppress(ValueError):
            self._cursors.remove(cursor)

    def close(self) -> None:
        """Delete the spool. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        for cursor in list(self._cursors):
            self._release(cursor)
        try:
            self._connection.close()
        except sqlite3.Error:
            pass
        shutil.rmtree(self._directory, ignore_errors=True)
        if self._directory.exists():
            # A stale handle on Windows can outlive the close by a moment. The
            # spool holds a full copy of the user's export, so a silent failure
            # here is the leak, not a tidiness problem.
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


class _HashingReader(io.RawIOBase):
    """A file wrapper that digests the source while the parser consumes it.

    Preflight used to read the file once for its hash and again to parse it.
    Reading once and hashing on the way through means a 250 MB export is never
    resident, and the recorded digest still covers every byte the parse saw.

    It is a real ``RawIOBase`` so that both ijson and ``TextIOWrapper`` can
    drive it; implementing ``read`` alone is not enough for the latter.
    """

    def __init__(self, handle):
        super().__init__()
        self._handle = handle
        self._digest = hashlib.sha256()

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        chunk = self._handle.read(len(buffer))
        if not chunk:
            return 0
        self._digest.update(chunk)
        buffer[: len(chunk)] = chunk
        return len(chunk)

    @property
    def hexdigest(self) -> str:
        return self._digest.hexdigest()


# Where each export keeps its bookmark array, in the order a container is
# preferred when a document offers more than one. A top-level array is the
# empty prefix; ijson names an array member "<prefix>.item".
#
# The order matters and is not decoration. A Karakeep export that carries an
# empty "links" alongside its real "bookmarks" must resolve to "bookmarks", and
# picking whichever container appears first in the file instead produces a
# migration that silently imports nothing.
_JSON_CONTAINER_KEYS = {
    "linkwarden": ("links", "bookmarks", "data"),
    "karakeep": ("bookmarks", "links", "data", "items"),
}
_JSON_NESTED_KEYS = ("bookmarks", "links", "items")


def _json_prefix_priority(source: str) -> tuple[str, ...]:
    """Every container prefix for a source, most preferred first.

    Each top-level key is tried before its nested forms, matching the one-level
    descent the materializing parser did under whichever key it settled on.
    """
    order = [""]
    for key in _JSON_CONTAINER_KEYS[source]:
        order.append(key)
        order.extend(f"{key}.{nested}" for nested in _JSON_NESTED_KEYS if nested != key)
    return tuple(order)


def _spool_json_candidates(reader, source: str, spool: "_PlanSpool") -> str:
    """Read the export once, keeping every candidate container on disk.

    A single event pass cannot know whether a better-ranked container appears
    later in the file, and re-reading to find out would mean parsing a 250 MB
    export twice. So every candidate array's records are spooled as raw JSON
    tagged with their prefix, the ranking picks the winner afterwards, and the
    losers are discarded. Nothing is held in memory beyond one record.
    """
    import ijson
    from ijson.common import ObjectBuilder

    candidates = set(_json_prefix_priority(source))
    member_prefix: str | None = None
    active_prefix = ""
    builder: ObjectBuilder | None = None
    depth = 0
    seen_any = False

    for prefix, event, value in ijson.parse(reader):
        if builder is None:
            if event == "start_array" and prefix in candidates:
                active_prefix = prefix
                member_prefix = f"{prefix}.item" if prefix else "item"
                seen_any = True
                continue
            # Only whole objects are records; a stray scalar in the array is
            # skipped the way the list comprehension used to skip it.
            if member_prefix is not None and prefix == member_prefix and event == "start_map":
                builder = ObjectBuilder()
                depth = 0
            else:
                continue
        if event in ("start_map", "start_array"):
            depth += 1
        elif event in ("end_map", "end_array"):
            depth -= 1
        builder.event(event, value)
        if depth == 0:
            spool.add_raw(active_prefix, builder.value)
            builder = None

    if not seen_any:
        raise ValueError(f"{source} export does not contain a supported bookmark list")
    spool.commit()
    stored = spool.raw_prefixes()
    for prefix in _json_prefix_priority(source):
        if stored.get(prefix):
            return prefix
    # Every candidate container was present but empty. That is a real export
    # with nothing in it, not an unrecognized one.
    return next(iter(stored), "")


def _reject_oversized_fields(item: Mapping, limits: "MigrationLimits", index: int) -> None:
    """Refuse a record carrying a field too large to be a bookmark field.

    A single field is what a hostile export inflates: one 400 MB title costs
    the same as a million records and passes a record count untouched.
    """
    stack = [(item, 0)]
    while stack:
        value, depth = stack.pop()
        if depth > limits.max_json_depth:
            raise MigrationSpoolError(
                f"max_json_depth exceeded at record {index}: "
                f"nesting deeper than {limits.max_json_depth}"
            )
        if isinstance(value, str):
            if len(value) > limits.max_field_chars:
                raise MigrationSpoolError(
                    f"max_field_chars exceeded at record {index}: "
                    f"{len(value)} characters, limit {limits.max_field_chars}"
                )
        elif isinstance(value, Mapping):
            # Keys as well as values. An unknown key is interned into the
            # unsupported-field counter and kept for the whole run, so a
            # megabyte-long key costs more than a megabyte-long title.
            stack.extend((child, depth + 1) for child in value.keys())
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend((child, depth + 1) for child in value)


def _stream_csv_items(reader) -> "Iterator[dict]":
    """Yield each CSV row, decoding the hashed byte stream as it arrives."""
    return iter(csv.DictReader(io.TextIOWrapper(reader, encoding="utf-8-sig", newline="")))


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
    limits: "MigrationLimits | None" = None,
) -> MigrationPlan:
    """Parse a competitor export without mutating the library."""
    source = str(source).strip().lower()
    if source not in SUPPORTED_MIGRATION_SOURCES:
        raise ValueError(f"unsupported migration source: {source}")
    limits = limits or MigrationLimits()
    source_path = Path(path)
    # The whole file is read below, so its size is checked before that happens
    # rather than after the process has already committed the memory.
    size = source_path.stat().st_size
    if size > limits.max_source_bytes:
        raise MigrationSpoolError(
            f"max_source_bytes exceeded: {size} bytes, limit {limits.max_source_bytes}"
        )
    counters = {name: Counter() for name in ("preserved", "transformed", "unsupported")}
    spool = _PlanSpool()
    try:
        spool.seed_existing(normalize_url(url) for url in existing_urls)
        total = invalid = duplicates = 0
        with source_path.open("rb") as handle:
            reader = _HashingReader(handle)
            if source in {"linkwarden", "karakeep"}:
                chosen = _spool_json_candidates(reader, source, spool)
                items: "Iterator[Mapping]" = spool.iter_raw(chosen)
            else:
                items = _stream_csv_items(reader)
            for index, item in enumerate(items):
                total += 1
                if total > limits.max_records:
                    raise MigrationSpoolError(
                        f"max_records exceeded: more than {limits.max_records} records"
                    )
                _reject_oversized_fields(item, limits, index)
                bookmark = _convert_item(source, item, index, counters)
                if bookmark is None:
                    invalid += 1
                    continue
                canonical = normalize_url(bookmark.url)
                # The spool's primary key is the dedupe check, so no set of
                # every URL in the library and the export is held in memory.
                if not canonical or not spool.add(canonical, bookmark.to_dict()):
                    duplicates += 1
                    continue
            # Drain whatever the parser has not touched so the digest covers
            # every byte, not only the bytes up to the last record.
            while reader.read(1024 * 1024):
                pass
            source_sha256 = reader.hexdigest
        spool.discard_raw()
        spool.commit()
        report = MigrationReport(
            source=source,
            source_sha256=source_sha256,
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
