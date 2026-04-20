"""Citation-aware AI summarizer.

Generates summaries that cite back to specific text spans within the
source bookmark. Each chunk has a stable id (`c0`, `c1`, ...) and a
char offset; the LLM is asked to emit `[#cN]` tokens, which can then
be resolved by the UI to a click-to-source highlight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bookmark_organizer_pro.ai import AIConfigManager, create_ai_client
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.embeddings import EmbeddingService


CITATION_PATTERN = re.compile(r"\[#(c\d+)\]")


@dataclass
class Citation:
    chunk_id: str
    char_start: int
    char_end: int
    text: str
    bookmark_id: int = 0


@dataclass
class CitedSummary:
    summary: str
    citations: List[Citation] = field(default_factory=list)
    model: str = ""

    def render_html(self) -> str:
        """Replace [#cN] tokens with <a> anchors."""
        out = self.summary
        for cit in self.citations:
            anchor = f'<a href="#{cit.chunk_id}" data-start="{cit.char_start}" '\
                     f'data-end="{cit.char_end}">{cit.chunk_id}</a>'
            out = out.replace(f"[#{cit.chunk_id}]", anchor)
        return out


SYSTEM_PROMPT = (
    "You are a careful summarizer. You are given numbered text chunks. "
    "Write a concise summary (3-6 sentences). After every claim, cite the "
    "supporting chunk(s) using the form [#cN] where N is the chunk number. "
    "Do not invent facts. If a claim is not supported by the chunks, omit it."
)


class CitationSummarizer:
    """Produce a cited summary from a bookmark's extracted text."""

    def __init__(self, ai_config: AIConfigManager,
                 embedder: Optional[EmbeddingService] = None):
        self.ai_config = ai_config
        self.embedder = embedder or EmbeddingService()

    # ------------------------------------------------------------------
    def summarize_bookmark(self, bookmark: Bookmark,
                           extracted_text: Optional[str] = None,
                           max_chunks: int = 8) -> CitedSummary:
        """Summarize the given bookmark with inline citations."""
        text = extracted_text
        if text is None and bookmark.extracted_text_path:
            try:
                text = Path(bookmark.extracted_text_path).read_text(encoding="utf-8")
            except OSError as exc:
                log.warning(f"Could not read extracted text: {exc}")
                return CitedSummary(summary="", citations=[])
        if not text:
            return CitedSummary(summary="", citations=[])

        chunks = EmbeddingService.chunk_text(text)[:max_chunks]
        if not chunks:
            return CitedSummary(summary="", citations=[])

        prompt = self._build_prompt(bookmark, chunks)
        try:
            client = create_ai_client(self.ai_config)
            response = client.complete(
                system=SYSTEM_PROMPT,
                prompt=prompt,
                max_tokens=600,
                temperature=0.2,
            )
        except Exception as exc:
            log.warning(f"Citation summary failed: {exc}")
            return CitedSummary(summary="", citations=[])

        return self._parse_response(response, chunks, bookmark.id,
                                    model=str(self.ai_config.get_model() or ""))

    # ------------------------------------------------------------------
    def _build_prompt(self, bookmark: Bookmark, chunks: List[Dict]) -> str:
        lines = [
            f"TITLE: {bookmark.title}",
            f"URL: {bookmark.url}",
            "",
            "CHUNKS:",
        ]
        for c in chunks:
            lines.append(f"[{c['id']}] {c['text']}")
            lines.append("")
        lines.append("Write the cited summary now.")
        return "\n".join(lines)

    def _parse_response(self, text: str, chunks: List[Dict],
                        bookmark_id: int, model: str) -> CitedSummary:
        cited_ids = set(CITATION_PATTERN.findall(text or ""))
        chunk_lookup = {c["id"]: c for c in chunks}
        citations = []
        for cid in cited_ids:
            chunk = chunk_lookup.get(cid)
            if not chunk:
                continue
            citations.append(Citation(
                chunk_id=cid,
                char_start=int(chunk["char_start"]),
                char_end=int(chunk["char_end"]),
                text=chunk["text"][:400],
                bookmark_id=int(bookmark_id),
            ))
        return CitedSummary(summary=text or "", citations=citations, model=model)
