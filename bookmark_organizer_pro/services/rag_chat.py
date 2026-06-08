"""Conversational RAG over bookmark collections.

Single-turn first ("ask anything about this collection"); multi-turn message
history is supported but capped to keep prompts bounded.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

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
    chunk_provenance: List[dict] = field(default_factory=list)


@dataclass
class ChatStreamEvent:
    type: str
    index: int = 0
    text: str = ""
    sources: List[dict] = field(default_factory=list)
    used_chunks: int = 0
    chunk_provenance: List[dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "type": self.type,
            "index": self.index,
        }
        if self.text:
            payload["text"] = self.text
        if self.sources:
            payload["sources"] = self.sources
        if self.used_chunks:
            payload["used_chunks"] = self.used_chunks
        if self.chunk_provenance:
            payload["chunk_provenance"] = self.chunk_provenance
        return payload


@dataclass
class ChatStreamResult:
    turn: ChatTurn
    events: List[ChatStreamEvent]
    provider_streaming: bool = False


def normalize_stream_chunk_chars(chunk_chars: int = 160) -> int:
    try:
        value = int(chunk_chars)
    except (TypeError, ValueError):
        value = 160
    return max(40, min(value, 1000))


def split_answer_chunks(text: str, chunk_chars: int = 160) -> List[str]:
    """Split a completed answer into stable client-consumable chunks."""
    if not text:
        return []
    size = normalize_stream_chunk_chars(chunk_chars)
    chunks: List[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(len(text), cursor + size)
        if end < len(text):
            boundary = max(
                text.rfind(" ", cursor + 1, end),
                text.rfind("\n", cursor + 1, end),
            )
            min_boundary = cursor + max(20, size // 3)
            if boundary >= min_boundary:
                end = boundary + 1
        chunk = text[cursor:end]
        if chunk:
            chunks.append(chunk)
        cursor = end
    return chunks


def build_chat_stream_events(turn: ChatTurn, chunk_chars: int = 160) -> List[ChatStreamEvent]:
    chunks = split_answer_chunks(turn.answer, chunk_chars)
    events = [
        ChatStreamEvent(type="chunk", index=index, text=chunk)
        for index, chunk in enumerate(chunks)
    ]
    events.append(
        ChatStreamEvent(
            type="complete",
            index=len(chunks),
            sources=turn.sources,
            used_chunks=turn.used_chunks,
            chunk_provenance=turn.chunk_provenance,
        )
    )
    return events


def emit_chunk_events(events: Sequence[ChatStreamEvent],
                      on_event: Optional[Callable[[ChatStreamEvent], None]]) -> None:
    if on_event is None:
        return
    for event in events:
        if event.type == "chunk":
            on_event(event)


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

    def _cache_lookup(self, question: str,
                      restrict_ids: Optional[Iterable[int]],
                      use_cache: bool) -> Tuple[bool, Optional[ChatTurn]]:
        is_first_turn = not self.history
        if use_cache and is_first_turn:
            key = self._cache_key(question, restrict_ids)
            if key in self._cache:
                self._cache.move_to_end(key)
                return is_first_turn, self._cache[key]
        return is_first_turn, None

    def _prepare_prompt(self, question: str,
                        restrict_ids: Optional[Iterable[int]]) -> Tuple[
                            Optional[Tuple[List[dict], List[dict], str]],
                            Optional[ChatTurn],
                        ]:
        retrieved = self.vector_store.search(
            question, k=self.retrieval_k, restrict_ids=restrict_ids
        )
        if not retrieved and not self.vector_store.embedder.available:
            return None, ChatTurn(
                answer="Semantic search is unavailable (install fastembed or model2vec).",
                sources=[],
            )

        context_lines = []
        provenance = []
        for i, hit in enumerate(retrieved):
            context_lines.append(
                f"[#c{i}] (bookmark {hit['bookmark_id']}) {hit['text'][:600]}"
            )
            provenance.append({
                "citation_id": f"c{i}",
                "bookmark_id": hit.get("bookmark_id"),
                "char_start": hit.get("char_start", 0),
                "char_end": hit.get("char_end", 0),
                "text_preview": hit.get("text", "")[:100],
            })
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
        return (retrieved, provenance, "\n".join(prompt_parts)), None

    def _sanitize_answer(self, answer: str, retrieved: Sequence[dict]) -> str:
        import re as _re
        valid_ids = {f"c{i}" for i in range(len(retrieved))}
        return _re.sub(
            r'\[#(c\d+)\]',
            lambda m: m.group(0) if m.group(1) in valid_ids else '',
            answer,
        )

    def _finish_turn(self, question: str, answer: str,
                     retrieved: List[dict], provenance: List[dict],
                     is_first_turn: bool,
                     restrict_ids: Optional[Iterable[int]],
                     use_cache: bool) -> ChatTurn:
        self.history.append(ChatMessage(role="user", content=question))
        self.history.append(ChatMessage(role="assistant", content=answer))

        turn = ChatTurn(
            answer=answer,
            sources=retrieved,
            used_chunks=len(retrieved),
            chunk_provenance=provenance,
        )

        if use_cache and is_first_turn:
            key = self._cache_key(question, restrict_ids)
            self._cache[key] = turn
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

        return turn

    def ask(self, question: str,
            restrict_ids: Optional[Iterable[int]] = None,
            use_cache: bool = True) -> ChatTurn:
        if not question.strip():
            return ChatTurn(answer="")
        restrict_ids = list(restrict_ids) if restrict_ids is not None else None

        is_first_turn, cached = self._cache_lookup(question, restrict_ids, use_cache)
        if cached is not None:
            return cached

        prepared, early_turn = self._prepare_prompt(question, restrict_ids)
        if early_turn is not None:
            return early_turn
        assert prepared is not None
        retrieved, provenance, prompt = prepared

        try:
            client = create_ai_client(self.ai_config)
            answer = client.complete(
                system=SYSTEM_PROMPT,
                prompt=prompt,
                max_tokens=500,
                temperature=0.2,
            )
        except Exception as exc:
            log.warning(f"RAG chat failed: {exc}")
            return ChatTurn(answer=f"AI request failed: {exc}", sources=retrieved)

        answer = self._sanitize_answer(answer, retrieved)
        return self._finish_turn(
            question, answer, retrieved, provenance, is_first_turn,
            restrict_ids, use_cache,
        )

    def stream_answer(self, question: str,
                      restrict_ids: Optional[Iterable[int]] = None,
                      chunk_chars: int = 160,
                      use_cache: bool = True,
                      on_event: Optional[Callable[[ChatStreamEvent], None]] = None) -> ChatStreamResult:
        if not question.strip():
            turn = ChatTurn(answer="")
            events = build_chat_stream_events(turn, chunk_chars)
            emit_chunk_events(events, on_event)
            return ChatStreamResult(turn, events)
        restrict_ids = list(restrict_ids) if restrict_ids is not None else None

        is_first_turn, cached = self._cache_lookup(question, restrict_ids, use_cache)
        if cached is not None:
            events = build_chat_stream_events(cached, chunk_chars)
            emit_chunk_events(events, on_event)
            return ChatStreamResult(cached, events)

        prepared, early_turn = self._prepare_prompt(question, restrict_ids)
        if early_turn is not None:
            events = build_chat_stream_events(early_turn, chunk_chars)
            emit_chunk_events(events, on_event)
            return ChatStreamResult(
                early_turn,
                events,
            )
        assert prepared is not None
        retrieved, provenance, prompt = prepared

        try:
            client = create_ai_client(self.ai_config)
            provider_streaming = bool(
                getattr(client, "supports_native_streaming", False)
            )
            raw_chunks = []
            provider_events = []
            for chunk in client.stream_complete(
                system=SYSTEM_PROMPT,
                prompt=prompt,
                max_tokens=500,
                temperature=0.2,
            ):
                if not chunk:
                    continue
                text = str(chunk)
                raw_chunks.append(text)
                event = ChatStreamEvent(
                    type="chunk",
                    index=len(provider_events),
                    text=text,
                )
                provider_events.append(event)
                if provider_streaming and on_event is not None:
                    on_event(event)
            raw_answer = "".join(raw_chunks)
            answer = self._sanitize_answer(raw_answer, retrieved)
        except Exception as exc:
            log.warning(f"RAG chat streaming failed: {exc}")
            turn = ChatTurn(answer=f"AI request failed: {exc}", sources=retrieved)
            return ChatStreamResult(turn, build_chat_stream_events(turn, chunk_chars))

        turn = self._finish_turn(
            question, answer, retrieved, provenance, is_first_turn,
            restrict_ids, use_cache,
        )
        events_from_provider = provider_streaming and raw_chunks and answer == raw_answer
        if events_from_provider:
            events = provider_events
            events.append(
                ChatStreamEvent(
                    type="complete",
                    index=len(raw_chunks),
                    sources=turn.sources,
                    used_chunks=turn.used_chunks,
                    chunk_provenance=turn.chunk_provenance,
                )
            )
        else:
            events = build_chat_stream_events(turn, chunk_chars)
            if not provider_streaming:
                emit_chunk_events(events, on_event)
        return ChatStreamResult(turn, events, events_from_provider)
