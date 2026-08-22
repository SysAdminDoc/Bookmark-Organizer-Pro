"""Importers added in v6.0: Pocket export, Readwise Reader CSV,
Pinboard JSON, Instapaper CSV/HTML, Reddit Saved JSON.

Each importer takes a path and yields Bookmark objects (without IDs); the
caller is responsible for dedupe and persistence via BookmarkManager.
"""

from __future__ import annotations

import csv
import html as html_module
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Tuple

from bookmark_organizer_pro.importers import (
    SessionImportStats,
    _iter_csv_rows,
    raise_csv_field_limit,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


raise_csv_field_limit()

# Metadata JSON in a real export is a few megabytes; a zip declares the
# uncompressed size of each member, so an absurd one is refused before it is
# read into memory.
MAX_ARCHIVE_MEMBER_BYTES = 50_000_000


def _ts(value) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(int(value)).isoformat()
        return str(value)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
class PocketExportImporter:
    """Mozilla Pocket export (HTML or JSON)."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        if p.suffix.lower() == ".json":
            return self._from_json(p)
        return self._from_html(p)

    def _from_html(self, p: Path) -> Iterator[Bookmark]:
        try:
            from bs4 import BeautifulSoup
        except Exception:
            log.error("Pocket HTML import requires beautifulsoup4")
            return iter(())
        soup = BeautifulSoup(p.read_text(encoding="utf-8", errors="ignore"),
                             "html.parser")
        out: List[Bookmark] = []
        for a in soup.find_all("a"):
            url = (a.get("href") or "").strip()
            if not url:
                continue
            tags_attr = (a.get("tags") or "").strip()
            tags = [t.strip() for t in tags_attr.split(",") if t.strip()]
            try:
                bm = Bookmark(
                    id=None,
                    url=url,
                    title=html_module.unescape(a.get_text(strip=True) or url),
                    add_date=_ts(a.get("time_added") or a.get("add_date")),
                    tags=tags,
                    source_file="pocket-export",
                )
                out.append(bm)
            except ValueError:
                continue
        return iter(out)

    def _from_json(self, p: Path) -> Iterator[Bookmark]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error(f"Pocket JSON parse failed: {exc}")
            return iter(())
        items = data.get("list", data) if isinstance(data, dict) else data
        out: List[Bookmark] = []
        if isinstance(items, dict):
            items = items.values()
        for item in items if isinstance(items, Iterable) else []:
            if not isinstance(item, dict):
                continue
            url = item.get("resolved_url") or item.get("given_url") or ""
            if not url:
                continue
            tags = []
            t = item.get("tags")
            if isinstance(t, dict):
                tags = list(t.keys())
            elif isinstance(t, list):
                tags = [str(x) for x in t]
            try:
                out.append(Bookmark(
                    id=None, url=str(url),
                    title=str(item.get("resolved_title") or
                              item.get("given_title") or url),
                    add_date=_ts(item.get("time_added")),
                    tags=tags,
                    source_file="pocket-export-json",
                ))
            except ValueError:
                continue
        return iter(out)


# ---------------------------------------------------------------------------
class ReadwiseReaderCSVImporter:
    """Readwise Reader CSV export."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        out: List[Bookmark] = []
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in _iter_csv_rows(reader):
                url = (row.get("URL") or row.get("url") or "").strip()
                if not url:
                    continue
                tags_field = row.get("Tags") or row.get("tags") or ""
                tags = [t.strip() for t in re.split(r"[,;]", tags_field) if t.strip()]
                try:
                    out.append(Bookmark(
                        id=None, url=url,
                        title=row.get("Title") or row.get("title") or url,
                        description=row.get("Document note") or row.get("Note") or "",
                        category=row.get("Category") or "",
                        tags=tags,
                        add_date=row.get("Saved date") or row.get("created_at") or "",
                        source_file="readwise-reader-csv",
                    ))
                except ValueError:
                    continue
        return iter(out)


# ---------------------------------------------------------------------------
class MappedCSVImporter:
    """Any CSV export with a URL column.

    Column names vary by product, so headers are matched case-insensitively
    against known aliases and an explicit mapping can override them. This
    covers Markwise (``Title,URL,Main Category,Sub Category,Added At``),
    start.me, and Pinboard CSV without a bespoke importer for each.
    """

    ALIASES = {
        "url": ("url", "href", "link", "address"),
        "title": ("title", "name", "description"),
        "category": ("sub category", "subcategory", "category", "folder", "collection"),
        "parent_category": ("main category", "parent category", "group"),
        "tags": ("tags", "labels", "keywords"),
        "notes": ("notes", "note", "comment", "excerpt", "document note"),
        "add_date": ("added at", "saved date", "created_at", "created", "date", "time"),
    }

    def __init__(self, mapping: dict | None = None):
        self.mapping = {k: str(v) for k, v in (mapping or {}).items() if v}
        self.stats = SessionImportStats()

    @classmethod
    def headers(cls, path: str) -> List[str]:
        """Read just the header row, for building a column mapping."""
        # utf-8-sig strips the BOM that Excel writes; without it the first
        # header becomes "﻿Title" and every title falls back to the URL.
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            for row in csv.reader(handle):
                return [str(cell).strip() for cell in row]
        return []

    @classmethod
    def suggest_mapping(cls, headers: Iterable[str]) -> dict:
        """Best-guess field -> column name from a header row."""
        lowered = {str(h).strip().lower(): str(h).strip() for h in headers if str(h).strip()}
        mapping = {}
        for field, aliases in cls.ALIASES.items():
            for alias in aliases:
                if alias in lowered:
                    mapping[field] = lowered[alias]
                    break
        return mapping

    def _value(self, row: dict, field: str) -> str:
        # Row keys are lower-cased, so an explicit mapping must be too.
        column = self.mapping.get(field, "").strip().lower()
        if column and column in row:
            return str(row.get(column) or "").strip()
        for alias in self.ALIASES.get(field, ()):
            if alias in row:
                return str(row.get(alias) or "").strip()
        return ""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        out: List[Bookmark] = []
        with p.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in _iter_csv_rows(reader, self.stats):
                row = {str(k or "").strip().lower(): (v or "") for k, v in raw.items()}
                url = self._value(row, "url")
                if not url:
                    self.stats.record("row has no URL column value")
                    continue
                if not url.startswith(("http://", "https://")):
                    self.stats.record("row URL was not http(s)")
                    continue
                tags = [t.strip() for t in re.split(r"[,;]", self._value(row, "tags")) if t.strip()]
                try:
                    out.append(Bookmark(
                        id=None,
                        url=url,
                        title=self._value(row, "title") or url,
                        category=self._value(row, "category"),
                        parent_category=self._value(row, "parent_category"),
                        tags=tags,
                        notes=self._value(row, "notes"),
                        add_date=self._value(row, "add_date"),
                        source_file="csv-import",
                    ))
                except ValueError as exc:
                    self.stats.record(f"invalid row: {str(exc)[:120]}")
        return iter(out)


# ---------------------------------------------------------------------------
class PinboardJSONImporter:
    """Pinboard `format=json` export."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return iter(())
        if not isinstance(data, list):
            return iter(())
        out: List[Bookmark] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            url = (item.get("href") or "").strip()
            if not url:
                continue
            tags_str = item.get("tags") or ""
            tags = [t.strip() for t in tags_str.split(" ") if t.strip()]
            try:
                out.append(Bookmark(
                    id=None, url=url,
                    title=item.get("description") or url,
                    description=item.get("extended") or "",
                    tags=tags,
                    add_date=item.get("time") or "",
                    source_file="pinboard-json",
                ))
            except ValueError:
                continue
        return iter(out)


# ---------------------------------------------------------------------------
class InstapaperImporter:
    """Instapaper CSV export (folder, URL, title, selection, timestamp)."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        out: List[Bookmark] = []
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in _iter_csv_rows(reader):
                if len(row) < 2:
                    continue
                # Header detection
                if row[0].lower() == "url" or row[0].lower() == "folder":
                    continue
                # Layout: URL,Title,Selection,Folder,Timestamp
                if "://" in row[0]:
                    url = row[0]
                    title = row[1] if len(row) > 1 else url
                    folder = row[3] if len(row) > 3 else ""
                else:
                    folder = row[0]
                    url = row[1]
                    title = row[2] if len(row) > 2 else url
                if not url:
                    continue
                try:
                    out.append(Bookmark(
                        id=None, url=url, title=title or url,
                        category=folder or "",
                        source_file="instapaper-csv",
                    ))
                except ValueError:
                    continue
        return iter(out)


# ---------------------------------------------------------------------------
class RedditSavedImporter:
    """Reddit `saved.json` from Reddit data export."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return iter(())
        children = []
        if isinstance(data, dict):
            children = data.get("data", {}).get("children", []) or []
        elif isinstance(data, list):
            children = data
        out: List[Bookmark] = []
        for child in children:
            if not isinstance(child, dict):
                continue
            d = child.get("data") if "data" in child else child
            if not isinstance(d, dict):
                continue
            url = d.get("url") or d.get("link") or ""
            permalink = d.get("permalink") or ""
            if permalink and not url:
                url = "https://www.reddit.com" + permalink
            if not url:
                continue
            title = d.get("title") or d.get("link_title") or url
            subreddit = d.get("subreddit") or ""
            tags = ["reddit"]
            if subreddit:
                tags.append(f"r/{subreddit}")
            try:
                out.append(Bookmark(
                    id=None, url=url, title=title,
                    category=f"Reddit / {subreddit}" if subreddit else "Reddit",
                    tags=tags,
                    add_date=_ts(d.get("created_utc") or d.get("created")),
                    source_file="reddit-saved",
                ))
            except ValueError:
                continue
        return iter(out)


class MatterImporter:
    """Import from Matter app CSV export.

    Matter exports a CSV with columns: Title, URL, Author, Tags, Status,
    Highlight Count, Note Count, Date Saved. All fields are optional except URL.
    """

    @staticmethod
    def from_path(path: str) -> List[Bookmark]:
        bookmarks = []
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in _iter_csv_rows(reader):
                    url = (row.get("URL") or row.get("url") or "").strip()
                    if not url or not url.startswith(("http://", "https://")):
                        continue
                    title = (row.get("Title") or row.get("title") or url).strip()
                    tags_raw = row.get("Tags") or row.get("tags") or ""
                    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
                    created = _ts(row.get("Date Saved") or row.get("date_saved") or "")
                    bm = Bookmark(
                        id=None,
                        url=url,
                        title=html_module.unescape(title),
                        tags=tags,
                        created_at=created,
                        source_file=str(path),
                    )
                    status = (row.get("Status") or "").strip().lower()
                    if status in ("queue", "later", "unread"):
                        bm.read_later = True
                    bookmarks.append(bm)
        except Exception as exc:
            log.error(f"Matter import failed: {exc}")
        return bookmarks


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _UnreadableMember:
    """A metadata file that could not be parsed, reported instead of dropped."""

    error: str


class OmnivoreImporter:
    """Omnivore export: a directory or zip of ``metadata_*.json`` files.

    Omnivore shut down in November 2024 and its export became a common
    migration format, so accept the archive as downloaded rather than asking
    people to merge the per-batch metadata files by hand. Each file holds a
    list of entries with url, title, labels, savedAt, and a state field.
    """

    def __init__(self):
        self.stats = SessionImportStats()

    @staticmethod
    def _iter_documents(path: Path) -> Iterator[Tuple[str, object]]:
        if path.is_dir():
            for candidate in sorted(path.rglob("metadata_*.json")):
                try:
                    # utf-8-sig so a BOM-prefixed export member still parses.
                    yield candidate.name, json.loads(candidate.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError) as exc:
                    yield candidate.name, _UnreadableMember(str(exc))
            return
        if path.suffix.lower() == ".zip":
            import zipfile

            try:
                with zipfile.ZipFile(path) as archive:
                    names = [n for n in archive.namelist()
                             if n.endswith(".json") and "metadata_" in Path(n).name]
                    for name in sorted(names):
                        try:
                            # A zip declares its uncompressed size, so check it
                            # before reading: a small archive can hold a
                            # highly compressible multi-gigabyte member.
                            declared = archive.getinfo(name).file_size
                            if declared > MAX_ARCHIVE_MEMBER_BYTES:
                                yield name, _UnreadableMember(
                                    f"member is {declared} bytes, over the "
                                    f"{MAX_ARCHIVE_MEMBER_BYTES}-byte limit"
                                )
                                continue
                            yield name, json.loads(archive.read(name).decode("utf-8-sig"))
                        except (KeyError, ValueError, UnicodeDecodeError) as exc:
                            yield name, _UnreadableMember(str(exc))
            except (OSError, zipfile.BadZipFile):
                return
            return
        try:
            yield path.name, json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            yield path.name, _UnreadableMember(str(exc))

    @staticmethod
    def metadata_files(directory: str) -> List[str]:
        """List the metadata files inside an unpacked export directory."""
        root = Path(directory)
        if not root.is_dir():
            return []
        return [str(p) for p in sorted(root.rglob("metadata_*.json"))]

    def from_paths(self, paths: List[str]) -> Iterator[Bookmark]:
        return self._collect([Path(p) for p in paths])

    def from_path(self, path: str) -> Iterator[Bookmark]:
        return self._collect([Path(path)])

    def _collect(self, sources: List[Path]) -> Iterator[Bookmark]:
        out: List[Bookmark] = []
        seen: set = set()
        for source in sources:
            if not source.exists():
                continue
            self._collect_one(source, out, seen)
        return iter(out)

    def _collect_one(self, source: Path, out: List[Bookmark], seen: set) -> None:
        for _name, document in self._iter_documents(source):
            if isinstance(document, _UnreadableMember):
                self.stats.record(f"metadata file could not be parsed: {document.error[:120]}")
                continue
            entries = document if isinstance(document, list) else []
            if isinstance(document, dict):
                for key in ("items", "data", "articles"):
                    if isinstance(document.get(key), list):
                        entries = document[key]
                        break
            for item in entries:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url or not url.startswith(("http://", "https://")):
                    if url:
                        self.stats.record("entry URL was not http(s)")
                    continue
                if url in seen:
                    continue
                seen.add(url)
                labels = []
                for label in (item.get("labels") or []):
                    if isinstance(label, dict):
                        name = str(label.get("name") or "").strip()
                    else:
                        name = str(label or "").strip()
                    if name:
                        labels.append(name)
                state = str(item.get("state") or "").strip().upper()
                try:
                    bookmark = Bookmark(
                        id=None,
                        url=url,
                        title=str(item.get("title") or url),
                        description=str(item.get("description") or ""),
                        notes=str(item.get("note") or ""),
                        tags=labels,
                        add_date=_ts(item.get("savedAt") or item.get("createdAt")),
                        source_file="omnivore",
                    )
                except ValueError as exc:
                    self.stats.record(f"invalid entry: {str(exc)[:120]}")
                    continue
                if state in {"SUCCEEDED", "SAVED", "ACTIVE", ""}:
                    bookmark.read_later = True
                if state == "ARCHIVED":
                    # Archived means read and filed away, which is distinct from
                    # never having been saved to the queue at all.
                    bookmark.read_later = False
                    bookmark.is_archived = True
                out.append(bookmark)


# ---------------------------------------------------------------------------
class WallabagJSONImporter:
    """Wallabag JSON export.

    Wallabag exports entries as a JSON array. Each entry has: title, url,
    content, is_archived, is_starred, tags (list of {label, slug}),
    created_at, updated_at, reading_time, domain_name, etc.
    Maps is_starred to pinned.
    """

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return iter(())
        if not isinstance(data, list):
            return iter(())
        out: List[Bookmark] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            url = (item.get("url") or "").strip()
            if not url or not url.startswith(("http://", "https://")):
                continue
            tags = []
            for tag_obj in (item.get("tags") or []):
                label = ""
                if isinstance(tag_obj, dict):
                    label = (tag_obj.get("label") or tag_obj.get("slug") or "").strip()
                elif isinstance(tag_obj, str):
                    label = tag_obj.strip()
                if label:
                    tags.append(label)
            bm = Bookmark(
                id=None,
                url=url,
                title=html_module.unescape(item.get("title") or url),
                description=item.get("preview_picture") or "",
                tags=tags,
                created_at=item.get("created_at") or "",
                source_file="wallabag-json",
            )
            if item.get("is_starred"):
                bm.is_pinned = True
            out.append(bm)
        return iter(out)


# ---------------------------------------------------------------------------
class ArcBrowserImporter:
    """Arc Browser sidebar export (StorableSidebar.json).

    Arc stores its sidebar state in StorableSidebar.json. Each item has
    a ``data`` dict with ``tab`` containing ``savedURL`` and ``savedTitle``.
    """

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return iter(())
        out: List[Bookmark] = []
        items = data if isinstance(data, list) else data.get("sidebarItems", data.get("items", []))
        self._walk(items, out, "Imported from Arc")
        return iter(out)

    def _walk(self, items, out: list, category: str):
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            item_data = item.get("data", item)
            tab = item_data.get("tab", {})
            url = (tab.get("savedURL") or tab.get("url") or "").strip()
            title = (tab.get("savedTitle") or tab.get("title") or "").strip()
            if url and url.startswith(("http://", "https://")):
                out.append(Bookmark(
                    id=None, url=url,
                    title=html_module.unescape(title or url),
                    category=category,
                    source_file="arc-browser",
                ))
            children = item.get("childrenIds") or item.get("children", [])
            if isinstance(children, list) and children:
                child_title = title or category
                for child in children:
                    if isinstance(child, dict):
                        self._walk([child], out, child_title)


def import_into(manager, importer, path: str) -> Tuple[int, int]:
    """Run an importer through a durable, resumable import session.

    Returns (added, duplicates).
    """
    from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

    source = importer.__class__.__name__.removesuffix("Importer").lower()
    sessions = ImportSessionManager()
    report = sessions.run(manager, importer, path, source=source)
    importer.last_session_report = report
    return report.added, report.duplicates
