"""Read-later queue helper.

Read-later is a first-class boolean field on the Bookmark model (rather
than a tag) with a separate ordering. This service exposes the queue
operations: enqueue, dequeue, reorder, peek, complete.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from bookmark_organizer_pro.models import Bookmark


class ReadLaterQueue:
    """Pure-function operations over a bookmark collection's read-later queue."""

    @staticmethod
    def enqueue(bookmark: Bookmark, position: Optional[int] = None) -> None:
        bookmark.read_later = True
        if position is not None:
            bookmark.read_later_position = max(0, int(position))

    @staticmethod
    def dequeue(bookmark: Bookmark) -> None:
        bookmark.read_later = False
        bookmark.read_later_position = 0

    @staticmethod
    def list_queue(bookmarks: Iterable[Bookmark]) -> List[Bookmark]:
        out = [b for b in bookmarks if b.read_later and not b.is_archived]
        out.sort(key=lambda b: (b.read_later_position, b.created_at))
        return out

    @staticmethod
    def reorder(bookmarks: Sequence[Bookmark],
                bookmark_ids_in_order: List[int]) -> int:
        """Apply a new ordering to the read-later queue. Returns count moved."""
        bid_to_pos = {bid: i for i, bid in enumerate(bookmark_ids_in_order)}
        moved = 0
        for bm in bookmarks:
            if bm.id in bid_to_pos:
                new_pos = bid_to_pos[bm.id]
                if bm.read_later_position != new_pos or not bm.read_later:
                    bm.read_later = True
                    bm.read_later_position = new_pos
                    moved += 1
        return moved

    @staticmethod
    def peek_next(bookmarks: Iterable[Bookmark]) -> Optional[Bookmark]:
        queue = ReadLaterQueue.list_queue(bookmarks)
        return queue[0] if queue else None

    @staticmethod
    def complete(bookmark: Bookmark) -> None:
        bookmark.read_later = False
        bookmark.read_later_position = 0
        from datetime import datetime as _dt
        bookmark.last_visited = _dt.now().isoformat()
        bookmark.visit_count += 1
