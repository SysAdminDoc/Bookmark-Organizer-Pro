"""Pure view-model builders for the desktop UI.

This module keeps view state, count math, and summary copy out of Tkinter
widgets. The functions accept plain bookmark-like objects, making them easy to
unit test and reusable for a future Qt or web frontend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Mapping, Optional, Sequence

from .foundation import format_compact_count, pluralize, truncate_middle


@dataclass(frozen=True)
class FilterCountsViewModel:
    """Counts shown in the quick-filter sidebar."""

    all: int = 0
    pinned: int = 0
    recent: int = 0
    broken: int = 0
    untagged: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "All": self.all,
            "Pinned": self.pinned,
            "Recent": self.recent,
            "Broken": self.broken,
            "Untagged": self.untagged,
        }


@dataclass(frozen=True)
class CollectionSummaryViewModel:
    """State for the summary strip above the bookmark list."""

    title: str
    detail: str
    metrics: Mapping[str, int]


def _is_recent(bookmark, cutoff: datetime) -> bool:
    created_at = getattr(bookmark, "created_at", "") or ""
    if not created_at:
        return False
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is not None:
            created = created.replace(tzinfo=None)
        return created >= cutoff
    except Exception:
        return str(created_at) >= cutoff.isoformat()


def _is_untagged(bookmark) -> bool:
    return not getattr(bookmark, "tags", None) and not getattr(bookmark, "ai_tags", None)


def build_filter_counts(bookmarks: Sequence, now: Optional[datetime] = None) -> FilterCountsViewModel:
    """Build quick-filter counts from bookmark-like objects."""
    now = now or datetime.now()
    week_ago = now - timedelta(days=7)
    return FilterCountsViewModel(
        all=len(bookmarks),
        pinned=sum(1 for bm in bookmarks if bool(getattr(bm, "is_pinned", False))),
        recent=sum(1 for bm in bookmarks if _is_recent(bm, week_ago)),
        broken=sum(1 for bm in bookmarks if not bool(getattr(bm, "is_valid", True))),
        untagged=sum(1 for bm in bookmarks if _is_untagged(bm)),
    )


def build_collection_summary(
    *,
    visible_count: int,
    total_count: int,
    stats: Mapping,
    all_bookmarks: Sequence,
    query: str = "",
    quick_filter: str = "",
    current_category: Optional[str] = None,
) -> CollectionSummaryViewModel:
    """Build the summary strip state for the current library view."""
    metrics = {
        "visible": visible_count,
        "pinned": int(stats.get("pinned", 0) or 0),
        "broken": int(stats.get("broken", 0) or 0),
        "untagged": sum(1 for bm in all_bookmarks if _is_untagged(bm)),
    }

    query = str(query or "").strip()
    quick_filter = str(quick_filter or "").strip()
    current_category = str(current_category or "").strip()

    if total_count == 0:
        title = "No Bookmarks Yet"
        detail = (
            "Start with an import or save a single URL. Your library health, "
            "categories, and domains will appear here."
        )
    elif query:
        title = "Search Results"
        detail = (
            f"Showing {pluralize(visible_count, 'bookmark')} for "
            f"“{truncate_middle(query, 64)}” out of {format_compact_count(total_count)} total."
        )
    elif quick_filter:
        title = f"{quick_filter.title()} View"
        detail = f"Showing {pluralize(visible_count, 'bookmark')} in this focused view."
    elif current_category:
        title = current_category
        detail = f"Showing {pluralize(visible_count, 'bookmark')} in this category."
    else:
        active_category_count = sum(
            1 for count in stats.get("category_counts", {}).values()
            if int(count or 0) > 0
        )
        category_phrase = pluralize(active_category_count, "category", "categories")
        title = "Library Overview"
        detail = (
            f"{pluralize(total_count, 'bookmark')} organized across {category_phrase}."
        )

    return CollectionSummaryViewModel(title=title, detail=detail, metrics=metrics)
