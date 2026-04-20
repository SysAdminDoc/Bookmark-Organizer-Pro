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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bookmark_organizer_pro.logging_config import log
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


class HybridDuplicateDetector:
    """Layered duplicate detection."""

    SIMHASH_THRESHOLD = 3       # bits Hamming distance
    EMBEDDING_THRESHOLD = 0.92  # cosine similarity

    def __init__(self, embedder: Optional[EmbeddingService] = None):
        self.embedder = embedder

    def detect(self, bookmarks: Sequence[Bookmark]) -> DuplicateReport:
        report = DuplicateReport(method_counts={"url": 0, "simhash": 0, "embedding": 0})
        seen_ids: set[int] = set()

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

        remaining = [bm for bm in bookmarks if bm.id not in seen_ids]

        # --- Pass 2: SimHash
        sims: Dict[int, int] = {}
        for bm in remaining:
            tokens = WORD_RE.findall(_read_text(bm).lower())
            sims[bm.id] = _simhash64(tokens)

        sim_groups: Dict[int, List[int]] = defaultdict(list)
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
            still_remaining = [bm for bm in bookmarks if bm.id not in seen_ids]
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

        return report
