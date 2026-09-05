"""Hybrid duplicate detection: URL canonical → SimHash → embedding cosine.

Three layered passes, surfaced as a review queue (never auto-merge):
    1. URL canonical match (BookmarkManager.find_duplicates already does this)
    2. SimHash (k=3 Hamming) over title + extracted text — catches near
       duplicates with different URLs.
    3. Embedding cosine (≥0.92) — catches paraphrases and translations.

Optional dependency: `datasketch` for MinHash LSH if available; fallback
uses a 64-bit SimHash hand-rolled implementation.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.embeddings import EmbeddingService
from bookmark_organizer_pro.utils import normalize_url


WORD_RE = re.compile(r"\w{3,}")


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _simhash64(tokens: Sequence[str]) -> int:
    """64-bit SimHash via SHA-1 token hashing."""
    if not tokens:
        return 0
    bits = [0] * 64
    for tok in tokens:
        h = int.from_bytes(hashlib.sha1(tok.encode("utf-8", errors="replace")).digest()[:8], "big")
        for i in range(64):
            bits[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if bits[i] > 0:
            out |= (1 << i)
    return out


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    import math
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _read_text(bm: Bookmark) -> str:
    """Best-available text representation for fingerprinting."""
    parts = [bm.title or "", bm.description or ""]
    if bm.extracted_text_path:
        try:
            parts.append(Path(bm.extracted_text_path).read_text(encoding="utf-8")[:8000])
        except OSError:
            pass
    return "\n".join(parts)


@dataclass
class DuplicateGroup:
    method: str            # "url" | "simhash" | "embedding"
    canonical_id: int
    bookmark_ids: List[int]
    confidence: float = 1.0


@dataclass
class DuplicateReport:
    groups: List[DuplicateGroup] = field(default_factory=list)
    method_counts: Dict[str, int] = field(default_factory=dict)
    library_size: int = 0
    pairwise_examined: int = 0
    pairwise_skipped: int = 0

    @property
    def truncated(self) -> bool:
        """Whether the pairwise passes left part of the library uncompared."""
        return self.pairwise_skipped > 0

    def coverage_summary(self) -> str:
        """One line describing how much of the library the pairwise passes saw."""
        if not self.truncated:
            return f"Compared all {self.library_size} bookmarks."
        return (
            f"Compared {self.pairwise_examined} of {self.library_size} bookmarks; "
            f"{self.pairwise_skipped} were not compared because the near-duplicate "
            "passes are capped. Scan one collection at a time to cover the rest."
        )


class HybridDuplicateDetector:
    """Layered duplicate detection."""

    SIMHASH_THRESHOLD = 3       # bits Hamming distance
    EMBEDDING_THRESHOLD = 0.92  # cosine similarity
    MAX_PAIRWISE = 5000         # cap O(n²) passes to avoid minutes-long stalls

    def __init__(
        self,
        embedder: Optional[EmbeddingService] = None,
        *,
        max_pairwise: Optional[int] = None,
    ):
        self.embedder = embedder
        self.max_pairwise = self.MAX_PAIRWISE if max_pairwise is None else int(max_pairwise)

    def detect(self, bookmarks: Sequence[Bookmark]) -> DuplicateReport:
        report = DuplicateReport(
            method_counts={"url": 0, "simhash": 0, "embedding": 0},
            library_size=len(bookmarks),
        )
        seen_ids: set[int] = set()
        # Records that entered a pairwise pass. Everything the cap left out of
        # every pass is reported as skipped so no caller can read an empty
        # result as "this library has no near-duplicates".
        compared_ids: set[int] = set()
        pairwise_candidate_ids: set[int] = set()

        # --- Pass 1: URL canonical
        url_buckets: Dict[str, List[Bookmark]] = defaultdict(list)
        for bm in bookmarks:
            url_buckets[normalize_url(bm.url)].append(bm)
        for url, bms in url_buckets.items():
            if len(bms) > 1:
                ids = [b.id for b in bms]
                seen_ids.update(ids)
                report.groups.append(DuplicateGroup(
                    method="url", canonical_id=ids[0], bookmark_ids=ids, confidence=1.0,
                ))
                report.method_counts["url"] += 1

        pass2_candidates = [bm for bm in bookmarks if bm.id not in seen_ids]
        pairwise_candidate_ids.update(bm.id for bm in pass2_candidates)
        remaining = pass2_candidates[:self.max_pairwise]
        compared_ids.update(bm.id for bm in remaining)

        # --- Pass 2: SimHash
        sims: Dict[int, int] = {}
        for bm in remaining:
            tokens = WORD_RE.findall(_read_text(bm).lower())
            sims[bm.id] = _simhash64(tokens)

        defaultdict(list)
        used: set[int] = set()
        ids = list(sims.keys())
        for i, a in enumerate(ids):
            if a in used:
                continue
            group = [a]
            for b in ids[i + 1:]:
                if b in used:
                    continue
                if _hamming(sims[a], sims[b]) <= self.SIMHASH_THRESHOLD:
                    group.append(b)
                    used.add(b)
            if len(group) > 1:
                used.add(a)
                seen_ids.update(group)
                report.groups.append(DuplicateGroup(
                    method="simhash", canonical_id=group[0], bookmark_ids=group,
                    confidence=0.85,
                ))
                report.method_counts["simhash"] += 1

        # --- Pass 3: Embedding cosine
        if self.embedder is not None and self.embedder.available:
            pass3_candidates = [bm for bm in bookmarks if bm.id not in seen_ids]
            pairwise_candidate_ids.update(bm.id for bm in pass3_candidates)
            still_remaining = pass3_candidates[:self.max_pairwise]
            compared_ids.update(bm.id for bm in still_remaining)
            texts = [(_read_text(bm)[:1500]) for bm in still_remaining]
            if texts:
                vectors = self.embedder.embed(texts)
                for i in range(len(still_remaining)):
                    if not vectors[i] or still_remaining[i].id in seen_ids:
                        continue
                    matches = [still_remaining[i].id]
                    for j in range(i + 1, len(still_remaining)):
                        if not vectors[j] or still_remaining[j].id in seen_ids:
                            continue
                        if _cosine(vectors[i], vectors[j]) >= self.EMBEDDING_THRESHOLD:
                            matches.append(still_remaining[j].id)
                            seen_ids.add(still_remaining[j].id)
                    if len(matches) > 1:
                        seen_ids.update(matches)
                        report.groups.append(DuplicateGroup(
                            method="embedding", canonical_id=matches[0],
                            bookmark_ids=matches, confidence=0.75,
                        ))
                        report.method_counts["embedding"] += 1

        report.pairwise_examined = len(compared_ids)
        report.pairwise_skipped = len(pairwise_candidate_ids - compared_ids)
        return report
