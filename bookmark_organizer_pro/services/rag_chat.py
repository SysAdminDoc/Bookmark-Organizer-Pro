"""Conversational RAG over bookmark collections.

Single-turn first ("ask anything about this collection"); multi-turn message
history is supported but capped to keep prompts bounded.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bookmark_organizer_pro.ai import AIConfigManager, create_ai_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.embeddings import EmbeddingService
from bookmark_organizer_pro.services.vector_store import VectorStore


SYSTEM_PROMPT = (
    "You are an assistant that answers questions about a personal bookmark "
    "library. You receive numbered context snippets pulled from saved pages. "
    "Answer concisely (3-6 sentences). Cite supporting snippets inline using "
    "[#cN]. If the snippets do not answer the question, say so plainly."
)


@dataclass
class ChatMessage:
    role: str   # "user" | "assistant"
    content: str


@dataclass
class ChatTurn:
    answer: str
    sources: List[dict] = field(default_factory=list)
    used_chunks: int = 0


class CollectionChat:
    """Stateful chat over a subset of bookmarks with answer caching."""

    def __init__(self, ai_config: AIConfigManager, vector_store: VectorStore,
                 max_history: int = 6, retrieval_k: int = 6,
                 cache_size: int = 128):
        self.ai_config = ai_config
        self.vector_store = vector_store
        self.max_history = max_history
        self.retrieval_k = retrieval_k
        self.history: List[ChatMessage] = []
        self._cache: OrderedDict[str, ChatTurn] = OrderedDict()
        self._cache_size = cache_size

    def _cache_key(self, question: str, restrict_ids: Optional[Iterable[int]]) -> str:
        scope = ",".join(str(i) for i in sorted(restrict_ids)) if restrict_ids else ""
        raw = f"{question.strip().lower()}|{scope}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def reset(self):
        self.history = []

    def clear_cache(self):
        self._cache.clear()

    @property
    def cache_stats(self) -> Dict[str, int]:
        return {"size": len(self._cache), "max": self._cache_size}

    def ask(self, question: str,
            restrict_ids: Optional[Iterable[int]] = None,
            use_cache: bool = True) -> ChatTurn:
        if not question.strip():
            return ChatTurn(answer="")

        if use_cache and not self.history:
            key = self._cache_key(question, restrict_ids)
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]

        retrieved = self.vector_store.search(
            question, k=self.retrieval_k, restrict_ids=restrict_ids
        )
        if not retrieved and not self.vector_store.embedder.available:
            return ChatTurn(
                answer="Semantic search is unavailable (install fastembed or model2vec).",
                sources=[],
            )

        context_lines = []
        for i, hit in enumerate(retrieved):
            context_lines.append(
                f"[#c{i}] (bookmark {hit['bookmark_id']}) {hit['text'][:600]}"
            )
        context = "\n".join(context_lines) if context_lines else "(no matching context)"

        history_lines = []
        for msg in self.history[-self.max_history:]:
            history_lines.append(f"{msg.role.upper()}: {msg.content}")
        history_block = "\n".join(history_lines)

        prompt_parts = []
        if history_block:
            prompt_parts.append("CONVERSATION SO FAR:")
            prompt_parts.append(history_block)
            prompt_parts.append("")
        prompt_parts.append("CONTEXT SNIPPETS:")
        prompt_parts.append(context)
        prompt_parts.append("")
        prompt_parts.append(f"USER QUESTION: {question}")

        try:
            client = create_ai_client(self.ai_config)
            answer = client.complete(
                system=SYSTEM_PROMPT,
                prompt="\n".join(prompt_parts),
                max_tokens=500,
                temperature=0.2,
            )
        except Exception as exc:
            log.warning(f"RAG chat failed: {exc}")
            return ChatTurn(answer=f"AI request failed: {exc}", sources=retrieved)

        import re as _re
        valid_ids = {f"c{i}" for i in range(len(retrieved))}
        answer = _re.sub(
            r'\[#(c\d+)\]',
            lambda m: m.group(0) if m.group(1) in valid_ids else '',
            answer,
        )

        self.history.append(ChatMessage(role="user", content=question))
        self.history.append(ChatMessage(role="assistant", content=answer))

        turn = ChatTurn(answer=answer, sources=retrieved, used_chunks=len(retrieved))

        if use_cache and not self.history[:-2]:
            key = self._cache_key(question, restrict_ids)
            self._cache[key] = turn
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

        return turn
