"""Reader highlight and annotation persistence."""

from __future__ import annotations

import csv
from copy import deepcopy
import hashlib
import io
import json
import os
import re
from string import Formatter
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit, urlunsplit

from bookmark_organizer_pro import constants as app_constants
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentStore,
    require_list_document,
)


HIGHLIGHT_COLORS = {
    "yellow": "#fff3a3",
    "green": "#bbf7d0",
    "blue": "#bae6fd",
    "pink": "#fbcfe8",
}
DEFAULT_HIGHLIGHT_COLOR = "yellow"
SELECTOR_CONTEXT_CHARS = 64
MAX_ANCHOR_HISTORY = 50
ANCHOR_STATUSES = {"unverified", "anchored", "reanchored", "orphaned"}


def _migrate_reader_annotations_v0(document):
    """Normalize both historical annotation layouts to the canonical array."""
    if isinstance(document, dict):
        return document.get("highlights", [])
    return document


def _migrate_reader_annotations_v1(document):
    """Add W3C-style quote selectors without inventing unavailable context."""
    if not isinstance(document, list):
        return document
    migrated = []
    for raw in document:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item.setdefault("source_sha256", "")
        item.setdefault("quote_exact", str(item.get("text") or ""))
        item.setdefault("quote_prefix", "")
        item.setdefault("quote_suffix", "")
        item.setdefault("anchor_status", "unverified")
        item.setdefault("orphan_reason", "")
        item.setdefault("anchor_history", [])
        migrated.append(item)
    return migrated


def _now() -> str:
    return datetime.now().isoformat()


def _clean_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def source_text_sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _selector_context(
    source: str,
    start: int,
    end: int,
) -> tuple[str, str]:
    return (
        source[max(0, start - SELECTOR_CONTEXT_CHARS):start],
        source[end:end + SELECTOR_CONTEXT_CHARS],
    )


def _clean_digest(value: object) -> str:
    digest = str(value or "").strip().lower()
    return digest if re.fullmatch(r"[0-9a-f]{64}", digest) else ""


def _clean_anchor_history(value: object) -> List[dict]:
    if not isinstance(value, list):
        return []
    cleaned: List[dict] = []
    allowed = {
        "at",
        "action",
        "reason",
        "from_start",
        "from_end",
        "from_source_sha256",
        "to_start",
        "to_end",
        "to_source_sha256",
    }
    for raw in value[-MAX_ANCHOR_HISTORY:]:
        if not isinstance(raw, dict):
            continue
        item = {
            str(key): raw[key]
            for key in allowed
            if key in raw
        }
        for key in ("from_start", "from_end", "to_start", "to_end"):
            if key in item:
                item[key] = max(0, _clean_int(item[key]))
        for key in ("from_source_sha256", "to_source_sha256"):
            if key in item:
                item[key] = _clean_digest(item[key])
        for key in ("at", "action", "reason"):
            if key in item:
                item[key] = str(item[key])[:500]
        cleaned.append(item)
    return cleaned


def _validate_reader_annotations(document) -> None:
    require_list_document(document)
    for raw in document:
        if not isinstance(raw, dict):
            raise ValueError("reader annotation entries must be objects")
        digest = str(raw.get("source_sha256") or "")
        if digest and not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("reader annotation source digest is invalid")
        if len(str(raw.get("quote_prefix") or "")) > SELECTOR_CONTEXT_CHARS:
            raise ValueError("reader annotation quote prefix is too long")
        if len(str(raw.get("quote_suffix") or "")) > SELECTOR_CONTEXT_CHARS:
            raise ValueError("reader annotation quote suffix is too long")
        if raw.get("anchor_status") not in ANCHOR_STATUSES:
            raise ValueError("reader annotation anchor status is invalid")
        history = raw.get("anchor_history", [])
        if not isinstance(history, list) or len(history) > MAX_ANCHOR_HISTORY:
            raise ValueError("reader annotation anchor history is invalid")


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
    paths = [
        str(bookmark.extracted_text_path or ""),
        str(getattr(bookmark, "youtube_transcript_path", "") or ""),
    ]
    for path_value in paths:
        if not path_value:
            continue
        try:
            text_path = Path(path_value).expanduser().resolve()
            if not text_path.is_relative_to(app_constants.APP_DIR.resolve()):
                log.warning(f"Refusing derived text outside app data for bookmark {bookmark.id}")
                continue
            return text_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning(f"Could not read derived text for bookmark {bookmark.id}: {exc}")
    return ""


def _safe_filename_stem(value: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "bookmark"))
    stem = re.sub(r"_+", "_", stem).strip("_. ")
    return stem[:100] or "bookmark"


def _markdown_quote(text: str) -> List[str]:
    lines = str(text or "").splitlines() or [""]
    return [f"> {line}" if line else ">" for line in lines]


# Readwise's Daily Review resurfaces on recall probability rather than card
# grading, because a highlight has no answer to score. Soon/Later/Someday are
# the reader-facing choice; the numbers are the half-lives behind them.
REVIEW_PACES = {"soon": 7.0, "later": 14.0, "someday": 28.0}
DEFAULT_HALF_LIFE_DAYS = REVIEW_PACES["later"]
MIN_HALF_LIFE_DAYS = 1.0
MAX_HALF_LIFE_DAYS = 365.0
RECALL_DUE_THRESHOLD = 0.5


def _clean_half_life(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number <= 0:
        return 0.0
    return max(MIN_HALF_LIFE_DAYS, min(MAX_HALF_LIFE_DAYS, number))


def _clean_weight(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.25, min(4.0, number))


def _parse_review_time(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _last_surfaced_at(highlight: "ReaderHighlight") -> Optional[datetime]:
    """When this highlight was last put in front of the reader, or None.

    None means never, which is always due. A record written by the previous
    SM-2 scheduler has no such timestamp, so it is reconstructed from that
    scheduler's own next-review date and interval and the old cadence carries
    over intact.
    """
    direct = _parse_review_time(getattr(highlight, "sr_last_seen", ""))
    if direct is not None:
        return direct
    legacy_due = _parse_review_time(getattr(highlight, "sr_next_review", ""))
    interval = max(0, int(getattr(highlight, "sr_interval", 0) or 0))
    if legacy_due is not None and interval:
        return legacy_due - timedelta(days=interval)
    return None


def _effective_half_life(highlight: "ReaderHighlight") -> float:
    """Half-life in days, migrating an SM-2 record on first use.

    Older highlights carry only an SM-2 interval and ease. That interval is
    already an estimate of how long recall lasts, so it seeds the half-life
    directly and no review history is lost.
    """
    stored = _clean_half_life(getattr(highlight, "sr_half_life", 0.0))
    if not stored:
        legacy_interval = max(0, int(getattr(highlight, "sr_interval", 0) or 0))
        stored = _clean_half_life(legacy_interval) if legacy_interval else DEFAULT_HALF_LIFE_DAYS
    weight = _clean_weight(getattr(highlight, "sr_weight", 1.0))
    return max(MIN_HALF_LIFE_DAYS, min(MAX_HALF_LIFE_DAYS, stored * weight))


@dataclass
class ReaderHighlight:
    """A selected text range with optional reader notes."""

    id: str
    bookmark_id: int
    char_start: int
    char_end: int
    text: str
    source_sha256: str = ""
    quote_exact: str = ""
    quote_prefix: str = ""
    quote_suffix: str = ""
    anchor_status: str = "unverified"
    orphan_reason: str = ""
    anchor_history: List[dict] = field(default_factory=list)
    color: str = DEFAULT_HIGHLIGHT_COLOR
    note: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    modified_at: str = ""
    sr_interval: int = 0
    sr_repetitions: int = 0
    sr_ease: float = 2.5
    sr_next_review: str = ""
    # Resurfacing state. Highlights are not flashcards: there is no right
    # answer to grade, so recall decays with time and a highlight comes back
    # when the estimated chance of remembering it falls to half.
    sr_half_life: float = 0.0
    sr_last_seen: str = ""
    sr_weight: float = 1.0

    @property
    def color_hex(self) -> str:
        return HIGHLIGHT_COLORS[self.color]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["color"] = normalize_highlight_color(payload.get("color", ""))
        payload["source_sha256"] = _clean_digest(payload.get("source_sha256"))
        payload["quote_exact"] = str(
            payload.get("quote_exact") or payload.get("text") or ""
        )
        payload["text"] = payload["quote_exact"]
        payload["quote_prefix"] = str(payload.get("quote_prefix") or "")[
            -SELECTOR_CONTEXT_CHARS:
        ]
        payload["quote_suffix"] = str(payload.get("quote_suffix") or "")[
            :SELECTOR_CONTEXT_CHARS
        ]
        if payload.get("anchor_status") not in ANCHOR_STATUSES:
            payload["anchor_status"] = "unverified"
        payload["orphan_reason"] = str(payload.get("orphan_reason") or "")[:500]
        payload["anchor_history"] = _clean_anchor_history(
            payload.get("anchor_history")
        )
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "ReaderHighlight":
        now = _now()
        start = max(0, _clean_int(data.get("char_start")))
        end = max(start, _clean_int(data.get("char_end"), start))
        exact = str(data.get("quote_exact") or data.get("text") or "")
        digest = _clean_digest(data.get("source_sha256"))
        status = str(data.get("anchor_status") or "unverified")
        if status not in ANCHOR_STATUSES or (not digest and status != "orphaned"):
            status = "unverified"
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            bookmark_id=_clean_int(data.get("bookmark_id")),
            char_start=start,
            char_end=end,
            text=exact,
            source_sha256=digest,
            quote_exact=exact,
            quote_prefix=str(data.get("quote_prefix") or "")[
                -SELECTOR_CONTEXT_CHARS:
            ],
            quote_suffix=str(data.get("quote_suffix") or "")[
                :SELECTOR_CONTEXT_CHARS
            ],
            anchor_status=status,
            orphan_reason=str(data.get("orphan_reason") or "")[:500],
            anchor_history=_clean_anchor_history(data.get("anchor_history")),
            color=normalize_highlight_color(str(data.get("color") or "")),
            note=str(data.get("note") or ""),
            tags=[str(tag).strip() for tag in data.get("tags", []) if str(tag).strip()]
            if isinstance(data.get("tags", []), (list, tuple, set))
            else [],
            created_at=str(data.get("created_at") or now),
            modified_at=str(data.get("modified_at") or data.get("created_at") or now),
            sr_interval=_clean_int(data.get("sr_interval")),
            sr_repetitions=_clean_int(data.get("sr_repetitions")),
            sr_ease=float(data.get("sr_ease", 2.5) or 2.5),
            sr_next_review=str(data.get("sr_next_review") or ""),
            sr_half_life=_clean_half_life(data.get("sr_half_life")),
            sr_last_seen=str(data.get("sr_last_seen") or ""),
            sr_weight=_clean_weight(data.get("sr_weight")),
        )


def _anchor_event(
    highlight: ReaderHighlight,
    *,
    action: str,
    to_start: int | None = None,
    to_end: int | None = None,
    to_digest: str = "",
    reason: str = "",
) -> dict:
    event = {
        "at": _now(),
        "action": str(action)[:80],
        "from_start": highlight.char_start,
        "from_end": highlight.char_end,
        "from_source_sha256": highlight.source_sha256,
    }
    if to_start is not None:
        event["to_start"] = int(to_start)
    if to_end is not None:
        event["to_end"] = int(to_end)
    if to_digest:
        event["to_source_sha256"] = to_digest
    if reason:
        event["reason"] = str(reason)[:500]
    return event


def _append_anchor_event(highlight: ReaderHighlight, event: dict) -> None:
    highlight.anchor_history = _clean_anchor_history(
        [*highlight.anchor_history, event]
    )


def _orphan_highlight(
    highlight: ReaderHighlight,
    *,
    reason: str,
    current_digest: str = "",
) -> tuple[ReaderHighlight, bool]:
    if (
        highlight.anchor_status == "orphaned"
        and highlight.orphan_reason == reason
    ):
        return highlight, False
    _append_anchor_event(
        highlight,
        _anchor_event(
            highlight,
            action="orphaned",
            to_digest=current_digest,
            reason=reason,
        ),
    )
    highlight.anchor_status = "orphaned"
    highlight.orphan_reason = reason
    highlight.modified_at = _now()
    return highlight, True


def _quote_occurrences(source: str, exact: str, *, limit: int = 1001) -> List[int]:
    offsets: List[int] = []
    cursor = 0
    while len(offsets) < limit:
        found = source.find(exact, cursor)
        if found < 0:
            break
        offsets.append(found)
        cursor = found + 1
    return offsets


def reconcile_highlight_anchor(
    highlight: ReaderHighlight,
    source_text: str,
) -> tuple[ReaderHighlight, bool]:
    """Resolve one quote selector against current source text deterministically."""
    resolved = deepcopy(highlight)
    source = str(source_text or "")
    exact = str(resolved.quote_exact or resolved.text or "")
    resolved.quote_exact = exact
    resolved.text = exact
    if not source:
        return _orphan_highlight(
            resolved,
            reason="source text is unavailable",
        )
    current_digest = source_text_sha256(source)
    start = resolved.char_start
    end = resolved.char_end
    offsets_match = (
        0 <= start < end <= len(source)
        and source[start:end] == exact
    )
    if resolved.source_sha256 == current_digest:
        if not offsets_match:
            return _orphan_highlight(
                resolved,
                reason="stored offsets do not match the unchanged source",
                current_digest=current_digest,
            )
        was_orphaned = resolved.anchor_status == "orphaned"
        changed = (
            resolved.anchor_status != "anchored"
            or bool(resolved.orphan_reason)
        )
        if was_orphaned:
            _append_anchor_event(
                resolved,
                _anchor_event(
                    resolved,
                    action="anchor-restored",
                    to_start=start,
                    to_end=end,
                    to_digest=current_digest,
                ),
            )
        resolved.anchor_status = "anchored"
        resolved.orphan_reason = ""
        if changed:
            resolved.modified_at = _now()
        return resolved, changed

    if not resolved.source_sha256 and offsets_match:
        prefix, suffix = _selector_context(source, start, end)
        _append_anchor_event(
            resolved,
            _anchor_event(
                resolved,
                action="legacy-anchor-migrated",
                to_start=start,
                to_end=end,
                to_digest=current_digest,
            ),
        )
        resolved.source_sha256 = current_digest
        resolved.quote_prefix = prefix
        resolved.quote_suffix = suffix
        resolved.anchor_status = "anchored"
        resolved.orphan_reason = ""
        resolved.modified_at = _now()
        return resolved, True

    if not exact:
        return _orphan_highlight(
            resolved,
            reason="exact quote selector is empty",
            current_digest=current_digest,
        )
    occurrences = _quote_occurrences(source, exact)
    if not occurrences:
        return _orphan_highlight(
            resolved,
            reason="exact quote was not found in the current source",
            current_digest=current_digest,
        )
    candidates = occurrences
    if len(candidates) > 1:
        contextual = []
        for candidate in candidates:
            candidate_end = candidate + len(exact)
            prefix_ok = (
                not resolved.quote_prefix
                or source[max(0, candidate - len(resolved.quote_prefix)):candidate]
                == resolved.quote_prefix
            )
            suffix_ok = (
                not resolved.quote_suffix
                or source[candidate_end:candidate_end + len(resolved.quote_suffix)]
                == resolved.quote_suffix
            )
            if prefix_ok and suffix_ok:
                contextual.append(candidate)
        candidates = contextual
    if len(candidates) != 1:
        return _orphan_highlight(
            resolved,
            reason="exact quote has multiple possible matches",
            current_digest=current_digest,
        )

    new_start = candidates[0]
    new_end = new_start + len(exact)
    prefix, suffix = _selector_context(source, new_start, new_end)
    _append_anchor_event(
        resolved,
        _anchor_event(
            resolved,
            action="automatic-reanchor",
            to_start=new_start,
            to_end=new_end,
            to_digest=current_digest,
        ),
    )
    resolved.char_start = new_start
    resolved.char_end = new_end
    resolved.source_sha256 = current_digest
    resolved.quote_prefix = prefix
    resolved.quote_suffix = suffix
    resolved.anchor_status = "reanchored"
    resolved.orphan_reason = ""
    resolved.modified_at = _now()
    return resolved, True


class ReaderAnnotationStore:
    """Persisted reader highlight CRUD."""

    def __init__(self, filepath: Path | None = None):
        self.filepath = Path(filepath) if filepath is not None else app_constants.READER_ANNOTATIONS_FILE
        self._lock = threading.RLock()
        self._store = AtomicDocumentStore(
            self.filepath,
            schema="bookmark-organizer-pro/reader-annotations",
            current_version=2,
            default_factory=list,
            migrations={
                0: _migrate_reader_annotations_v0,
                1: _migrate_reader_annotations_v1,
            },
            validator=_validate_reader_annotations,
        )
        self._revision = 0
        self._highlights: Dict[str, ReaderHighlight] = {}
        self._committed_highlights: Dict[str, ReaderHighlight] = {}
        self._load()

    @property
    def storage_status(self):
        return self._store.status

    def _load(self) -> None:
        data = self._store.load()
        self._revision = self._store.revision
        items = data.get("highlights", []) if isinstance(data, dict) else data
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
            self._committed_highlights = deepcopy(self._highlights)

    def _save(self) -> None:
        with self._lock:
            highlights = sorted(
                self._highlights.values(),
                key=lambda item: (item.bookmark_id, item.char_start, item.created_at),
            )
            payload = [item.to_dict() for item in highlights]
            try:
                revision = self._store.save(payload, expected_revision=self._revision)
            except Exception:
                self._highlights = deepcopy(self._committed_highlights)
                raise
            self._revision = revision
            self._committed_highlights = deepcopy(self._highlights)

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
        prefix, suffix = _selector_context(source, start, end)
        now = _now()
        highlight = ReaderHighlight(
            id=uuid.uuid4().hex,
            bookmark_id=int(bookmark_id),
            char_start=start,
            char_end=end,
            text=selected,
            source_sha256=source_text_sha256(source),
            quote_exact=selected,
            quote_prefix=prefix,
            quote_suffix=suffix,
            anchor_status="anchored",
            color=normalize_highlight_color(color),
            note=str(note or ""),
            created_at=now,
            modified_at=now,
        )
        with self._lock:
            self._highlights[highlight.id] = highlight
            self._save()
            return deepcopy(highlight)

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
            items = deepcopy([item for item in self._highlights.values() if item.bookmark_id == bid])
        return sorted(items, key=lambda item: (item.char_start, item.created_at))

    def reconcile_for_bookmark(
        self,
        bookmark_id: int,
        source_text: str,
        *,
        persist: bool = True,
    ) -> List[ReaderHighlight]:
        """Re-anchor every highlight for one bookmark and persist state changes."""
        bid = int(bookmark_id)
        changed = False
        items: List[ReaderHighlight] = []
        with self._lock:
            for highlight_id, current in list(self._highlights.items()):
                if current.bookmark_id != bid:
                    continue
                resolved, item_changed = reconcile_highlight_anchor(
                    current,
                    source_text,
                )
                if item_changed and persist:
                    self._highlights[highlight_id] = resolved
                    changed = True
                items.append(resolved)
            if changed and persist:
                self._save()
        return sorted(items, key=lambda item: (item.char_start, item.created_at))

    def relink(
        self,
        highlight_id: str,
        source_text: str,
        char_start: int,
        char_end: int,
    ) -> Optional[ReaderHighlight]:
        """Manually relink an orphan while preserving its identity and metadata."""
        source = str(source_text or "")
        start = _clean_int(char_start)
        end = _clean_int(char_end)
        if start < 0 or end <= start or end > len(source):
            raise ValueError("highlight range is outside the extracted text")
        selected = source[start:end]
        if not selected.strip():
            raise ValueError("highlight selection cannot be blank")
        with self._lock:
            highlight = self._highlights.get(str(highlight_id))
            if highlight is None:
                return None
            if highlight.anchor_status != "orphaned":
                raise ValueError("only orphaned highlights can be relinked")
            digest = source_text_sha256(source)
            prefix, suffix = _selector_context(source, start, end)
            _append_anchor_event(
                highlight,
                _anchor_event(
                    highlight,
                    action="manual-relink",
                    to_start=start,
                    to_end=end,
                    to_digest=digest,
                ),
            )
            highlight.char_start = start
            highlight.char_end = end
            highlight.text = selected
            highlight.source_sha256 = digest
            highlight.quote_exact = selected
            highlight.quote_prefix = prefix
            highlight.quote_suffix = suffix
            highlight.anchor_status = "reanchored"
            highlight.orphan_reason = ""
            highlight.modified_at = _now()
            self._save()
            return deepcopy(highlight)

    def list_all(self) -> List[ReaderHighlight]:
        with self._lock:
            items = deepcopy(list(self._highlights.values()))
        return sorted(items, key=lambda item: (item.bookmark_id, item.char_start, item.created_at))

    def get(self, highlight_id: str) -> Optional[ReaderHighlight]:
        with self._lock:
            highlight = self._highlights.get(str(highlight_id))
            return deepcopy(highlight) if highlight is not None else None

    def delete(self, highlight_id: str) -> bool:
        return self.delete_and_return(highlight_id) is not None

    def delete_and_return(self, highlight_id: str) -> Optional[ReaderHighlight]:
        """Delete one highlight and return an exact session-safe copy for undo."""
        with self._lock:
            highlight = self._highlights.pop(str(highlight_id), None)
            if highlight is None:
                return None
            deleted = deepcopy(highlight)
            self._save()
            return deleted

    def restore(self, highlight: ReaderHighlight) -> bool:
        """Restore a previously deleted highlight without changing its identity or metadata."""
        if not isinstance(highlight, ReaderHighlight):
            raise TypeError("highlight must be a ReaderHighlight")
        restored = deepcopy(highlight)
        with self._lock:
            if restored.id in self._highlights:
                return False
            self._highlights[restored.id] = restored
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

    def recall_probability(self, highlight: ReaderHighlight, now: Optional[datetime] = None) -> float:
        """Estimated chance the reader still remembers this highlight."""
        now = now or datetime.now()
        seen = _last_surfaced_at(highlight)
        if seen is None:
            # Never surfaced, so there is nothing to have forgotten yet and the
            # highlight is due on its first pass.
            return 0.0
        half_life = _effective_half_life(highlight)
        elapsed_days = max(0.0, (now - seen).total_seconds() / 86400.0)
        return 2.0 ** (-elapsed_days / half_life) if half_life > 0 else 0.0

    def due_for_review(self, today: Optional[datetime] = None) -> List[ReaderHighlight]:
        """Return highlights whose recall has decayed to even odds or worse.

        A highlight never surfaced before is always due; after that it comes
        back when the estimated chance of recall reaches 50 percent, which is
        what the half-life encodes.
        """
        now = today or datetime.now()
        with self._lock:
            due = [
                h for h in self._highlights.values()
                if self.recall_probability(h, now) <= RECALL_DUE_THRESHOLD
            ]
            ranked = sorted(
                deepcopy(due),
                key=lambda h: (self.recall_probability(h, now), h.created_at),
            )
        return ranked

    def set_review_pace(self, highlight_id: str, pace: str) -> bool:
        """Choose how often a highlight resurfaces: soon, later, or someday."""
        key = str(pace or "").strip().lower()
        if key not in REVIEW_PACES:
            raise ValueError(f"Unknown review pace {pace!r}; choose from {', '.join(REVIEW_PACES)}")
        with self._lock:
            highlight = self._highlights.get(str(highlight_id))
            if highlight is None:
                return False
            highlight.sr_half_life = float(REVIEW_PACES[key])
            if not highlight.sr_last_seen:
                highlight.sr_last_seen = _now()
            highlight.modified_at = _now()
            self._save()
            return True

    def set_source_weight(self, highlight_id: str, weight: float) -> bool:
        """Up- or down-weight one highlight's source, as Readwise's review does.

        A weight above 1 stretches the half-life so the highlight returns less
        often; below 1 brings it back sooner.
        """
        with self._lock:
            highlight = self._highlights.get(str(highlight_id))
            if highlight is None:
                return False
            highlight.sr_weight = _clean_weight(weight)
            highlight.modified_at = _now()
            self._save()
            return True

    def record_review(self, highlight_id: str, quality: int, now: Optional[datetime] = None) -> bool:
        """Record that a highlight was resurfaced. quality: 0-5, kept for compatibility.

        The 0-5 scale predates this scheduler and is still accepted by the CLI
        and MCP tools. It now adjusts the half-life instead of an SM-2 interval:
        a confident recall stretches it, a failed one collapses it.
        """
        quality = max(0, min(5, int(quality)))
        stamp = now or datetime.now()
        with self._lock:
            h = self._highlights.get(str(highlight_id))
            if h is None:
                return False

            half_life = _effective_half_life(h) / max(0.1, h.sr_weight or 1.0)
            if quality < 3:
                half_life = MIN_HALF_LIFE_DAYS
                h.sr_repetitions = 0
            else:
                # 3 holds the pace, 4 and 5 stretch it progressively.
                half_life = min(MAX_HALF_LIFE_DAYS, half_life * (1.0 + 0.5 * (quality - 3)))
                h.sr_repetitions += 1

            h.sr_half_life = max(MIN_HALF_LIFE_DAYS, half_life)
            h.sr_last_seen = stamp.isoformat()
            # Legacy fields stay coherent so an older reader still sees a date.
            h.sr_interval = max(1, round(_effective_half_life(h)))
            h.sr_next_review = (stamp + timedelta(days=h.sr_interval)).date().isoformat()
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
        lines.extend(
            [
                f"### Highlight {index}",
                "",
                f"- Color: {item.color}",
                f"- Range: {item.char_start}-{item.char_end}",
                f"- Anchor: {item.anchor_status}"
                + (f" ({item.orphan_reason})" if item.orphan_reason else ""),
                f"- Source SHA-256: {item.source_sha256 or 'unverified'}",
                "",
            ]
        )
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


ANNOTATION_EXPORT_SCHEMA = "bookmark-organizer-pro/annotations-v2"
LEGACY_ANNOTATION_EXPORT_SCHEMA = "bookmark-organizer-pro/annotations-v1"
DEFAULT_ANNOTATION_FIELDS = (
    "document_id",
    "document_title",
    "document_url",
    "document_category",
    "document_tags",
    "document_notes",
    "document_created_at",
    "document_modified_at",
    "highlight_id",
    "highlight_text",
    "highlight_color",
    "highlight_tags",
    "highlight_note",
    "highlight_created_at",
    "highlight_modified_at",
    "highlight_anchor_status",
    "highlight_orphan_reason",
    "highlight_source_sha256",
    "highlight_quote_exact",
    "highlight_quote_prefix",
    "highlight_quote_suffix",
    "highlight_anchor_history",
    "review_interval",
    "review_repetitions",
    "review_ease",
    "review_next",
    "source_link",
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
        "- Anchor: {highlight_anchor_status} {highlight_orphan_reason}\n"
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
        records.append(
            {
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
                "highlight_anchor_status": item.anchor_status,
                "highlight_orphan_reason": item.orphan_reason,
                "highlight_source_sha256": item.source_sha256,
                "highlight_quote_exact": item.quote_exact or item.text,
                "highlight_quote_prefix": item.quote_prefix,
                "highlight_quote_suffix": item.quote_suffix,
                "highlight_anchor_history": deepcopy(item.anchor_history),
                "review_interval": item.sr_interval,
                "review_repetitions": item.sr_repetitions,
                "review_ease": item.sr_ease,
                "review_next": item.sr_next_review,
                "source_link": source_link,
            }
        )
    return records


def render_annotation_export(records: Sequence[Mapping], template: AnnotationExportTemplate) -> str:
    """Render records using a validated template, deterministically."""
    if template.format == "json":
        selected = [{field: record.get(field, "") for field in template.fields} for record in records]
        return (
            json.dumps({"schema": ANNOTATION_EXPORT_SCHEMA, "records": selected}, indent=2, ensure_ascii=False) + "\n"
        )
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
        if (
            not isinstance(payload, dict)
            or payload.get("schema")
            not in {ANNOTATION_EXPORT_SCHEMA, LEGACY_ANNOTATION_EXPORT_SCHEMA}
        ):
            raise ValueError("unsupported annotation export schema")
        records = payload.get("records", [])
        if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
            raise ValueError("annotation export records must be objects")
        return records
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ValueError("round-trip parsing supports CSV and JSON annotation exports")
