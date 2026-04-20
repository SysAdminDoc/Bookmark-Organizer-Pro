"""On-this-day daily digest service.

Surfaces bookmarks saved on this calendar date in prior years (Shaarli-
inspired). Also produces "rediscovery picks" and "stale but high-value"
lists for the dashboard's morning view.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Sequence

from bookmark_organizer_pro.models import Bookmark


@dataclass
class DigestSection:
    title: str
    description: str
    bookmarks: List[Bookmark] = field(default_factory=list)


@dataclass
class DailyDigest:
    generated_at: str
    sections: List[DigestSection] = field(default_factory=list)


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


class DailyDigestService:
    """Compute "on this day" / "rediscover" lists."""

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()

    def build(self, bookmarks: Sequence[Bookmark],
              today: Optional[datetime] = None,
              rediscover_count: int = 5,
              read_later_count: int = 5) -> DailyDigest:
        today = today or datetime.now()
        sections: List[DigestSection] = []

        on_this_day = self._on_this_day(bookmarks, today)
        if on_this_day:
            sections.append(DigestSection(
                title="On this day",
                description=f"Bookmarks saved on {today.strftime('%B %d')} in previous years.",
                bookmarks=on_this_day,
            ))

        last_week = self._this_week_last_year(bookmarks, today)
        if last_week:
            sections.append(DigestSection(
                title="This week, one year ago",
                description="What you were saving last year around this time.",
                bookmarks=last_week,
            ))

        rediscover = self._rediscover(bookmarks, today, rediscover_count)
        if rediscover:
            sections.append(DigestSection(
                title="Rediscover",
                description="Random older saves you may have forgotten.",
                bookmarks=rediscover,
            ))

        read_later = self._read_later_top(bookmarks, read_later_count)
        if read_later:
            sections.append(DigestSection(
                title="Read later",
                description="Top of your read-later queue.",
                bookmarks=read_later,
            ))

        stale = self._stale_high_value(bookmarks, today)
        if stale:
            sections.append(DigestSection(
                title="Stale but loved",
                description=(
                    "Frequently-visited bookmarks you haven't opened in a while."
                ),
                bookmarks=stale,
            ))

        return DailyDigest(generated_at=today.isoformat(), sections=sections)

    # ------------------------------------------------------------------
    def _on_this_day(self, bookmarks, today) -> List[Bookmark]:
        out = []
        for bm in bookmarks:
            d = _parse_date(bm.created_at)
            if not d:
                continue
            if d.month == today.month and d.day == today.day and d.year < today.year:
                out.append(bm)
        out.sort(key=lambda b: b.created_at, reverse=True)
        return out[:10]

    def _this_week_last_year(self, bookmarks, today) -> List[Bookmark]:
        out = []
        anchor = today - timedelta(days=365)
        window_start = anchor - timedelta(days=3)
        window_end = anchor + timedelta(days=3)
        for bm in bookmarks:
            d = _parse_date(bm.created_at)
            if not d:
                continue
            if window_start <= d <= window_end:
                out.append(bm)
        out.sort(key=lambda b: b.created_at, reverse=True)
        return out[:8]

    def _rediscover(self, bookmarks, today, count) -> List[Bookmark]:
        candidates = []
        cutoff = today - timedelta(days=180)
        for bm in bookmarks:
            if bm.is_archived or bm.read_later:
                continue
            d = _parse_date(bm.created_at)
            if d and d < cutoff:
                candidates.append(bm)
        if not candidates:
            return []
        return self.rng.sample(candidates, min(count, len(candidates)))

    def _read_later_top(self, bookmarks, count) -> List[Bookmark]:
        out = [b for b in bookmarks if b.read_later and not b.is_archived]
        out.sort(key=lambda b: (b.read_later_position, -_parse_position(b)))
        return out[:count]

    def _stale_high_value(self, bookmarks, today) -> List[Bookmark]:
        cutoff = today - timedelta(days=120)
        out = []
        for bm in bookmarks:
            if bm.visit_count < 3 or bm.is_archived:
                continue
            d = _parse_date(bm.last_visited or bm.created_at)
            if d and d < cutoff:
                out.append(bm)
        out.sort(key=lambda b: b.visit_count, reverse=True)
        return out[:8]


def _parse_position(b: Bookmark) -> int:
    try:
        return int(b.read_later_position)
    except Exception:
        return 0
