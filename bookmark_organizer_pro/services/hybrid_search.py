"""Hybrid keyword + semantic search via Reciprocal Rank Fusion.

Uses BOP's existing SearchEngine for keyword/FTS-style ranking and the
local VectorStore for semantic ranking, then merges the two with RRF
(k=60). Falls back to keyword-only when no embeddings are available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.search import SearchEngine
from bookmark_organizer_pro.services.vector_store import (
    VectorStore,
    reciprocal_rank_fusion,
)


@dataclass
class HybridResult:
    bookmark: Bookmark
    score: float
    keyword_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    snippet: str = ""


class HybridSearch:
    """Combined keyword + semantic search over a bookmark collection."""

    def __init__(self, vector_store: VectorStore,
                 keyword_engine: Optional[SearchEngine] = None):
        self.vector_store = vector_store
        self.keyword_engine = keyword_engine or SearchEngine()

    @staticmethod
    def _recency_factor(bookmark: Bookmark, half_life_days: float = 180.0) -> float:
        """Exponential decay factor based on bookmark age. 1.0 = new, ~0.5 at half_life_days."""
        try:
            ts = bookmark.last_visited or bookmark.created_at
            if not ts:
                return 0.5
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            # Use UTC consistently to avoid timezone-offset skew
            from datetime import timezone
            now_utc = datetime.now(timezone.utc)
            dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            age_days = max(0, (now_utc - dt_utc).days)
            return math.exp(-0.693 * age_days / max(1, half_life_days))
        except Exception:
            return 0.5

    def search(self, bookmarks: Sequence[Bookmark], query: str,
               limit: int = 50, semantic_k: int = 50,
               time_weight: float = 0.0,
               offset: int = 0) -> List[HybridResult]:
        """Rank bookmarks by fusing keyword, semantic, and full-text results.

        ``offset`` pages through the fused ranking. Fusion still happens over
        the full candidate set, because paging the inputs separately would
        change which documents fuse together and make page 2 inconsistent with
        page 1.
        """
        if not query:
            return []
        offset = max(0, int(offset or 0))
        window = limit + offset
        # Semantic and full-text candidates must cover the whole window, or a
        # page past the default k silently degrades to keyword-only ranking.
        semantic_k = max(semantic_k, window)

        keyword_hits = self.keyword_engine.search(list(bookmarks), query)
        keyword_ids = [bm.id for bm, _ in keyword_hits]

        semantic_results = self.vector_store.search(query, k=semantic_k)
        semantic_ids: List[int] = []
        snippet_map: Dict[int, str] = {}
        for hit in semantic_results:
            bid = hit["bookmark_id"]
            if bid not in snippet_map:
                snippet_map[bid] = hit["text"][:300]
            if bid not in semantic_ids:
                semantic_ids.append(bid)

        fts_ids = self.vector_store.fts_search(query, k=semantic_k)

        if not semantic_ids and not fts_ids:
            return [
                HybridResult(bookmark=bm, score=score, keyword_rank=i)
                for i, (bm, score) in enumerate(keyword_hits[:window])
            ][offset:]

        rankings = [keyword_ids, semantic_ids]
        if fts_ids:
            rankings.append(fts_ids)
        fused = reciprocal_rank_fusion(rankings)
        bm_lookup = {bm.id: bm for bm in bookmarks}
        keyword_rank = {bid: i for i, bid in enumerate(keyword_ids)}
        semantic_rank = {bid: i for i, bid in enumerate(semantic_ids)}

        results: List[HybridResult] = []
        tw = max(0.0, min(1.0, time_weight))
        for bid, score in fused[:max(window * 2, limit * 2)]:
            bm = bm_lookup.get(bid)
            if bm is None:
                continue
            final_score = score
            if tw > 0:
                recency = self._recency_factor(bm)
                final_score = score * (1 - tw) + score * recency * tw
            results.append(HybridResult(
                bookmark=bm,
                score=final_score,
                keyword_rank=keyword_rank.get(bid),
                semantic_rank=semantic_rank.get(bid),
                snippet=snippet_map.get(bid, ""),
            ))
        results.sort(key=lambda r: r.score, reverse=True)
        # Ranking must finish before paging, or page 2 would be cut from a
        # different ordering than page 1.
        return results[offset:offset + limit]
