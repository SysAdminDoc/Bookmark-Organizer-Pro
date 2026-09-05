"""Import a folder of bookmark exports as one deduplicated batch.

Real migrations arrive as a pile of exports accumulated over years: the same
file saved a dozen times under different names, several formats side by side,
and heavy overlap between them. Importing them one dialog at a time is the
wrong shape, so this module discovers a directory, drops byte-identical
duplicates by digest, picks an importer per surviving file, and merges the
parsed entries on the same canonical URL key the rest of the app uses.

The result is importer-shaped (``from_path``/``from_paths``/``stats``) so it
runs through :class:`ImportSessionManager` unchanged and inherits that
session's single rollback safepoint and transactional apply.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from bookmark_organizer_pro.importers import (
    FirefoxBookmarkBackupImporter,
    NetscapeBookmarkImporter,
    OPMLImporter,
    SessionImportStats,
    TextURLImporter,
)
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.utils.url import normalize_url

# Extensions worth opening at all. Anything else in the folder is reported as
# unsupported rather than silently ignored.
SUPPORTED_SUFFIXES = frozenset({".html", ".htm", ".json", ".jsonlz4", ".csv", ".txt", ".opml"})

MAX_SOURCE_BYTES = 250_000_000

_EPOCH = datetime(1970, 1, 1)


@dataclass(frozen=True)
class BatchSourceFile:
    """One discovered file and what became of it."""

    path: str
    digest: str
    format: str = ""
    entries: int = 0
    duplicate_of: Optional[str] = None
    error: str = ""

    @property
    def counted(self) -> bool:
        """True when this file contributed entries to the merge."""
        return not self.duplicate_of and not self.error


@dataclass(frozen=True)
class BatchConflict:
    """A URL whose title or date disagreed between source files."""

    url: str
    field: str
    kept: str
    discarded: str


@dataclass
class BatchImportPlan:
    """What a batch import would do, before anything is committed."""

    files: Tuple[BatchSourceFile, ...] = ()
    bookmarks: Tuple[Bookmark, ...] = ()
    parsed_entries: int = 0
    conflicts: Tuple[BatchConflict, ...] = ()
    stats: SessionImportStats = field(default_factory=SessionImportStats)

    @property
    def unique_files(self) -> Tuple[BatchSourceFile, ...]:
        return tuple(f for f in self.files if f.counted)

    @property
    def duplicate_files(self) -> Tuple[BatchSourceFile, ...]:
        return tuple(f for f in self.files if f.duplicate_of)

    @property
    def unreadable_files(self) -> Tuple[BatchSourceFile, ...]:
        return tuple(f for f in self.files if f.error)

    @property
    def unique_urls(self) -> int:
        return len(self.bookmarks)

    @property
    def merged(self) -> int:
        """Entries collapsed into an existing URL during the merge."""
        return max(0, self.parsed_entries - len(self.bookmarks))

    def summary(self) -> Dict[str, int]:
        return {
            "files": len(self.files),
            "unique_files": len(self.unique_files),
            "duplicate_files": len(self.duplicate_files),
            "unreadable_files": len(self.unreadable_files),
            "parsed_entries": self.parsed_entries,
            "unique_urls": self.unique_urls,
            "merged": self.merged,
            "conflicts": len(self.conflicts),
        }


def _parse_netscape(path: str, *, categorize=None) -> List[Bookmark]:
    return list(NetscapeBookmarkImporter.import_from_netscape(path, categorize=categorize))


def _parse_firefox_backup(path: str) -> List[Bookmark]:
    return list(FirefoxBookmarkBackupImporter().from_path(path))


def _load_json(path: str):
    """Read JSON tolerating a UTF-8 BOM, which Windows exporters often write."""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _parse_json_records(path: str) -> List[Bookmark]:
    """Parse an exported JSON list of bookmark records.

    Covers this app's own export shape (``{"data": [...]}``), the common
    ``{"bookmarks": [...]}`` variant, and a bare list.
    """
    data = _load_json(path)
    if isinstance(data, dict):
        records = data.get("bookmarks", data.get("data", []))
    else:
        records = data
    if not isinstance(records, list):
        raise ValueError("JSON export does not contain a bookmark list")
    out: List[Bookmark] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        url = str(record.get("url") or record.get("href") or "").strip()
        if not url:
            continue
        tags = record.get("tags")
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,;\s]+", tags) if t.strip()]
        elif not isinstance(tags, list):
            tags = []
        try:
            out.append(Bookmark(
                id=None,
                url=url,
                title=str(record.get("title") or record.get("description") or url),
                category=str(record.get("category") or ""),
                parent_category=str(record.get("parent_category") or ""),
                tags=[str(t) for t in tags],
                notes=str(record.get("notes") or record.get("extended") or ""),
                description=str(record.get("description") or ""),
                add_date=str(record.get("add_date") or record.get("created_at") or record.get("time") or ""),
                source_file="json-export",
            ))
        except ValueError:
            continue
    return out


def _parse_csv_records(path: str) -> List[Bookmark]:
    """Parse a CSV export with a URL column, keeping any category columns."""
    from bookmark_organizer_pro.importers_extra import MappedCSVImporter

    return list(MappedCSVImporter().from_path(path))


def _parse_text_urls(path: str) -> List[Bookmark]:
    return list(TextURLImporter.import_from_text(path))


def _parse_opml(path: str) -> List[Bookmark]:
    return list(OPMLImporter.import_from_opml(path))


def _looks_like_json_records(path: str) -> bool:
    try:
        data = _load_json(path)
    except Exception:
        return False
    if isinstance(data, list):
        return True
    return isinstance(data, dict) and isinstance(data.get("bookmarks", data.get("data")), list)


# (label, suffixes, sniff, parse). Order matters: the first match wins, so
# content sniffs sit ahead of the generic reader for the same extension.
_FORMATS: Tuple[Tuple[str, frozenset, Optional[Callable[[str], bool]], Callable[[str], List[Bookmark]]], ...] = (
    ("netscape-html", frozenset({".html", ".htm"}), None, _parse_netscape),
    ("firefox-backup", frozenset({".json", ".jsonlz4"}),
     lambda p: FirefoxBookmarkBackupImporter.looks_like_backup(p), _parse_firefox_backup),
    ("json-export", frozenset({".json"}), _looks_like_json_records, _parse_json_records),
    ("csv-export", frozenset({".csv"}), None, _parse_csv_records),
    ("text-urls", frozenset({".txt"}), None, _parse_text_urls),
    ("opml", frozenset({".opml"}), None, _parse_opml),
)


def detect_format(path: str | Path) -> str:
    """Return the importer label for a file, or "" when nothing handles it."""
    candidate = Path(path)
    suffix = candidate.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return ""
    for label, suffixes, sniff, _parse in _FORMATS:
        if suffix not in suffixes:
            continue
        if sniff is not None and not sniff(str(candidate)):
            continue
        return label
    return ""


def _accepts_categorize(parser: Callable) -> bool:
    """Whether a registered parser takes the shared categorization policy."""
    import inspect

    try:
        return "categorize" in inspect.signature(parser).parameters
    except (TypeError, ValueError):
        return False


def _parser_for(label: str) -> Callable[[str], List[Bookmark]]:
    for candidate, _suffixes, _sniff, parse in _FORMATS:
        if candidate == label:
            return parse
    raise ValueError(f"No parser registered for {label!r}")


def _parse_timestamp(value: object) -> Optional[float]:
    """Return a comparable epoch value for the date shapes exports actually use.

    Netscape files carry epoch seconds, service exports carry ISO 8601, and some
    carry epoch milliseconds or microseconds. Comparing these as strings would
    rank "999999999" above "1700000000" and any ISO date above every epoch, so
    every candidate is converted before comparison and unparseable text is
    treated as no date at all.
    """
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d{1,19}", text):
        number = float(text)
        # Disambiguate seconds / milliseconds / microseconds by magnitude.
        for divisor in (1.0, 1_000.0, 1_000_000.0):
            candidate = number / divisor
            if 0 < candidate < 4_102_444_800:  # through the year 2100
                return candidate
        return None
    normalized = text.replace("Z", "+00:00")
    for parser in (
        lambda s: datetime.fromisoformat(s),
        lambda s: datetime.strptime(s, "%Y-%m-%d"),
        lambda s: datetime.strptime(s, "%Y/%m/%d"),
    ):
        try:
            parsed = parser(normalized)
        except (ValueError, TypeError):
            continue
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        # Subtracting the epoch avoids datetime.timestamp(), which raises
        # OSError on Windows for values at or before 1970.
        return (parsed - _EPOCH).total_seconds()
    return None


# Importers that put the source date in ``created_at`` rather than ``add_date``.
# Every other field is left alone, because ``created_at`` otherwise defaults to
# the moment the object was built and would outrank every real source date.
_CREATED_AT_FORMATS = frozenset({"netscape-html", "firefox-backup"})


def _normalize_source_dates(bookmarks: Iterable[Bookmark], label: str) -> None:
    """Move a parser's source date into ``add_date`` so merges can compare it."""
    if label not in _CREATED_AT_FORMATS:
        return
    for bookmark in bookmarks:
        if not str(getattr(bookmark, "add_date", "") or "").strip():
            source_date = str(getattr(bookmark, "created_at", "") or "").strip()
            if source_date and _parse_timestamp(source_date) is not None:
                bookmark.add_date = source_date


def _best_timestamp(bookmark: Bookmark) -> Optional[float]:
    """Comparable source date for a bookmark, or None when it has none."""
    return _parse_timestamp(getattr(bookmark, "add_date", ""))


class BatchDirectoryImporter:
    """Importer-shaped facade over a directory (or explicit list) of exports."""

    def __init__(self, *, recursive: bool = True, categorize=None):
        self.recursive = recursive
        # Same URL-categorization policy the desktop and CLI single-file
        # importers apply, so one export produces one set of records no
        # matter which surface reads it.
        self.categorize = categorize
        self.stats = SessionImportStats()
        self.last_plan: Optional[BatchImportPlan] = None

    # ── discovery ────────────────────────────────────────────────────────
    def discover(self, source: str | Path | Sequence[str | Path]) -> List[Path]:
        """List candidate files from a directory, or normalize an explicit list."""
        if isinstance(source, (list, tuple)):
            return [Path(item).resolve() for item in source]
        root = Path(source).resolve()
        if root.is_file():
            return [root]
        if not root.is_dir():
            raise ValueError(f"Import source is not a readable file or directory: {root}")
        pattern = "**/*" if self.recursive else "*"
        return sorted(
            (p.resolve() for p in root.glob(pattern)
             if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES),
            key=lambda p: str(p).lower(),
        )

    @staticmethod
    def _digest(path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    # ── planning ─────────────────────────────────────────────────────────
    def plan(self, source: str | Path | Sequence[str | Path]) -> BatchImportPlan:
        """Hash, detect, parse, and merge without touching the library."""
        stats = SessionImportStats()
        files: List[BatchSourceFile] = []
        merged: Dict[str, Bookmark] = {}
        conflicts: List[BatchConflict] = []
        seen_digests: Dict[str, str] = {}
        parsed_entries = 0

        for path in self.discover(source):
            try:
                size = path.stat().st_size
            except OSError as exc:
                files.append(BatchSourceFile(path=str(path), digest="", error=str(exc)))
                stats.record("source file could not be read")
                continue
            if size > MAX_SOURCE_BYTES:
                files.append(BatchSourceFile(
                    path=str(path), digest="", error=f"file exceeds {MAX_SOURCE_BYTES} bytes"))
                stats.record("source file too large")
                continue

            try:
                digest = self._digest(path)
            except OSError as exc:
                files.append(BatchSourceFile(path=str(path), digest="", error=str(exc)))
                stats.record("source file could not be read")
                continue

            if digest in seen_digests:
                files.append(BatchSourceFile(
                    path=str(path), digest=digest, duplicate_of=seen_digests[digest]))
                continue

            label = detect_format(path)
            if not label:
                files.append(BatchSourceFile(
                    path=str(path), digest=digest, error="no importer handles this file"))
                stats.record("unsupported source format")
                continue

            try:
                parser = _parser_for(label)
                if self.categorize is not None and _accepts_categorize(parser):
                    parsed = parser(str(path), categorize=self.categorize)
                else:
                    parsed = parser(str(path))
            except Exception as exc:  # a bad file must not abort the batch
                log.warning(f"Batch import could not parse {path}: {exc}")
                files.append(BatchSourceFile(
                    path=str(path), digest=digest, format=label, error=str(exc)[:300]))
                stats.record(f"{label} parse failed")
                continue

            _normalize_source_dates(parsed, label)
            seen_digests[digest] = str(path)
            files.append(BatchSourceFile(
                path=str(path), digest=digest, format=label, entries=len(parsed)))
            parsed_entries += len(parsed)
            self._merge(parsed, merged, conflicts)

        plan = BatchImportPlan(
            files=tuple(files),
            bookmarks=tuple(merged.values()),
            parsed_entries=parsed_entries,
            conflicts=tuple(conflicts),
            stats=stats,
        )
        self.stats = stats
        self.last_plan = plan
        return plan

    @staticmethod
    def _merge(parsed: Iterable[Bookmark], merged: Dict[str, Bookmark],
               conflicts: List[BatchConflict]) -> None:
        """Fold parsed entries into the merge, newest date and longest title win."""
        for bookmark in parsed:
            key = normalize_url(bookmark.url)
            if not key:
                continue
            current = merged.get(key)
            if current is None:
                merged[key] = bookmark
                continue

            incoming_stamp = _best_timestamp(bookmark)
            current_stamp = _best_timestamp(current)
            if incoming_stamp is not None and current_stamp is not None and incoming_stamp != current_stamp:
                # Record the disagreement whichever side wins, so the preview
                # count does not depend on the order files were read in.
                newer_wins = incoming_stamp > current_stamp
                conflicts.append(BatchConflict(
                    key, "date",
                    str((bookmark if newer_wins else current).add_date or ""),
                    str((current if newer_wins else bookmark).add_date or ""),
                ))
            if incoming_stamp is not None and (current_stamp is None or incoming_stamp > current_stamp):
                current.add_date = bookmark.add_date
                current.url = bookmark.url

            incoming_title = str(bookmark.title or "").strip()
            current_title = str(current.title or "").strip()
            if current_title and incoming_title and incoming_title != current_title:
                conflicts.append(BatchConflict(
                    key, "title",
                    incoming_title if len(incoming_title) > len(current_title) else current_title,
                    current_title if len(incoming_title) > len(current_title) else incoming_title,
                ))
            if len(incoming_title) > len(current_title):
                current.title = bookmark.title

            if not str(current.category or "").strip() and str(bookmark.category or "").strip():
                current.category = bookmark.category
                current.parent_category = bookmark.parent_category
            if not str(current.notes or "").strip() and str(bookmark.notes or "").strip():
                current.notes = bookmark.notes
            if bookmark.tags:
                have = {str(t).strip().lower() for t in current.tags}
                current.tags = list(current.tags) + [
                    t for t in bookmark.tags if str(t).strip().lower() not in have
                ]

    # ── importer interface ───────────────────────────────────────────────
    def from_path(self, path: str) -> List[Bookmark]:
        return list(self.plan(path).bookmarks)

    def from_paths(self, paths: List[str]) -> List[Bookmark]:
        return list(self.plan(list(paths)).bookmarks)
