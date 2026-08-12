"""Paginated, metadata-only projection for collection-wide reader highlights."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import unicodedata
from typing import Iterable, Sequence

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.reader_annotations import (
    ANCHOR_STATUSES,
    HIGHLIGHT_COLORS,
    ReaderAnnotationStore,
    ReaderHighlight,
    export_annotations,
    normalize_highlight_color,
)


MAX_PAGE_SIZE = 200
MAX_OFFSET = 1_000_000
MAX_DELETE_IDS = 500
MAX_EXPORT_HIGHLIGHTS = 10_000
REVIEW_STATUSES = {"all", "new", "due", "scheduled", "reviewed"}
ANCHOR_FILTERS = {"all", *ANCHOR_STATUSES, "anchored"}


def _fold(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def _clean_limit(value: object, default: int = 50) -> int:
    try:
        return max(1, min(MAX_PAGE_SIZE, int(value)))
    except (TypeError, ValueError):
        return default


def _clean_offset(value: object) -> int:
    try:
        return max(0, min(MAX_OFFSET, int(value)))
    except (TypeError, ValueError):
        return 0


def _review_status(highlight: ReaderHighlight, today: date | None = None) -> str:
    """Return a stable filter label for one SM-2 review state."""
    today = today or date.today()
    next_review = str(highlight.sr_next_review or "").strip()
    if not next_review and highlight.sr_repetitions <= 0:
        return "new"
    if not next_review or next_review <= today.isoformat():
        return "due"
    return "scheduled"


def _anchor_matches(highlight: ReaderHighlight, requested: str) -> bool:
    normalized = _fold(requested)
    if not normalized or normalized == "all":
        return True
    if normalized == "orphan":
        normalized = "orphaned"
    if normalized == "anchored":
        return highlight.anchor_status in {"anchored", "reanchored"}
    return _fold(highlight.anchor_status) == normalized


@dataclass(frozen=True)
class HighlightWorkspaceQuery:
    """Validated filters shared by desktop, CLI, and MCP consumers."""

    text: str = ""
    note: str = ""
    tag: str = ""
    color: str = ""
    bookmark_id: int | None = None
    review_status: str = "all"
    anchor_status: str = "all"
    limit: int = 50
    offset: int = 0

    @classmethod
    def create(
        cls,
        *,
        text: object = "",
        note: object = "",
        tag: object = "",
        color: object = "",
        bookmark_id: object = None,
        review_status: object = "all",
        anchor_status: object = "all",
        limit: object = 50,
        offset: object = 0,
    ) -> "HighlightWorkspaceQuery":
        try:
            normalized_bookmark_id = (
                int(bookmark_id) if bookmark_id is not None and str(bookmark_id).strip() else None
            )
        except (TypeError, ValueError):
            normalized_bookmark_id = None
        normalized_review = _fold(review_status) or "all"
        if normalized_review not in REVIEW_STATUSES:
            raise ValueError("review_status must be all, new, due, scheduled, or reviewed")
        normalized_anchor = _fold(anchor_status) or "all"
        if normalized_anchor == "orphan":
            normalized_anchor = "orphaned"
        if normalized_anchor not in ANCHOR_FILTERS:
            raise ValueError("anchor_status is not supported")
        raw_color = _fold(color)
        normalized_color = normalize_highlight_color(color) if raw_color else ""
        supported_colors = {
            _fold(name) for name in HIGHLIGHT_COLORS
        } | {
            _fold(value) for value in HIGHLIGHT_COLORS.values()
        }
        if raw_color and raw_color not in supported_colors:
            raise ValueError("color is not supported")
        return cls(
            text=str(text or "").strip(),
            note=str(note or "").strip(),
            tag=str(tag or "").strip(),
            color=normalized_color,
            bookmark_id=normalized_bookmark_id,
            review_status=normalized_review,
            anchor_status=normalized_anchor,
            limit=_clean_limit(limit),
            offset=_clean_offset(offset),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "note": self.note,
            "tag": self.tag,
            "color": self.color,
            "bookmark_id": self.bookmark_id,
            "review_status": self.review_status,
            "anchor_status": self.anchor_status,
            "limit": self.limit,
            "offset": self.offset,
        }


@dataclass(frozen=True)
class HighlightWorkspaceRecord:
    """One highlight plus bookmark metadata; never loads page content."""

    highlight: ReaderHighlight
    bookmark_title: str = ""
    bookmark_url: str = ""
    bookmark_category: str = ""
    bookmark_tags: tuple[str, ...] = ()
    bookmark_exists: bool = True

    @property
    def id(self) -> str:
        return self.highlight.id

    @property
    def bookmark_id(self) -> int:
        return self.highlight.bookmark_id

    @property
    def review_status(self) -> str:
        return _review_status(self.highlight)

    @property
    def is_due(self) -> bool:
        return self.review_status in {"new", "due"}

    @property
    def preview(self) -> str:
        return " ".join(self.highlight.text.split())[:240]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "bookmark_id": self.bookmark_id,
            "bookmark": {
                "id": self.bookmark_id,
                "title": self.bookmark_title,
                "url": self.bookmark_url,
                "category": self.bookmark_category,
                "tags": list(self.bookmark_tags),
                "exists": self.bookmark_exists,
            },
            "text": self.highlight.text,
            "preview": self.preview,
            "note": self.highlight.note,
            "color": self.highlight.color,
            "color_hex": self.highlight.color_hex,
            "tags": list(self.highlight.tags),
            "anchor_status": self.highlight.anchor_status,
            "orphan_reason": self.highlight.orphan_reason,
            "review_status": self.review_status,
            "review_interval": self.highlight.sr_interval,
            "review_repetitions": self.highlight.sr_repetitions,
            "review_next": self.highlight.sr_next_review,
            "created_at": self.highlight.created_at,
            "modified_at": self.highlight.modified_at,
            "char_start": self.highlight.char_start,
            "char_end": self.highlight.char_end,
        }


@dataclass(frozen=True)
class HighlightWorkspacePage:
    """A bounded page of highlight metadata."""

    items: tuple[HighlightWorkspaceRecord, ...]
    total: int
    offset: int
    limit: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total

    @property
    def next_offset(self) -> int | None:
        return self.offset + len(self.items) if self.has_more else None

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "returned": len(self.items),
            "offset": self.offset,
            "limit": self.limit,
            "has_more": self.has_more,
            "next_offset": self.next_offset,
            "highlights": [item.to_dict() for item in self.items],
        }


class HighlightWorkspaceService:
    """Query, export, and recover highlights across the bookmark collection."""

    def __init__(
        self,
        *,
        store: ReaderAnnotationStore | None = None,
        bookmark_manager=None,
        bookmarks: Iterable[Bookmark] | None = None,
    ):
        self.store = store or ReaderAnnotationStore()
        self.bookmark_manager = bookmark_manager
        self._bookmarks = tuple(bookmarks) if bookmarks is not None else None

    def _bookmark_map(self) -> dict[int, Bookmark]:
        if self._bookmarks is not None:
            source = self._bookmarks
        elif self.bookmark_manager is not None:
            source = self.bookmark_manager.get_all_bookmarks()
        else:
            source = ()
        result = {}
        for bookmark in source:
            try:
                result[int(bookmark.id)] = bookmark
            except (AttributeError, TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _record(highlight: ReaderHighlight, bookmark: Bookmark | None) -> HighlightWorkspaceRecord:
        return HighlightWorkspaceRecord(
            highlight=highlight,
            bookmark_title=str(getattr(bookmark, "title", "") or "") if bookmark else "",
            bookmark_url=str(getattr(bookmark, "url", "") or "") if bookmark else "",
            bookmark_category=str(
                getattr(bookmark, "full_category_path", "")
                or getattr(bookmark, "category", "")
                or ""
            ) if bookmark else "",
            bookmark_tags=tuple(
                str(tag) for tag in getattr(bookmark, "tags", ()) if str(tag).strip()
            ) if bookmark else (),
            bookmark_exists=bookmark is not None,
        )

    def query(self, query: HighlightWorkspaceQuery | None = None, **filters) -> HighlightWorkspacePage:
        """Filter persisted highlight metadata without opening any source file."""
        query = query or HighlightWorkspaceQuery.create(**filters)
        bookmarks = self._bookmark_map()
        text = _fold(query.text)
        note = _fold(query.note)
        tag = _fold(query.tag)
        records = []
        for highlight in self.store.list_all():
            if query.bookmark_id is not None and highlight.bookmark_id != query.bookmark_id:
                continue
            if text and text not in _fold(highlight.text):
                continue
            if note and note not in _fold(highlight.note):
                continue
            if tag and not any(tag == _fold(item) for item in highlight.tags):
                continue
            if query.color and normalize_highlight_color(highlight.color) != query.color:
                continue
            current_review = _review_status(highlight)
            if query.review_status == "reviewed":
                if highlight.sr_repetitions <= 0:
                    continue
            elif query.review_status == "due":
                if current_review not in {"new", "due"}:
                    continue
            elif query.review_status == "new" and current_review != "new":
                continue
            elif query.review_status == "scheduled" and current_review != "scheduled":
                continue
            if not _anchor_matches(highlight, query.anchor_status):
                continue
            records.append(self._record(highlight, bookmarks.get(highlight.bookmark_id)))

        if query.review_status == "due":
            records.sort(
                key=lambda item: (
                    item.highlight.sr_next_review or "",
                    item.highlight.created_at,
                    item.id,
                )
            )
        else:
            records.sort(
                key=lambda item: (
                    str(item.highlight.modified_at or item.highlight.created_at or ""),
                    int(item.bookmark_id),
                    item.highlight.char_start,
                    item.id,
                ),
                reverse=True,
            )
        total = len(records)
        page = records[query.offset:query.offset + query.limit]
        return HighlightWorkspacePage(tuple(page), total, query.offset, query.limit)

    def get(self, highlight_id: str) -> HighlightWorkspaceRecord | None:
        highlight = self.store.get(str(highlight_id or ""))
        if highlight is None:
            return None
        return self._record(highlight, self._bookmark_map().get(highlight.bookmark_id))

    def delete_many(self, highlight_ids: Sequence[str]) -> tuple[ReaderHighlight, ...]:
        """Delete a bounded batch and return exact records for one-step undo."""
        deleted = []
        seen = set()
        for raw_id in list(highlight_ids or ())[:MAX_DELETE_IDS]:
            highlight_id = str(raw_id or "").strip()
            if not highlight_id or highlight_id in seen:
                continue
            seen.add(highlight_id)
            item = self.store.delete_and_return(highlight_id)
            if item is not None:
                deleted.append(item)
        return tuple(deleted)

    def restore_many(self, highlights: Sequence[ReaderHighlight]) -> int:
        restored = 0
        for highlight in list(highlights or ())[:MAX_DELETE_IDS]:
            if self.store.restore(highlight):
                restored += 1
        return restored

    def export(
        self,
        output_path: str | Path,
        *,
        query: HighlightWorkspaceQuery | None = None,
        highlight_ids: Sequence[str] | None = None,
        output_format: str | None = None,
        template_path: str | Path | None = None,
        changed_since: str | None = None,
    ) -> Path:
        """Export selected or filtered records without loading page content."""
        if highlight_ids:
            records = []
            bookmark_map = self._bookmark_map()
            seen = set()
            for raw_id in list(highlight_ids)[:MAX_EXPORT_HIGHLIGHTS]:
                highlight_id = str(raw_id or "").strip()
                if not highlight_id or highlight_id in seen:
                    continue
                seen.add(highlight_id)
                highlight = self.store.get(highlight_id)
                if highlight is not None:
                    records.append(
                        self._record(highlight, bookmark_map.get(highlight.bookmark_id))
                    )
        else:
            base = query or HighlightWorkspaceQuery.create(limit=MAX_PAGE_SIZE)
            first = self.query(
                HighlightWorkspaceQuery(
                    **{**base.to_dict(), "limit": MAX_PAGE_SIZE, "offset": 0}
                )
            )
            if first.total > MAX_EXPORT_HIGHLIGHTS:
                raise ValueError(f"export is limited to {MAX_EXPORT_HIGHLIGHTS} highlights")
            records = list(first.items)
            while first.has_more:
                first = self.query(
                    HighlightWorkspaceQuery(
                        **{**base.to_dict(), "limit": MAX_PAGE_SIZE, "offset": first.next_offset or 0}
                    )
                )
                records.extend(first.items)
        bookmarks = self._bookmark_map()
        bookmark_list_by_id = {}
        for item in records:
            if item.bookmark_id not in bookmark_list_by_id:
                bookmark_list_by_id[item.bookmark_id] = bookmarks.get(
                    item.bookmark_id,
                    Bookmark(
                        id=item.bookmark_id,
                        url=f"about:blank#bookmark-{item.bookmark_id}",
                        title=f"Missing bookmark {item.bookmark_id}",
                    ),
                )
        bookmark_list = list(bookmark_list_by_id.values())
        highlights = [item.highlight for item in records]
        return export_annotations(
            bookmark_list,
            highlights,
            output_path,
            output_format=output_format,
            template_path=template_path,
            changed_since=changed_since,
        )


HighlightWorkspace = HighlightWorkspaceService
GlobalHighlightsService = HighlightWorkspaceService


__all__ = [
    "ANCHOR_FILTERS",
    "GlobalHighlightsService",
    "HighlightWorkspace",
    "HighlightWorkspacePage",
    "HighlightWorkspaceQuery",
    "HighlightWorkspaceRecord",
    "HighlightWorkspaceService",
    "MAX_EXPORT_HIGHLIGHTS",
    "MAX_PAGE_SIZE",
    "REVIEW_STATUSES",
]
