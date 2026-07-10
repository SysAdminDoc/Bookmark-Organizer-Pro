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


@dataclass(frozen=True)
class CollectionPulseViewModel:
    """Compact health and next-action state for the contextual rail."""

    health_score: int
    health_label: str
    healthy: int
    needs_review: int
    issues: int
    metrics: Mapping[str, int]
    action_key: str
    action_title: str
    action_detail: str


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
    bookmarks = list(bookmarks or [])
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
    if not isinstance(stats, Mapping):
        stats = {}
    all_bookmarks = list(all_bookmarks or [])
    visible_count = _safe_int(visible_count)
    total_count = _safe_int(total_count)

    metrics = {
        "visible": visible_count,
        "pinned": _safe_int(stats.get("pinned", 0)),
        "broken": _safe_int(stats.get("broken", 0)),
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
        category_counts = stats.get("category_counts", {})
        if not isinstance(category_counts, Mapping):
            category_counts = {}
        active_category_count = sum(
            1 for count in category_counts.values()
            if _safe_int(count) > 0
        )
        category_phrase = pluralize(active_category_count, "category", "categories")
        title = "Library Overview"
        detail = (
            f"{pluralize(total_count, 'bookmark')} organized across {category_phrase}."
        )

    return CollectionSummaryViewModel(title=title, detail=detail, metrics=metrics)


def build_collection_pulse(
    *, stats: Mapping, all_bookmarks: Sequence, health_score: int
) -> CollectionPulseViewModel:
    """Build a mutually exclusive health split and one useful next action."""
    if not isinstance(stats, Mapping):
        stats = {}
    all_bookmarks = list(all_bookmarks or [])
    total = _safe_int(stats.get("total_bookmarks", len(all_bookmarks)))
    broken_ids = {
        getattr(bookmark, "id", index)
        for index, bookmark in enumerate(all_bookmarks)
        if not bool(getattr(bookmark, "is_valid", True))
    }
    review_ids = {
        getattr(bookmark, "id", index)
        for index, bookmark in enumerate(all_bookmarks)
        if (
            bool(getattr(bookmark, "is_valid", True))
            and (
                not str(getattr(bookmark, "category", "") or "").strip()
                or _is_untagged(bookmark)
            )
        )
    }
    issues = len(broken_ids)
    needs_review = len(review_ids)
    healthy = max(0, total - issues - needs_review)

    category_counts = stats.get("category_counts", {})
    if not isinstance(category_counts, Mapping):
        category_counts = {}
    metrics = {
        "total": total,
        "tagged": _safe_int(stats.get("with_tags", 0)),
        "collections": sum(1 for value in category_counts.values() if _safe_int(value) > 0),
        "broken": _safe_int(stats.get("broken", issues)),
    }

    score = max(0, min(100, _safe_int(health_score))) if total else 0
    if total == 0:
        health_label = "Ready"
        action = (
            "import",
            "Import your bookmarks",
            "Bring in your bookmarks to unlock collection insights and recommendations.",
        )
    elif metrics["broken"]:
        health_label = "Needs review"
        action = (
            "broken",
            "Review broken links",
            f"Check {pluralize(metrics['broken'], 'link')} that could not be reached.",
        )
    elif _safe_int(stats.get("duplicate_bookmarks", 0)):
        duplicates = _safe_int(stats.get("duplicate_bookmarks", 0))
        health_label = "Needs review"
        action = (
            "duplicates",
            "Resolve duplicate bookmarks",
            f"Review {pluralize(duplicates, 'duplicate')} and keep the best copy.",
        )
    elif needs_review:
        health_label = "Good"
        action = (
            "untagged",
            "Organize unfinished items",
            f"Add context to {pluralize(needs_review, 'bookmark')} that need tags or a collection.",
        )
    else:
        health_label = "Healthy" if score >= 70 else "Good"
        action = (
            "search",
            "Rediscover your library",
            "Search by topic, domain, or tag to return to something useful.",
        )

    return CollectionPulseViewModel(
        health_score=score,
        health_label=health_label,
        healthy=healthy,
        needs_review=needs_review,
        issues=issues,
        metrics=metrics,
        action_key=action[0],
        action_title=action[1],
        action_detail=action[2],
    )


def _safe_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
