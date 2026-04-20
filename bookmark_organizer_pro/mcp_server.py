"""Model Context Protocol (MCP) server for Bookmark Organizer Pro.

Exposes the local bookmark library as MCP tools so Claude Desktop, Claude
Code, Cursor, and other MCP-aware agents can query and manipulate it
directly. No OSS bookmark manager ships this today — first-mover.

Run as:
    python -m bookmark_organizer_pro.mcp_server   # stdio transport

Tools exposed:
    list_bookmarks(limit, offset, category, tag) -> list
    get_bookmark(bookmark_id) -> dict
    search_bookmarks(query, limit) -> list                  (keyword)
    semantic_search(query, k) -> list                       (vector)
    hybrid_search(query, limit) -> list                     (RRF)
    add_bookmark(url, title, category, tags) -> dict
    list_tags() -> list
    list_categories() -> list
    get_extracted_text(bookmark_id) -> str
    chat_with_collection(question, restrict_ids) -> dict
    summarize_bookmark(bookmark_id) -> dict                 (cited)
    daily_digest() -> list
    list_dead_links() -> list
    list_flows() -> list
    get_flow(flow_id) -> dict
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from typing import Any, Dict, List, Optional

from bookmark_organizer_pro.ai import AIConfigManager
from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION
from bookmark_organizer_pro.core import CategoryManager
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.citation_summarizer import CitationSummarizer
from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner
from bookmark_organizer_pro.services.digest import DailyDigestService
from bookmark_organizer_pro.services.embeddings import EmbeddingService
from bookmark_organizer_pro.services.flows import FlowManager
from bookmark_organizer_pro.services.hybrid_search import HybridSearch
from bookmark_organizer_pro.services.rag_chat import CollectionChat
from bookmark_organizer_pro.services.vector_store import VectorStore


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _bm_to_dict(bm: Bookmark) -> Dict[str, Any]:
    return {
        "id": bm.id,
        "url": bm.url,
        "title": bm.title,
        "category": bm.full_category_path,
        "tags": list(bm.tags),
        "ai_tags": list(bm.ai_tags),
        "description": bm.description,
        "created_at": bm.created_at,
        "last_visited": bm.last_visited,
        "visit_count": bm.visit_count,
        "read_later": bm.read_later,
        "content_type": bm.content_type,
        "language": bm.language,
        "reading_time": bm.reading_time,
        "is_pinned": bm.is_pinned,
        "is_valid": bm.is_valid,
        "snapshot_path": bm.snapshot_path,
        "flow_id": bm.flow_id,
    }


class BookmarkServices:
    """Lazy holder for all the services the MCP server exposes."""

    def __init__(self):
        self.category_manager = CategoryManager()
        self.tag_manager = TagManager()
        self.bookmark_manager = BookmarkManager(self.category_manager, self.tag_manager)
        self.ai_config = AIConfigManager()
        self.embedder = EmbeddingService()
        self.vector_store = VectorStore(self.embedder)
        self.hybrid = HybridSearch(self.vector_store)
        self.summarizer = CitationSummarizer(self.ai_config, self.embedder)
        self.chat = CollectionChat(self.ai_config, self.vector_store)
        self.flows = FlowManager()
        self.digest = DailyDigestService()
        self.dead_links = DeadLinkScanner(
            get_bookmarks=lambda: self.bookmark_manager.get_all_bookmarks(),
        )


SERVICES: Optional[BookmarkServices] = None


def _services() -> BookmarkServices:
    global SERVICES
    if SERVICES is None:
        SERVICES = BookmarkServices()
    return SERVICES


# --- pure tool implementations ---------------------------------------------

def t_list_bookmarks(limit: int = 50, offset: int = 0,
                     category: Optional[str] = None,
                     tag: Optional[str] = None,
                     read_later_only: bool = False) -> List[Dict]:
    s = _services()
    bms = s.bookmark_manager.get_all_bookmarks()
    if category:
        bms = [b for b in bms if b.category == category or b.parent_category == category]
    if tag:
        tag_l = tag.lower()
        bms = [b for b in bms if any(t.lower() == tag_l for t in b.tags)]
    if read_later_only:
        bms = [b for b in bms if b.read_later]
    bms.sort(key=lambda b: b.created_at, reverse=True)
    return [_bm_to_dict(b) for b in bms[offset: offset + max(1, limit)]]


def t_get_bookmark(bookmark_id: int) -> Optional[Dict]:
    bm = _services().bookmark_manager.get_bookmark(int(bookmark_id))
    return _bm_to_dict(bm) if bm else None


def t_search(query: str, limit: int = 25) -> List[Dict]:
    s = _services()
    results = s.bookmark_manager.search_bookmarks(query)[:limit]
    return [_bm_to_dict(b) for b in results]


def t_semantic_search(query: str, k: int = 10) -> List[Dict]:
    s = _services()
    hits = s.vector_store.search(query, k=k)
    out: List[Dict] = []
    for hit in hits:
        bm = s.bookmark_manager.get_bookmark(hit["bookmark_id"])
        if bm is None:
            continue
        d = _bm_to_dict(bm)
        d["snippet"] = hit["text"][:300]
        d["score"] = hit["score"]
        out.append(d)
    return out


def t_hybrid_search(query: str, limit: int = 25) -> List[Dict]:
    s = _services()
    bms = s.bookmark_manager.get_all_bookmarks()
    out = []
    for r in s.hybrid.search(bms, query, limit=limit):
        d = _bm_to_dict(r.bookmark)
        d["score"] = r.score
        d["snippet"] = r.snippet
        out.append(d)
    return out


def t_add_bookmark(url: str, title: str = "", category: str = "",
                   tags: Optional[List[str]] = None) -> Optional[Dict]:
    bm = _services().bookmark_manager.add_bookmark_clean(
        url=url, title=title, category=category, tags=tags or [],
    )
    return _bm_to_dict(bm) if bm else None


def t_list_tags(limit: int = 100) -> List[Dict]:
    s = _services()
    counts = s.bookmark_manager.get_tag_counts()
    items = sorted(counts.items(), key=lambda x: -x[1])[:limit]
    return [{"tag": t, "count": c} for t, c in items]


def t_list_categories() -> List[Dict]:
    s = _services()
    counts = s.bookmark_manager.get_category_counts()
    return [{"category": c, "count": n} for c, n in sorted(counts.items())]


def t_get_extracted_text(bookmark_id: int) -> str:
    bm = _services().bookmark_manager.get_bookmark(int(bookmark_id))
    if not bm or not bm.extracted_text_path:
        return ""
    try:
        from pathlib import Path as _P
        return _P(bm.extracted_text_path).read_text(encoding="utf-8")
    except OSError:
        return ""


def t_chat(question: str, restrict_ids: Optional[List[int]] = None) -> Dict:
    s = _services()
    turn = s.chat.ask(question, restrict_ids=restrict_ids)
    return {
        "answer": turn.answer,
        "used_chunks": turn.used_chunks,
        "sources": turn.sources,
    }


def t_summarize(bookmark_id: int) -> Dict:
    s = _services()
    bm = s.bookmark_manager.get_bookmark(int(bookmark_id))
    if not bm:
        return {"error": "Bookmark not found"}
    summary = s.summarizer.summarize_bookmark(bm)
    return {
        "summary": summary.summary,
        "citations": [
            {
                "chunk_id": c.chunk_id,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "text": c.text,
            }
            for c in summary.citations
        ],
        "model": summary.model,
    }


def t_daily_digest() -> Dict:
    s = _services()
    digest = s.digest.build(s.bookmark_manager.get_all_bookmarks())
    return {
        "generated_at": digest.generated_at,
        "sections": [
            {
                "title": sec.title,
                "description": sec.description,
                "bookmarks": [_bm_to_dict(b) for b in sec.bookmarks],
            }
            for sec in digest.sections
        ],
    }


def t_dead_links() -> List[Dict]:
    s = _services()
    return [r.to_dict() for r in s.dead_links.list_dead_links()]


def t_list_flows() -> List[Dict]:
    return [
        {"id": f.id, "name": f.name, "description": f.description,
         "step_count": len(f.steps)}
        for f in _services().flows.list_flows()
    ]


def t_get_flow(flow_id: str) -> Optional[Dict]:
    flow = _services().flows.get(flow_id)
    if flow is None:
        return None
    s = _services()
    out = flow.to_dict()
    for step in out["steps"]:
        bm = s.bookmark_manager.get_bookmark(step["bookmark_id"])
        if bm:
            step["bookmark"] = _bm_to_dict(bm)
    return out


# --- MCP integration --------------------------------------------------------

TOOLS = [
    ("list_bookmarks", t_list_bookmarks,
     "List bookmarks with optional category/tag filters."),
    ("get_bookmark", t_get_bookmark, "Get a single bookmark by ID."),
    ("search_bookmarks", t_search, "Keyword search across bookmark titles/URLs."),
    ("semantic_search", t_semantic_search,
     "Semantic vector search over bookmark content (requires ingest first)."),
    ("hybrid_search", t_hybrid_search,
     "Best-of-both-worlds RRF over keyword + semantic results."),
    ("add_bookmark", t_add_bookmark,
     "Add a new bookmark with auto-categorization and URL cleaning."),
    ("list_tags", t_list_tags, "List tags with counts."),
    ("list_categories", t_list_categories, "List categories with counts."),
    ("get_extracted_text", t_get_extracted_text,
     "Return the extracted readable text for a bookmark."),
    ("chat_with_collection", t_chat,
     "Conversational RAG over the bookmark library."),
    ("summarize_bookmark", t_summarize,
     "AI summary of a bookmark with inline citations back to source spans."),
    ("daily_digest", t_daily_digest,
     "On-this-day digest plus rediscover/read-later/stale picks."),
    ("list_dead_links", t_dead_links,
     "Bookmarks the scheduled scanner has flagged as broken/redirected."),
    ("list_flows", t_list_flows,
     "List research flows (ordered, annotated bookmark sequences)."),
    ("get_flow", t_get_flow, "Get a flow with its steps and bookmarks."),
]


async def serve_stdio() -> int:
    """Run the MCP server over stdio. Requires `mcp` package."""
    mcp = _try_import("mcp")
    if mcp is None:
        print("error: install `mcp` (pip install mcp) to run the MCP server",
              file=sys.stderr)
        return 1
    server_module = _try_import("mcp.server")
    stdio = _try_import("mcp.server.stdio")
    types = _try_import("mcp.types")
    if server_module is None or stdio is None or types is None:
        print("error: incomplete MCP installation", file=sys.stderr)
        return 1

    Server = getattr(server_module, "Server")
    NotificationOptions = getattr(server_module, "NotificationOptions", None)
    InitializationOptions = None
    init_options_module = _try_import("mcp.server.models")
    if init_options_module is not None:
        InitializationOptions = getattr(init_options_module, "InitializationOptions", None)

    server = Server("bookmark-organizer-pro")

    @server.list_tools()
    async def _list_tools() -> List[Any]:
        from mcp.types import Tool
        return [
            Tool(
                name=name,
                description=desc,
                inputSchema={"type": "object", "additionalProperties": True},
            )
            for name, _, desc in TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]) -> List[Any]:
        from mcp.types import TextContent
        impl = next((fn for tname, fn, _ in TOOLS if tname == name), None)
        if impl is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            result = impl(**(arguments or {}))
        except TypeError as exc:
            return [TextContent(type="text", text=f"Bad arguments: {exc}")]
        except Exception as exc:
            log.exception(f"MCP tool {name} failed")
            return [TextContent(type="text", text=f"Error: {exc}")]
        return [TextContent(type="text",
                            text=json.dumps(result, indent=2, default=str))]

    init_options = None
    if InitializationOptions is not None and NotificationOptions is not None:
        init_options = InitializationOptions(
            server_name="bookmark-organizer-pro",
            server_version=APP_VERSION,
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            ),
        )

    async with stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)
    return 0


def main():
    log.info(f"{APP_NAME} MCP server v{APP_VERSION} starting (stdio)")
    try:
        sys.exit(asyncio.run(serve_stdio()))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
