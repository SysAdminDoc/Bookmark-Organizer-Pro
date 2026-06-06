"""Reader highlight and annotation persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

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
    created_at: str = ""
    modified_at: str = ""

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
            created_at=str(data.get("created_at") or now),
            modified_at=str(data.get("modified_at") or data.get("created_at") or now),
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
