"""Vector store for semantic search over bookmark content.

Backend: LanceDB (preferred) — pure-Python, embedded, no server.
Fallback: pure-Python in-memory store with cosine similarity persisted as JSON.

Stores chunked text per bookmark with char-offset anchors so AI summaries can
cite back to source spans.
"""

from __future__ import annotations

import importlib
import json
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from bookmark_organizer_pro.constants import EMBEDDINGS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.embeddings import EmbeddingService


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorStore:
    """Per-collection vector store keyed by bookmark_id + chunk_id."""

    def __init__(self, embedder: EmbeddingService,
                 store_dir: Path = EMBEDDINGS_DIR):
        self.embedder = embedder
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._backend = "memory"
        self._lance_db = None
        self._lance_table = None
        self._memory: Dict[str, Dict] = {}
        self._memory_path = self.store_dir / "vectors.json"
        self._init_backend()

    # ------------------------------------------------------------------
    def _init_backend(self):
        lancedb = _try_import("lancedb")
        if lancedb is not None:
            try:
                self._lance_db = lancedb.connect(str(self.store_dir / "lancedb"))
                self._backend = "lancedb"
                log.info("Vector store: LanceDB")
                return
            except Exception as exc:
                log.debug(f"LanceDB init failed: {exc}")
        self._backend = "memory"
        if self._memory_path.exists():
            try:
                self._memory = json.loads(self._memory_path.read_text(encoding="utf-8"))
            except Exception:
                self._memory = {}
        log.info("Vector store: in-memory JSON fallback")

    @property
    def backend(self) -> str:
        return self._backend

    # ------------------------------------------------------------------
    def upsert_bookmark(self, bookmark_id: int, chunks: List[dict]) -> int:
        """Replace any existing chunks for this bookmark with new ones."""
        if not chunks or not self.embedder.available:
            return 0
        texts = [c["text"] for c in chunks]
        vectors = self.embedder.embed(texts)
        rows = []
        for chunk, vec in zip(chunks, vectors):
            if not vec:
                continue
            rows.append({
                "bookmark_id": int(bookmark_id),
                "chunk_id": chunk["id"],
                "char_start": int(chunk.get("char_start", 0)),
                "char_end": int(chunk.get("char_end", 0)),
                "text": chunk["text"],
                "vector": vec,
                "added_at": datetime.now().isoformat(),
            })
        if not rows:
            return 0
        with self._lock:
            self._delete_bookmark(bookmark_id)
            if self._backend == "lancedb":
                table = self._table()
                if table is None:
                    table = self._lance_db.create_table("bookmarks", data=rows)
                    self._lance_table = table
                else:
                    table.add(rows)
            else:
                for row in rows:
                    key = f"{row['bookmark_id']}:{row['chunk_id']}"
                    self._memory[key] = row
                self._persist_memory()
        return len(rows)

    def delete_bookmark(self, bookmark_id: int) -> int:
        with self._lock:
            n = self._delete_bookmark(bookmark_id)
            if self._backend == "memory":
                self._persist_memory()
        return n

    def _delete_bookmark(self, bookmark_id: int) -> int:
        if self._backend == "lancedb":
            table = self._table()
            if table is None:
                return 0
            try:
                before = table.count_rows()
                table.delete(f"bookmark_id = {int(bookmark_id)}")
                return max(0, before - table.count_rows())
            except Exception:
                return 0
        prefix = f"{int(bookmark_id)}:"
        keys = [k for k in self._memory if k.startswith(prefix)]
        for k in keys:
            self._memory.pop(k, None)
        return len(keys)

    # ------------------------------------------------------------------
    def search(self, query: str, k: int = 10,
               restrict_ids: Optional[Iterable[int]] = None) -> List[Dict]:
        if not query or not self.embedder.available:
            return []
        qvec = self.embedder.embed_one(query)
        if not qvec:
            return []
        restrict = set(int(x) for x in restrict_ids) if restrict_ids else None
        with self._lock:
            if self._backend == "lancedb":
                table = self._table()
                if table is None:
                    return []
                try:
                    df = table.search(qvec).limit(max(k * 4, 20)).to_list()
                except Exception as exc:
                    log.debug(f"LanceDB search failed: {exc}")
                    df = []
                results = []
                for row in df:
                    bid = int(row.get("bookmark_id", 0))
                    if restrict is not None and bid not in restrict:
                        continue
                    distance = float(row.get("_distance", 0.0))
                    score = 1.0 / (1.0 + distance)
                    results.append({
                        "bookmark_id": bid,
                        "chunk_id": row.get("chunk_id", ""),
                        "text": row.get("text", ""),
                        "char_start": int(row.get("char_start", 0)),
                        "char_end": int(row.get("char_end", 0)),
                        "score": score,
                    })
                results.sort(key=lambda r: r["score"], reverse=True)
                return results[:k]
            # in-memory cosine
            scored = []
            for row in self._memory.values():
                bid = int(row["bookmark_id"])
                if restrict is not None and bid not in restrict:
                    continue
                score = _cosine(qvec, row["vector"])
                scored.append({
                    "bookmark_id": bid,
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "char_start": int(row["char_start"]),
                    "char_end": int(row["char_end"]),
                    "score": float(score),
                })
            scored.sort(key=lambda r: r["score"], reverse=True)
            return scored[:k]

    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, int]:
        with self._lock:
            if self._backend == "lancedb":
                table = self._table()
                count = table.count_rows() if table is not None else 0
            else:
                count = len(self._memory)
            return {"chunks": int(count), "backend": self._backend}

    def _table(self):
        if self._lance_table is not None:
            return self._lance_table
        if self._lance_db is None:
            return None
        try:
            self._lance_table = self._lance_db.open_table("bookmarks")
        except Exception:
            return None
        return self._lance_table

    def _persist_memory(self):
        try:
            self._memory_path.write_text(
                json.dumps(self._memory, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning(f"Could not persist vector store: {exc}")


def reciprocal_rank_fusion(rankings: List[List[int]], k: int = 60) -> List[Tuple[int, float]]:
    """Fuse multiple ranked lists of bookmark IDs using RRF.

    `rankings[i]` is a ranked list (best first) of bookmark IDs from one
    retrieval source. Returns merged list of (bookmark_id, score) sorted best
    first. k=60 is the canonical RRF constant.
    """
    scores: Dict[int, float] = {}
    for ranking in rankings:
        for rank, bid in enumerate(ranking):
            if bid is None:
                continue
            try:
                bid = int(bid)
            except (TypeError, ValueError):
                continue
            scores[bid] = scores.get(bid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
