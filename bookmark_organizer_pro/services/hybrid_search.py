"""Hybrid keyword + semantic search via Reciprocal Rank Fusion.

Uses BOP's existing SearchEngine for keyword/FTS-style ranking and the
local VectorStore for semantic ranking, then merges the two with RRF
(k=60). Falls back to keyword-only when no embeddings are available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.search import SearchEngine
from bookmark_organizer_pro.services.embeddings import EmbeddingService
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
            age_days = max(0, (datetime.now() - dt.replace(tzinfo=None)).days)
            return math.exp(-0.693 * age_days / max(1, half_life_days))
        except Exception:
            return 0.5

    def search(self, bookmarks: Sequence[Bookmark], query: str,
               limit: int = 50, semantic_k: int = 50,
               time_weight: float = 0.0) -> List[HybridResult]:
        if not query:
            return []

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

        if not semantic_ids:
            return [
                HybridResult(bookmark=bm, score=score, keyword_rank=i)
                for i, (bm, score) in enumerate(keyword_hits[:limit])
            ]

        fused = reciprocal_rank_fusion([keyword_ids, semantic_ids])
        bm_lookup = {bm.id: bm for bm in bookmarks}
        keyword_rank = {bid: i for i, bid in enumerate(keyword_ids)}
        semantic_rank = {bid: i for i, bid in enumerate(semantic_ids)}

        results: List[HybridResult] = []
        tw = max(0.0, min(1.0, time_weight))
        for bid, score in fused[:limit * 2]:
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
        return results[:limit]
