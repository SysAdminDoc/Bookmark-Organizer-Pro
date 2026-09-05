"""Vector store for semantic search over bookmark content.

Backend: LanceDB (preferred) — pure-Python, embedded, no server.
Fallback: pure-Python in-memory store with cosine similarity persisted as JSON.

Stores chunked text per bookmark with char-offset anchors so AI summaries can
cite back to source spans.
"""

from __future__ import annotations

import importlib
import hashlib
import json
import math
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from bookmark_organizer_pro.constants import EMBEDDINGS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.embeddings import (
    CHUNKER_VERSION,
    DEFAULT_CHUNK_CHARS,
    DEFAULT_CHUNK_OVERLAP,
    EmbeddingService,
)
from bookmark_organizer_pro.services.job_ledger import JobLedger
from bookmark_organizer_pro.utils.runtime import atomic_json_write


VECTOR_INDEX_SCHEMA_VERSION = 2
VECTOR_ROW_SCHEMA_VERSION = 2
VECTOR_INDEX_DOCUMENT_SCHEMA = "bookmark-organizer-pro/vector-index"
VECTOR_CONTRACT_SCHEMA_VERSION = 1


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _lance_table_names(database) -> list:
    """List a LanceDB connection's tables across both API generations.

    `table_names()` is deprecated in favour of `list_tables()`. Preferring the
    current name keeps the suite free of the deprecation warning it emitted on
    every connection, and the older name stays as an explicit fallback for the
    lower end of the supported range rather than an accident.
    """
    for attribute in ("list_tables", "table_names"):
        lister = getattr(database, attribute, None)
        if lister is None:
            continue
        try:
            return list(lister())
        except Exception as exc:
            log.debug(f"LanceDB {attribute}() failed: {exc}")
    return []


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
    """Versioned vector generations keyed by bookmark ID and chunk ID.

    A generation is queryable only when its manifest matches the active
    embedder and chunker contract. This deliberately bypasses pre-v2 indexes:
    their vectors cannot be proven compatible with the current runtime.
    """

    def __init__(
        self,
        embedder: EmbeddingService,
        store_dir: Path = EMBEDDINGS_DIR,
        job_ledger: JobLedger | None = None,
        source_digest_resolver: Optional[Callable[[int], Optional[str]]] = None,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        fts_language: str = "English",
        fts_remove_stop_words: bool = True,
        fts_ascii_folding: bool = True,
    ):
        self.embedder = embedder
        # Full-text index tuning. Stop-word removal keeps "the" and "and" from
        # diluting rankings; ASCII folding lets "cafe" find "café".
        self.fts_language = str(fts_language or "English")
        self.fts_remove_stop_words = bool(fts_remove_stop_words)
        self.fts_ascii_folding = bool(fts_ascii_folding)
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._backend = "memory"
        self._lance_db = None
        self._lance_table = None
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._manifest: Optional[Dict[str, Any]] = None
        self._legacy_detected = False
        self._diagnostics: List[str] = []
        self._memory_path = self.store_dir / "vectors.json"
        self._manifest_path = self.store_dir / "vector-index-manifest.json"
        self._source_digest_resolver = source_digest_resolver
        self._chunk_chars = int(chunk_chars)
        self._chunk_overlap = int(chunk_overlap)
        if self._chunk_chars <= 0:
            raise ValueError("chunk_chars must be greater than zero")
        if self._chunk_overlap < 0 or self._chunk_overlap >= self._chunk_chars:
            raise ValueError("chunk_overlap must satisfy 0 <= overlap < chunk_chars")
        self.job_ledger = job_ledger or JobLedger()
        self._init_backend()

    # ------------------------------------------------------------------
    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _digest_json(value: Any) -> str:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8", errors="replace")
        return hashlib.sha256(encoded).hexdigest()

    def _embedder_identity(self, dimension: Optional[int] = None) -> Dict[str, Any]:
        identity = getattr(self.embedder, "identity", None)
        if callable(identity):
            identity = identity()
        if not isinstance(identity, dict):
            backend = str(getattr(self.embedder, "backend", "unknown") or "unknown")
            model = str(
                getattr(self.embedder, "resolved_model_name", "")
                or getattr(self.embedder, "model_name", "")
                or backend
            )
            identity = {
                "schema_version": 1,
                "id": f"{backend}:{model}",
                "backend": backend,
                "model": model,
                "revision": str(getattr(self.embedder, "revision", "unknown")),
                "dimension": int(getattr(self.embedder, "dim", 0) or 0),
            }
        normalized = {
            "schema_version": int(identity.get("schema_version", 1)),
            "id": str(identity.get("id") or "unknown:unknown"),
            "backend": str(identity.get("backend") or "unknown"),
            "model": str(identity.get("model") or "unknown"),
            "revision": str(identity.get("revision") or "unknown"),
            "dimension": int(identity.get("dimension") or 0),
        }
        if dimension is not None:
            normalized["dimension"] = int(dimension)
        return normalized

    def _runtime_contract(self, dimension: Optional[int] = None) -> Dict[str, Any]:
        return {
            "schema_version": VECTOR_CONTRACT_SCHEMA_VERSION,
            "embedder": self._embedder_identity(dimension),
            "chunker": {
                "version": CHUNKER_VERSION,
                "chunk_chars": self._chunk_chars,
                "overlap": self._chunk_overlap,
            },
            # Vector generations are independent of answer-provider settings.
            "ai_config_digest": "not-applicable",
        }

    def _load_manifest_file(self) -> Optional[Dict[str, Any]]:
        if not self._manifest_path.exists():
            return None
        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            self._diagnostics = ["manifest_unreadable"]
            return None
        return payload if isinstance(payload, dict) else None

    def _init_backend(self):
        lancedb = _try_import("lancedb")
        if lancedb is not None:
            try:
                self._lance_db = lancedb.connect(str(self.store_dir / "lancedb"))
                self._backend = "lancedb"
                self._manifest = self._load_manifest_file()
                if self._manifest is None:
                    self._legacy_detected = "bookmarks" in _lance_table_names(self._lance_db)
                log.info("Vector store: LanceDB")
                return
            except Exception as exc:
                log.debug(f"LanceDB init failed: {exc}")
        self._backend = "memory"
        if self._memory_path.exists():
            try:
                payload = json.loads(self._memory_path.read_text(encoding="utf-8"))
                if (
                    isinstance(payload, dict)
                    and payload.get("schema") == VECTOR_INDEX_DOCUMENT_SCHEMA
                    and payload.get("schema_version") == VECTOR_INDEX_SCHEMA_VERSION
                    and isinstance(payload.get("manifest"), dict)
                    and isinstance(payload.get("rows"), dict)
                ):
                    self._manifest = payload["manifest"]
                    self._memory = payload["rows"]
                elif isinstance(payload, dict):
                    self._legacy_detected = bool(payload)
            except (OSError, json.JSONDecodeError, TypeError):
                self._diagnostics = ["index_unreadable"]
        log.info("Vector store: in-memory JSON fallback")

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def diagnostics(self) -> Tuple[str, ...]:
        """Content-free compatibility/freshness codes from the latest check."""
        return tuple(self._diagnostics)

    def _manifest_validation_codes(self) -> List[str]:
        manifest = self._manifest
        if manifest is None:
            return ["legacy_index"] if self._legacy_detected else ["index_missing"]
        if (
            manifest.get("schema") != VECTOR_INDEX_DOCUMENT_SCHEMA
            or manifest.get("schema_version") != VECTOR_INDEX_SCHEMA_VERSION
        ):
            return ["index_schema_mismatch"]
        if not manifest.get("generation_id"):
            return ["generation_missing"]
        persisted = manifest.get("contract")
        if not isinstance(persisted, dict):
            return ["contract_missing"]
        current = self._runtime_contract()
        if persisted.get("schema_version") != current["schema_version"]:
            return ["contract_schema_mismatch"]
        old_embedder = persisted.get("embedder")
        if not isinstance(old_embedder, dict):
            return ["embedder_contract_missing"]
        for field in ("schema_version", "id", "backend", "model", "revision", "dimension"):
            if old_embedder.get(field) != current["embedder"].get(field):
                return [f"embedder_{field}_mismatch"]
        if persisted.get("chunker") != current["chunker"]:
            return ["chunker_contract_mismatch"]
        if persisted.get("ai_config_digest") != "not-applicable":
            return ["vector_ai_contract_mismatch"]
        return []

    def _set_validation_diagnostics(self) -> bool:
        self._diagnostics = self._manifest_validation_codes()
        return not self._diagnostics

    def _new_manifest(
        self,
        generation_id: str,
        contract: Dict[str, Any],
        source_digest: str,
        bookmark_id: int,
        row_count: int,
        table_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = self._utc_now()
        sources = {str(int(bookmark_id)): source_digest}
        manifest = {
            "schema": VECTOR_INDEX_DOCUMENT_SCHEMA,
            "schema_version": VECTOR_INDEX_SCHEMA_VERSION,
            "generation_id": generation_id,
            "created_at": now,
            "updated_at": now,
            "contract": contract,
            "sources": sources,
            "source_set_digest": self._digest_json(sources),
            "bookmark_count": 1,
            "chunk_count": int(row_count),
        }
        if table_name:
            manifest["table_name"] = table_name
        return manifest

    @staticmethod
    def _chunk_contract(chunks: List[dict]) -> Tuple[int, int, int]:
        versions = {int(chunk.get("chunker_version", CHUNKER_VERSION)) for chunk in chunks}
        sizes = {int(chunk.get("chunk_chars", DEFAULT_CHUNK_CHARS)) for chunk in chunks}
        overlaps = {int(chunk.get("overlap", DEFAULT_CHUNK_OVERLAP)) for chunk in chunks}
        if len(versions) != 1 or len(sizes) != 1 or len(overlaps) != 1:
            raise ValueError("all chunks must share one chunker contract")
        return versions.pop(), sizes.pop(), overlaps.pop()

    @staticmethod
    def _source_digest(chunks: List[dict]) -> str:
        digests = {str(chunk.get("source_digest") or "") for chunk in chunks}
        digests.discard("")
        if len(digests) > 1:
            raise ValueError("all chunks must originate from one source digest")
        if digests:
            return digests.pop()
        ordered = sorted(
            chunks,
            key=lambda chunk: (
                int(chunk.get("char_start", 0)),
                str(chunk.get("id", "")),
            ),
        )
        reconstructed = "".join(str(chunk.get("text") or "") for chunk in ordered)
        return EmbeddingService.normalized_source_digest(reconstructed)

    def _build_rows(
        self,
        bookmark_id: int,
        chunks: List[dict],
        vectors: List[List[float]],
        generation_id: str,
        contract: Dict[str, Any],
        source_digest: str,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        embedder = contract["embedder"]
        chunker = contract["chunker"]
        for chunk, vector in zip(chunks, vectors):
            if not vector:
                continue
            rows.append({
                "index_schema_version": VECTOR_INDEX_SCHEMA_VERSION,
                "row_schema_version": VECTOR_ROW_SCHEMA_VERSION,
                "generation_id": generation_id,
                "bookmark_id": int(bookmark_id),
                "chunk_id": str(chunk["id"]),
                "char_start": int(chunk.get("char_start", 0)),
                "char_end": int(chunk.get("char_end", 0)),
                "text": str(chunk.get("text") or ""),
                "vector": [float(value) for value in vector],
                "embedder_id": embedder["id"],
                "embedder_revision": embedder["revision"],
                "vector_dimension": embedder["dimension"],
                "chunker_version": chunker["version"],
                "chunk_chars": chunker["chunk_chars"],
                "chunk_overlap": chunker["overlap"],
                "source_digest": source_digest,
                "added_at": self._utc_now(),
            })
        return rows

    def _persist_manifest(self) -> None:
        if self._manifest is not None:
            atomic_json_write(self._manifest_path, self._manifest)

    def _persist_memory(self) -> None:
        try:
            atomic_json_write(
                self._memory_path,
                {
                    "schema": VECTOR_INDEX_DOCUMENT_SCHEMA,
                    "schema_version": VECTOR_INDEX_SCHEMA_VERSION,
                    "manifest": self._manifest,
                    "rows": self._memory,
                },
            )
        except OSError as exc:
            log.warning(f"Could not persist vector store: {exc}")

    def _create_lance_table(self, table_name: str, rows: List[Dict[str, Any]]):
        if self._lance_db is None:
            raise RuntimeError("LanceDB is not initialized")
        try:
            return self._lance_db.create_table(table_name, data=rows)
        except TypeError:
            return self._lance_db.create_table(table_name, rows)

    # ------------------------------------------------------------------
    def upsert_bookmark(self, bookmark_id: int, chunks: List[dict]) -> int:
        """Replace a bookmark and atomically publish incompatible generations."""
        job = self.job_ledger.start(
            "embedding",
            bookmark_id=bookmark_id,
            backend=f"{self._backend}/{getattr(self.embedder, 'backend', 'unavailable')}",
        )
        if not chunks or not getattr(self.embedder, "available", False):
            job.fail(
                "No chunks or embedding backend available",
                retryable=not getattr(self.embedder, "available", False),
            )
            return 0
        try:
            version, chunk_chars, overlap = self._chunk_contract(chunks)
            if (
                version != CHUNKER_VERSION
                or chunk_chars != self._chunk_chars
                or overlap != self._chunk_overlap
            ):
                raise ValueError("chunks do not match the active chunker contract")
            source_digest = self._source_digest(chunks)
            texts = [str(chunk.get("text") or "") for chunk in chunks]
            vectors = self.embedder.embed(texts)
            dimensions = {len(vector) for vector in vectors if vector}
            if len(dimensions) != 1:
                raise ValueError("embedding backend returned inconsistent dimensions")
            if not dimensions:
                job.fail("Embedding backend returned no vectors", retryable=True)
                return 0
            dimension = dimensions.pop()
            contract = self._runtime_contract(dimension)
            if contract["embedder"]["dimension"] != dimension:
                raise ValueError("embedding dimension does not match embedder identity")
        except Exception as exc:
            job.fail(exc, retryable=True)
            if isinstance(exc, ValueError):
                log.warning(f"Vector upsert rejected incompatible input: {exc}")
                return 0
            raise

        with self._lock:
            compatible = (
                self._manifest is not None
                and self._manifest.get("contract") == contract
                and not self._manifest_validation_codes()
            )
            generation_id = (
                str(self._manifest["generation_id"])
                if compatible
                else uuid.uuid4().hex
            )
            rows = self._build_rows(
                bookmark_id,
                chunks,
                vectors,
                generation_id,
                contract,
                source_digest,
            )
            if not rows:
                job.fail("Embedding backend returned no vectors", retryable=True)
                return 0

            if not compatible:
                if self._backend == "lancedb":
                    table_name = f"bookmarks_{generation_id[:16]}"
                    table = self._create_lance_table(table_name, rows)
                    next_manifest = self._new_manifest(
                        generation_id,
                        contract,
                        source_digest,
                        bookmark_id,
                        len(rows),
                        table_name,
                    )
                    # Publish only after the complete replacement table exists.
                    atomic_json_write(self._manifest_path, next_manifest)
                    self._manifest = next_manifest
                    self._lance_table = table
                else:
                    next_memory = {
                        f"{row['bookmark_id']}:{row['chunk_id']}": row
                        for row in rows
                    }
                    self._memory = next_memory
                    self._manifest = self._new_manifest(
                        generation_id,
                        contract,
                        source_digest,
                        bookmark_id,
                        len(rows),
                    )
                    self._persist_memory()
                self._legacy_detected = False
            else:
                self._delete_bookmark_rows(bookmark_id)
                if self._backend == "lancedb":
                    table = self._table()
                    if table is None:
                        job.fail("Active vector generation is unavailable", retryable=True)
                        return 0
                    table.add(rows)
                else:
                    for row in rows:
                        self._memory[f"{row['bookmark_id']}:{row['chunk_id']}"] = row
                sources = self._manifest.setdefault("sources", {})
                sources[str(int(bookmark_id))] = source_digest
                self._refresh_manifest_counts()
                if self._backend == "memory":
                    self._persist_memory()
                else:
                    self._persist_manifest()
            self._diagnostics = []

        job.succeed(
            bytes_processed=sum(
                len(text.encode("utf-8", errors="replace")) for text in texts
            )
        )
        return len(rows)

    def _refresh_manifest_counts(self) -> None:
        if self._manifest is None:
            return
        sources = self._manifest.setdefault("sources", {})
        self._manifest["source_set_digest"] = self._digest_json(sources)
        self._manifest["bookmark_count"] = len(sources)
        if self._backend == "lancedb":
            table = self._table()
            self._manifest["chunk_count"] = (
                int(table.count_rows()) if table is not None else 0
            )
        else:
            self._manifest["chunk_count"] = len(self._memory)
        self._manifest["updated_at"] = self._utc_now()

    def delete_bookmark(self, bookmark_id: int) -> int:
        with self._lock:
            if self._manifest is None:
                return 0
            removed = self._delete_bookmark_rows(bookmark_id)
            self._manifest.setdefault("sources", {}).pop(str(int(bookmark_id)), None)
            self._refresh_manifest_counts()
            if self._backend == "memory":
                self._persist_memory()
            else:
                self._persist_manifest()
            return removed

    def _delete_bookmark_rows(self, bookmark_id: int) -> int:
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
        keys = [key for key in self._memory if key.startswith(prefix)]
        for key in keys:
            self._memory.pop(key, None)
        return len(keys)

    def _row_validation_code(
        self,
        row: Dict[str, Any],
        source_cache: Optional[Dict[int, Optional[str]]] = None,
    ) -> Optional[str]:
        manifest = self._manifest or {}
        contract = manifest.get("contract") or {}
        embedder = contract.get("embedder") or {}
        chunker = contract.get("chunker") or {}
        required = {
            "index_schema_version": VECTOR_INDEX_SCHEMA_VERSION,
            "row_schema_version": VECTOR_ROW_SCHEMA_VERSION,
            "generation_id": manifest.get("generation_id"),
            "embedder_id": embedder.get("id"),
            "embedder_revision": embedder.get("revision"),
            "vector_dimension": embedder.get("dimension"),
            "chunker_version": chunker.get("version"),
            "chunk_chars": chunker.get("chunk_chars"),
            "chunk_overlap": chunker.get("overlap"),
        }
        for field, expected in required.items():
            if row.get(field) != expected:
                return f"row_{field}_mismatch"
        vector = row.get("vector")
        if not isinstance(vector, (list, tuple)) or len(vector) != embedder.get("dimension"):
            return "row_vector_dimension_mismatch"
        source_digest = str(row.get("source_digest") or "")
        bookmark_id = int(row.get("bookmark_id", 0))
        expected_digest = (manifest.get("sources") or {}).get(str(bookmark_id))
        if not source_digest or source_digest != expected_digest:
            return "row_source_digest_mismatch"
        if self._source_digest_resolver is not None:
            if source_cache is not None and bookmark_id in source_cache:
                current_digest = source_cache[bookmark_id]
            else:
                try:
                    current_digest = self._source_digest_resolver(bookmark_id)
                except Exception:
                    return "source_validation_failed"
                if source_cache is not None:
                    source_cache[bookmark_id] = current_digest
            if not current_digest:
                return "source_missing"
            if str(current_digest) != source_digest:
                return "source_content_changed"
        return None

    @staticmethod
    def _public_result(row: Dict[str, Any], score: float) -> Dict[str, Any]:
        return {
            "bookmark_id": int(row.get("bookmark_id", 0)),
            "chunk_id": str(row.get("chunk_id", "")),
            "text": str(row.get("text", "")),
            "char_start": int(row.get("char_start", 0)),
            "char_end": int(row.get("char_end", 0)),
            "score": float(score),
            "source_digest": str(row.get("source_digest", "")),
            "generation_id": str(row.get("generation_id", "")),
        }

    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        k: int = 10,
        restrict_ids: Optional[Iterable[int]] = None,
    ) -> List[Dict[str, Any]]:
        if not query or not getattr(self.embedder, "available", False):
            return []
        restrict = (
            {int(bookmark_id) for bookmark_id in restrict_ids}
            if restrict_ids is not None
            else None
        )
        with self._lock:
            if not self._set_validation_diagnostics():
                return []
            qvec = self.embedder.embed_one(query)
            expected_dim = (
                self._manifest.get("contract", {})
                .get("embedder", {})
                .get("dimension", 0)
            )
            if not qvec or len(qvec) != expected_dim:
                self._diagnostics = ["query_vector_dimension_mismatch"]
                return []

            if self._backend == "lancedb":
                table = self._table()
                if table is None:
                    self._diagnostics = ["generation_table_missing"]
                    return []
                try:
                    candidates = (
                        table.search(qvec)
                        .limit(max(k * 4, 20))
                        .to_list()
                    )
                except Exception as exc:
                    log.debug(f"LanceDB search failed: {exc}")
                    self._diagnostics = ["vector_query_failed"]
                    return []
                scored = [
                    (row, 1.0 / (1.0 + float(row.get("_distance", 0.0))))
                    for row in candidates
                ]
            else:
                scored = [
                    (row, _cosine(qvec, list(row.get("vector") or [])))
                    for row in self._memory.values()
                ]

            results: List[Dict[str, Any]] = []
            stale_codes: set[str] = set()
            source_cache: Dict[int, Optional[str]] = {}
            for row, score in scored:
                bookmark_id = int(row.get("bookmark_id", 0))
                if restrict is not None and bookmark_id not in restrict:
                    continue
                row_code = self._row_validation_code(row, source_cache)
                if row_code:
                    stale_codes.add(row_code)
                    continue
                results.append(self._public_result(row, score))
            results.sort(key=lambda result: result["score"], reverse=True)
            self._diagnostics = sorted(stale_codes)
            return results[:k]

    # ------------------------------------------------------------------
    def _create_fts_index(self, table) -> None:
        """Build the FTS index, applying stop-word and tokenizer settings.

        LanceDB gained these options in 0.35; older builds reject the keywords,
        so an unsupported option falls back to a plain index rather than
        leaving the library with no full-text search at all.
        """
        options: Dict[str, Any] = {"replace": True}
        language = str(getattr(self, "fts_language", "") or "English").strip() or "English"
        if getattr(self, "fts_remove_stop_words", True):
            options["remove_stop_words"] = True
            options["language"] = language
        if getattr(self, "fts_ascii_folding", True):
            options["ascii_folding"] = True
        try:
            table.create_fts_index("text", **options)
            return
        except (TypeError, ValueError, AttributeError) as exc:
            log.debug(f"LanceDB FTS options unsupported, using defaults: {exc}")
        table.create_fts_index("text", replace=True)

    def fts_search(self, query: str, k: int = 50, offset: int = 0) -> List[int]:
        """Full-text search via the active, compatible LanceDB generation.

        ``offset`` pages through results without re-ranking the whole candidate
        set on the caller's side.
        """
        if not query or self._backend != "lancedb":
            return []
        with self._lock:
            if not self._set_validation_diagnostics():
                return []
            table = self._table()
            if table is None:
                self._diagnostics = ["generation_table_missing"]
                return []
            try:
                if not getattr(self, "_fts_indexed", False):
                    self._create_fts_index(table)
                    self._fts_indexed = True
                search = table.search(query, query_type="fts").limit(k)
                offset = max(0, int(offset or 0))
                if offset:
                    # Older LanceDB builds have no offset(); fall back to
                    # over-fetching and slicing rather than failing the query.
                    try:
                        search = search.offset(offset)
                        offset = 0
                    except (AttributeError, TypeError):
                        search = table.search(query, query_type="fts").limit(k + offset)
                rows = search.to_list()
                if offset:
                    rows = rows[offset:]
                ordered: List[int] = []
                seen: set[int] = set()
                stale_codes: set[str] = set()
                source_cache: Dict[int, Optional[str]] = {}
                for row in rows:
                    code = self._row_validation_code(row, source_cache)
                    if code:
                        stale_codes.add(code)
                        continue
                    bookmark_id = int(row.get("bookmark_id", 0))
                    if bookmark_id not in seen:
                        seen.add(bookmark_id)
                        ordered.append(bookmark_id)
                self._diagnostics = sorted(stale_codes)
                return ordered
            except Exception as exc:
                log.debug(f"LanceDB FTS search failed: {exc}")
                self._diagnostics = ["fts_query_failed"]
                return []

    # ------------------------------------------------------------------
    def index_status(self) -> Dict[str, Any]:
        """Return content-free index health suitable for CLI/UI diagnostics."""
        with self._lock:
            codes = self._manifest_validation_codes()
            if not codes and self._diagnostics:
                codes = list(self._diagnostics)
            manifest = self._manifest or {}
            contract = manifest.get("contract") or {}
            embedder = contract.get("embedder") or {}
            chunker = contract.get("chunker") or {}
            if codes:
                state = "missing" if codes == ["index_missing"] else "stale"
            elif int(manifest.get("chunk_count", 0)) == 0:
                state = "empty"
            else:
                state = "ready"
            return {
                "status": state,
                "backend": self._backend,
                "generation_id": str(manifest.get("generation_id") or ""),
                "bookmark_count": int(manifest.get("bookmark_count", 0)),
                "chunk_count": int(manifest.get("chunk_count", 0)),
                "embedder_id": str(embedder.get("id") or ""),
                "vector_dimension": int(embedder.get("dimension", 0)),
                "chunker_version": int(chunker.get("version", 0)),
                "rebuild_required": state == "stale",
                "diagnostics": sorted(set(codes)),
            }

    def cache_identity(self) -> Dict[str, Any]:
        """Return the non-content identity used to invalidate answer caches."""
        status = self.index_status()
        manifest = self._manifest or {}
        return {
            "valid": status["status"] == "ready",
            "generation_id": status["generation_id"],
            "contract_digest": self._digest_json(manifest.get("contract") or {}),
            "source_set_digest": str(manifest.get("source_set_digest") or ""),
        }

    def stats(self) -> Dict[str, Any]:
        status = self.index_status()
        return {
            "chunks": status["chunk_count"],
            "backend": self._backend,
            "status": status["status"],
            "rebuild_required": status["rebuild_required"],
        }

    def _table(self):
        if self._lance_table is not None:
            return self._lance_table
        if self._lance_db is None or self._manifest is None:
            return None
        table_name = self._manifest.get("table_name")
        if not table_name:
            return None
        try:
            self._lance_table = self._lance_db.open_table(str(table_name))
        except Exception:
            return None
        return self._lance_table


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
