"""Reader highlight and annotation persistence."""

from __future__ import annotations

import csv
import io
import json
import os
import re
from string import Formatter
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit

from bookmark_organizer_pro import constants as app_constants
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


HIGHLIGHT_COLORS = {
    "yellow": "#fff3a3",
    "green": "#bbf7d0",
    "blue": "#bae6fd",
    "pink": "#fbcfe8",
}
DEFAULT_HIGHLIGHT_COLOR = "yellow"


def _now() -> str:
    return datetime.now().isoformat()


def _clean_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_highlight_color(value: str) -> str:
    """Return one of the supported reader highlight color names."""
    color = str(value or "").strip().lower()
    if color in HIGHLIGHT_COLORS:
        return color
    for name, hex_value in HIGHLIGHT_COLORS.items():
        if color == hex_value:
            return name
    return DEFAULT_HIGHLIGHT_COLOR


def read_extracted_text(bookmark: Bookmark) -> str:
    """Read extracted text for a bookmark, returning an empty string on failure."""
    if not bookmark.extracted_text_path:
        return ""
    try:
        text_path = Path(bookmark.extracted_text_path).expanduser().resolve()
        if not text_path.is_relative_to(app_constants.APP_DIR.resolve()):
            log.warning(f"Refusing extracted text outside app data for bookmark {bookmark.id}")
            return ""
        return text_path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning(f"Could not read extracted text for bookmark {bookmark.id}: {exc}")
        return ""


def _safe_filename_stem(value: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "bookmark"))
    stem = re.sub(r"_+", "_", stem).strip("_. ")
    return stem[:100] or "bookmark"


def _markdown_quote(text: str) -> List[str]:
    lines = str(text or "").splitlines() or [""]
    return [f"> {line}" if line else ">" for line in lines]


@dataclass
class ReaderHighlight:
    """A selected text range with optional reader notes."""

    id: str
    bookmark_id: int
    char_start: int
    char_end: int
    text: str
    color: str = DEFAULT_HIGHLIGHT_COLOR
    note: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    modified_at: str = ""
    sr_interval: int = 0
    sr_repetitions: int = 0
    sr_ease: float = 2.5
    sr_next_review: str = ""

    @property
    def color_hex(self) -> str:
        return HIGHLIGHT_COLORS[self.color]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["color"] = normalize_highlight_color(payload.get("color", ""))
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "ReaderHighlight":
        now = _now()
        start = max(0, _clean_int(data.get("char_start")))
        end = max(start, _clean_int(data.get("char_end"), start))
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            bookmark_id=_clean_int(data.get("bookmark_id")),
            char_start=start,
            char_end=end,
            text=str(data.get("text") or ""),
            color=normalize_highlight_color(str(data.get("color") or "")),
            note=str(data.get("note") or ""),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()]
            if isinstance(data.get("tags", []), (list, tuple, set)) else [],
            created_at=str(data.get("created_at") or now),
            modified_at=str(data.get("modified_at") or data.get("created_at") or now),
            sr_interval=_clean_int(data.get("sr_interval")),
            sr_repetitions=_clean_int(data.get("sr_repetitions")),
            sr_ease=float(data.get("sr_ease", 2.5) or 2.5),
            sr_next_review=str(data.get("sr_next_review") or ""),
        )


class ReaderAnnotationStore:
    """Persisted reader highlight CRUD."""

    def __init__(self, filepath: Path | None = None):
        self.filepath = Path(filepath) if filepath is not None else app_constants.READER_ANNOTATIONS_FILE
        self._lock = threading.RLock()
        self._highlights: Dict[str, ReaderHighlight] = {}
        self._load()

    def _load(self) -> None:
        if not self.filepath.exists():
            return
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(f"Could not load reader annotations: {exc}")
            return
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("highlights", [])
        else:
            items = []
        with self._lock:
            self._highlights = {}
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                try:
                    highlight = ReaderHighlight.from_dict(item)
                    self._highlights[highlight.id] = highlight
                except Exception as exc:
                    log.warning(f"Bad reader annotation entry: {exc}")

    def _save(self) -> None:
        with self._lock:
            highlights = sorted(
                self._highlights.values(),
                key=lambda item: (item.bookmark_id, item.char_start, item.created_at),
            )
            payload = [item.to_dict() for item in highlights]
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.filepath.parent, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
            os.replace(tmp, self.filepath)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def add_from_text(
        self,
        bookmark_id: int,
        text: str,
        char_start: int,
        char_end: int,
        color: str = DEFAULT_HIGHLIGHT_COLOR,
        note: str = "",
    ) -> ReaderHighlight:
        source = str(text or "")
        start = _clean_int(char_start)
        end = _clean_int(char_end)
        if start < 0 or end <= start or end > len(source):
            raise ValueError("highlight range is outside the extracted text")
        selected = source[start:end]
        if not selected.strip():
            raise ValueError("highlight selection cannot be blank")
        now = _now()
        highlight = ReaderHighlight(
            id=uuid.uuid4().hex,
            bookmark_id=int(bookmark_id),
            char_start=start,
            char_end=end,
            text=selected,
            color=normalize_highlight_color(color),
            note=str(note or ""),
            created_at=now,
            modified_at=now,
        )
        with self._lock:
            self._highlights[highlight.id] = highlight
        self._save()
        return highlight

    def add_for_bookmark(
        self,
        bookmark: Bookmark,
        char_start: int,
        char_end: int,
        color: str = DEFAULT_HIGHLIGHT_COLOR,
        note: str = "",
    ) -> ReaderHighlight:
        text = read_extracted_text(bookmark)
        if not text:
            raise ValueError("bookmark has no extracted text")
        return self.add_from_text(int(bookmark.id), text, char_start, char_end, color=color, note=note)

    def list_for_bookmark(self, bookmark_id: int) -> List[ReaderHighlight]:
        bid = int(bookmark_id)
        with self._lock:
            items = [item for item in self._highlights.values() if item.bookmark_id == bid]
        return sorted(items, key=lambda item: (item.char_start, item.created_at))

    def list_all(self) -> List[ReaderHighlight]:
        with self._lock:
            items = list(self._highlights.values())
        return sorted(items, key=lambda item: (item.bookmark_id, item.char_start, item.created_at))

    def get(self, highlight_id: str) -> Optional[ReaderHighlight]:
        return self._highlights.get(str(highlight_id))

    def delete(self, highlight_id: str) -> bool:
        with self._lock:
            if str(highlight_id) not in self._highlights:
                return False
            del self._highlights[str(highlight_id)]
        self._save()
        return True

    def set_note(self, highlight_id: str, note: str) -> bool:
        with self._lock:
            highlight = self._highlights.get(str(highlight_id))
            if highlight is None:
                return False
            highlight.note = str(note or "")
            highlight.modified_at = _now()
        self._save()
        return True

    def due_for_review(self, today: Optional[datetime] = None) -> List[ReaderHighlight]:
        """Return highlights whose next review date is today or earlier."""
        today = today or datetime.now()
        today_iso = today.date().isoformat()
        with self._lock:
            due = []
            for h in self._highlights.values():
                if not h.sr_next_review:
                    due.append(h)
                elif h.sr_next_review <= today_iso:
                    due.append(h)
        return sorted(due, key=lambda h: (h.sr_next_review or "", h.created_at))

    def record_review(self, highlight_id: str, quality: int) -> bool:
        """Record a review using SM-2 algorithm. quality: 0-5 (0=fail, 5=perfect)."""
        quality = max(0, min(5, int(quality)))
        with self._lock:
            h = self._highlights.get(str(highlight_id))
            if h is None:
                return False
            if quality < 3:
                h.sr_repetitions = 0
                h.sr_interval = 1
            else:
                if h.sr_repetitions == 0:
                    h.sr_interval = 1
                elif h.sr_repetitions == 1:
                    h.sr_interval = 6
                else:
                    h.sr_interval = max(1, round(h.sr_interval * h.sr_ease))
                h.sr_repetitions += 1
                h.sr_ease = max(1.3, h.sr_ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
            from datetime import timedelta
            next_date = datetime.now() + timedelta(days=h.sr_interval)
            h.sr_next_review = next_date.date().isoformat()
            h.modified_at = _now()
        self._save()
        return True


def render_highlights_markdown(bookmark: Bookmark, highlights: Iterable[ReaderHighlight]) -> str:
    """Render bookmark reader highlights as Markdown."""
    lines = [
        f"# Reader highlights: {bookmark.title or bookmark.url}",
        "",
        f"> {bookmark.url}",
        "",
        f"Bookmark ID: {bookmark.id}",
        "",
        "## Highlights",
        "",
    ]
    items = list(highlights)
    if not items:
        lines.append("(none)")
        return "\n".join(lines).rstrip() + "\n"
    for index, item in enumerate(items, start=1):
        lines.extend([
            f"### Highlight {index}",
            "",
            f"- Color: {item.color}",
            f"- Range: {item.char_start}-{item.char_end}",
            "",
        ])
        lines.extend(_markdown_quote(item.text))
        lines.append("")
        if item.note:
            lines.extend(["Note:", "", item.note, ""])
    return "\n".join(lines).rstrip() + "\n"


def export_bookmark_highlights(
    bookmark: Bookmark,
    highlights: Iterable[ReaderHighlight],
    output_dir: Path | None = None,
) -> Path:
    """Export one bookmark's reader highlights to a Markdown file."""
    out_dir = Path(output_dir) if output_dir is not None else app_constants.EXPORTS_DIR / "reader-highlights"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_filename_stem(f"{bookmark.id}-{bookmark.title or bookmark.url}-highlights")
    out_path = out_dir / f"{stem}.md"
    out_path.write_text(render_highlights_markdown(bookmark, highlights), encoding="utf-8")
    return out_path


ANNOTATION_EXPORT_SCHEMA = "bookmark-organizer-pro/annotations-v1"
DEFAULT_ANNOTATION_FIELDS = (
    "document_id", "document_title", "document_url", "document_category",
    "document_tags", "document_notes", "document_created_at", "document_modified_at",
    "highlight_id", "highlight_text", "highlight_color", "highlight_tags", "highlight_note",
    "highlight_created_at", "highlight_modified_at", "review_interval", "review_repetitions",
    "review_ease", "review_next", "source_link",
)


@dataclass(frozen=True)
class AnnotationExportTemplate:
    """Validated, data-only annotation export template.

    Templates are JSON documents; no expressions or code are evaluated. CSV and
    JSON templates select/order fields. Markdown templates additionally support
    ``document_header`` and ``highlight`` format strings using the same fields.
    """

    format: str = "markdown"
    fields: tuple[str, ...] = DEFAULT_ANNOTATION_FIELDS
    document_header: str = "# {document_title}\n\nSource: {document_url}\n"
    highlight: str = (
        "## {highlight_text}\n\n"
        "- Color: {highlight_color}\n"
        "- Tags: {highlight_tags}\n"
        "- Review: {review_repetitions} repetitions; next {review_next}\n"
        "- Stable source: {source_link}\n\n"
        "{highlight_note}\n"
    )

    @classmethod
    def load(cls, path: str | Path | None = None, *, output_format: str | None = None):
        payload: dict = {}
        if path is not None:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("annotation export template must be a JSON object")
            payload = raw
        fmt = str(output_format or payload.get("format") or "markdown").strip().lower()
        if fmt not in {"markdown", "csv", "json"}:
            raise ValueError("annotation export format must be markdown, csv, or json")
        raw_fields = payload.get("fields", DEFAULT_ANNOTATION_FIELDS)
        if not isinstance(raw_fields, list) and raw_fields is not DEFAULT_ANNOTATION_FIELDS:
            raise ValueError("annotation export template fields must be a list")
        fields = tuple(str(item) for item in raw_fields)
        unknown = sorted(set(fields) - set(DEFAULT_ANNOTATION_FIELDS))
        if unknown:
            raise ValueError(f"unknown annotation export fields: {', '.join(unknown)}")
        if not fields:
            raise ValueError("annotation export template must select at least one field")
        document_header = str(payload.get("document_header", cls.document_header))
        highlight = str(payload.get("highlight", cls.highlight))
        for value in (document_header, highlight):
            if len(value) > 20_000:
                raise ValueError("annotation template strings must be at most 20000 characters")
            for _literal, field_name, format_spec, conversion in Formatter().parse(value):
                if field_name and field_name not in DEFAULT_ANNOTATION_FIELDS:
                    raise ValueError(f"unknown or unsafe annotation template field: {field_name}")
                if format_spec or conversion:
                    raise ValueError("annotation template conversions and format specifications are not allowed")
        return cls(
            format=fmt,
            fields=fields,
            document_header=document_header,
            highlight=highlight,
        )


class _BlankFormatDict(dict):
    def __missing__(self, key):
        return ""


def _parse_export_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid changed-since timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_changed_since(item: ReaderHighlight, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    value = item.modified_at or item.created_at
    try:
        changed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    return changed.astimezone(timezone.utc) >= cutoff


def annotation_export_records(
    bookmarks: Iterable[Bookmark],
    highlights: Iterable[ReaderHighlight],
    *,
    changed_since: str | None = None,
) -> List[dict]:
    """Return deterministic, flat records suitable for Markdown/CSV/JSON."""
    bookmark_map = {int(bookmark.id): bookmark for bookmark in bookmarks}
    cutoff = _parse_export_timestamp(changed_since)
    records: List[dict] = []
    ordered = sorted(
        highlights,
        key=lambda item: (item.bookmark_id, item.char_start, item.created_at, item.id),
    )
    for item in ordered:
        bookmark = bookmark_map.get(int(item.bookmark_id))
        if bookmark is None or not _is_changed_since(item, cutoff):
            continue
        parsed_url = urlsplit(bookmark.url)
        source_link = urlunsplit(parsed_url._replace(fragment=f"bop-highlight-{item.id}"))
        records.append({
            "document_id": int(bookmark.id),
            "document_title": bookmark.title or bookmark.url,
            "document_url": bookmark.url,
            "document_category": bookmark.full_category_path,
            "document_tags": list(bookmark.tags),
            "document_notes": bookmark.notes,
            "document_created_at": bookmark.created_at,
            "document_modified_at": bookmark.modified_at,
            "highlight_id": item.id,
            "highlight_text": item.text,
            "highlight_color": item.color,
            "highlight_tags": list(item.tags),
            "highlight_note": item.note,
            "highlight_created_at": item.created_at,
            "highlight_modified_at": item.modified_at,
            "review_interval": item.sr_interval,
            "review_repetitions": item.sr_repetitions,
            "review_ease": item.sr_ease,
            "review_next": item.sr_next_review,
            "source_link": source_link,
        })
    return records


def render_annotation_export(
    records: Sequence[Mapping], template: AnnotationExportTemplate
) -> str:
    """Render records using a validated template, deterministically."""
    if template.format == "json":
        selected = [{field: record.get(field, "") for field in template.fields} for record in records]
        return json.dumps({"schema": ANNOTATION_EXPORT_SCHEMA, "records": selected}, indent=2,
                          ensure_ascii=False) + "\n"
    if template.format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(template.fields), lineterminator="\n")
        writer.writeheader()
        for record in records:
            row = {}
            for field_name in template.fields:
                value = record.get(field_name, "")
                row[field_name] = ", ".join(map(str, value)) if isinstance(value, list) else value
            writer.writerow(row)
        return stream.getvalue()

    chunks: List[str] = []
    current_document = object()
    for record in records:
        values = _BlankFormatDict(record)
        values["document_tags"] = ", ".join(record.get("document_tags", []))
        values["highlight_tags"] = ", ".join(record.get("highlight_tags", []))
        if record.get("document_id") != current_document:
            current_document = record.get("document_id")
            chunks.append(template.document_header.format_map(values).rstrip())
        chunks.append(template.highlight.format_map(values).rstrip())
    return "\n\n".join(chunk for chunk in chunks if chunk).rstrip() + ("\n" if chunks else "")


def export_annotations(
    bookmarks: Iterable[Bookmark],
    highlights: Iterable[ReaderHighlight],
    output_path: str | Path,
    *,
    output_format: str | None = None,
    template_path: str | Path | None = None,
    changed_since: str | None = None,
) -> Path:
    """Export annotations atomically using a built-in or user JSON template."""
    template = AnnotationExportTemplate.load(template_path, output_format=output_format)
    records = annotation_export_records(bookmarks, highlights, changed_since=changed_since)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_annotation_export(records, template)
    fd, tmp = tempfile.mkstemp(dir=destination.parent, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(rendered)
        os.replace(tmp, destination)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return destination


def parse_annotation_export(path: str | Path) -> List[dict]:
    """Read CSV/JSON annotation exports for round-trip validation/migration."""
    source = Path(path)
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != ANNOTATION_EXPORT_SCHEMA:
            raise ValueError("unsupported annotation export schema")
        records = payload.get("records", [])
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ValueError("annotation export records must be objects")
        return records
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError("round-trip parsing supports CSV and JSON annotation exports")
