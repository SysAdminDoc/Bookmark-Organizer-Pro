"""Local embedding service.

Backend selection (in order of preference):
    1. fastembed        — ONNX runtime, small footprint (BAAI/bge-small-en-v1.5)
    2. model2vec        — distilled static embeddings (8-30MB, 500x CPU speedup)
    3. sentence_transformers — full PyTorch (only if user explicitly opts in)

All backends are optional; if none is installed, the service degrades to
returning empty vectors and the caller falls back to keyword search.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import threading
from pathlib import Path
from typing import List, Optional, Sequence

from bookmark_organizer_pro.constants import EMBEDDINGS_DIR
from bookmark_organizer_pro.logging_config import log


DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"   # 384 dims, fastembed default
MODEL2VEC_DEFAULT = "minishlab/potion-base-8M"
ST_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


class EmbeddingService:
    """Single entry point for generating text embeddings.

    Backend is chosen lazily on first call and cached.
    """

    def __init__(self, model_name: Optional[str] = None,
                 cache_dir: Path = EMBEDDINGS_DIR):
        self.model_name = model_name or DEFAULT_MODEL
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._backend = None
        self._embedder = None
        self._dim: Optional[int] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    @property
    def backend(self) -> str:
        self._ensure()
        return self._backend or "none"

    @property
    def dim(self) -> int:
        self._ensure()
        return self._dim or 0

    @property
    def available(self) -> bool:
        self._ensure()
        return self._backend not in (None, "none")

    # ------------------------------------------------------------------
    def _ensure(self):
        if self._backend is not None:
            return
        with self._lock:
            if self._backend is not None:
                return
            for loader in (self._load_fastembed, self._load_model2vec,
                           self._load_sentence_transformers):
                try:
                    if loader():
                        return
                except Exception as exc:
                    log.debug(f"embedding loader failed: {exc}")
            self._backend = "none"
            self._dim = 0
            log.info("No embedding backend available — semantic search disabled")

    def _load_fastembed(self) -> bool:
        fe = _try_import("fastembed")
        if fe is None:
            return False
        TextEmbedding = getattr(fe, "TextEmbedding", None)
        if TextEmbedding is None:
            return False
        self._embedder = TextEmbedding(model_name=self.model_name)
        # Probe
        sample = list(self._embedder.embed(["probe"]))[0]
        self._dim = len(sample)
        self._backend = "fastembed"
        log.info(f"Embeddings: fastembed ({self.model_name}, dim={self._dim})")
        return True

    def _load_model2vec(self) -> bool:
        m2v = _try_import("model2vec")
        if m2v is None:
            return False
        StaticModel = getattr(m2v, "StaticModel", None)
        if StaticModel is None:
            return False
        self._embedder = StaticModel.from_pretrained(MODEL2VEC_DEFAULT)
        sample = self._embedder.encode(["probe"])
        self._dim = int(sample.shape[1])
        self._backend = "model2vec"
        log.info(f"Embeddings: model2vec ({MODEL2VEC_DEFAULT}, dim={self._dim})")
        return True

    def _load_sentence_transformers(self) -> bool:
        st = _try_import("sentence_transformers")
        if st is None:
            return False
        SentenceTransformer = getattr(st, "SentenceTransformer", None)
        if SentenceTransformer is None:
            return False
        self._embedder = SentenceTransformer(ST_DEFAULT)
        self._dim = int(self._embedder.get_sentence_embedding_dimension())
        self._backend = "sentence_transformers"
        log.info(f"Embeddings: sentence_transformers ({ST_DEFAULT}, dim={self._dim})")
        return True

    # ------------------------------------------------------------------
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        self._ensure()
        if not self.available or not texts:
            return [[] for _ in texts]
        try:
            if self._backend == "fastembed":
                return [list(map(float, v)) for v in self._embedder.embed(list(texts))]
            if self._backend == "model2vec":
                arr = self._embedder.encode(list(texts))
                return [list(map(float, row)) for row in arr]
            if self._backend == "sentence_transformers":
                arr = self._embedder.encode(list(texts), show_progress_bar=False)
                return [list(map(float, row)) for row in arr]
        except Exception as exc:
            log.warning(f"Embedding failed: {exc}")
        return [[] for _ in texts]

    def embed_one(self, text: str) -> List[float]:
        out = self.embed([text])
        return out[0] if out else []

    # ------------------------------------------------------------------
    @staticmethod
    def chunk_text(text: str, chunk_chars: int = 1500,
                   overlap: int = 200) -> List[dict]:
        """Sliding-window chunker that records char offsets for citation."""
        text = text or ""
        if not text:
            return []
        chunks = []
        start = 0
        n = len(text)
        idx = 0
        while start < n:
            end = min(n, start + chunk_chars)
            # Try to break at a sentence boundary
            if end < n:
                window = text[end - 200:end + 200]
                local = window.rfind(". ")
                if local != -1:
                    end = (end - 200) + local + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append({
                    "id": f"c{idx}",
                    "text": chunk,
                    "char_start": start,
                    "char_end": end,
                })
                idx += 1
            if end >= n:
                break
            start = max(end - overlap, end)
        return chunks

    @staticmethod
    def stable_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
