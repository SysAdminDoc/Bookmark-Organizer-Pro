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
from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION, SNAPSHOTS_DIR
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
from bookmark_organizer_pro.services.zip_export import ZipExporter
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
        self.zip_exporter = ZipExporter()
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
    s = _services()
    existing = s.bookmark_manager.find_by_url(url)
    if existing:
        d = _bm_to_dict(existing)
        d["already_exists"] = True
        return d
    bm = s.bookmark_manager.add_bookmark_clean(
        url=url, title=title, category=category, tags=tags or [],
    )
    if bm:
        d = _bm_to_dict(bm)
        d["already_exists"] = False
        return d
    return None


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


def t_create_flow(name: str, description: str = "") -> Dict:
    flow = _services().flows.create(name=name, description=description)
    return flow.to_dict()


def t_append_to_flow(flow_id: str, bookmark_id: int, note: str = "") -> Dict:
    s = _services()
    ok = s.flows.add_step(flow_id, int(bookmark_id), note=note)
    if not ok:
        return {"error": "Flow not found or bookmark already in flow"}
    flow = s.flows.get(flow_id)
    return flow.to_dict() if flow else {"error": "Flow not found"}


def t_export_zip(bookmark_id: int) -> Dict:
    s = _services()
    bm = s.bookmark_manager.get_bookmark(int(bookmark_id))
    if not bm:
        return {"error": "Bookmark not found"}
    ok, path_or_err = s.zip_exporter.export_one(bm)
    if ok:
        return {"path": path_or_err, "bookmark_id": bm.id}
    return {"error": path_or_err}


def t_list_snapshots(limit: int = 50) -> List[Dict]:
    out = []
    if not SNAPSHOTS_DIR.is_dir():
        return out
    for f in sorted(SNAPSHOTS_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)[:max(1, limit)]:
        try:
            stat = f.stat()
            out.append({"filename": f.name, "size": stat.st_size,
                        "modified": stat.st_mtime})
        except OSError:
            continue
    return out


# --- MCP integration --------------------------------------------------------

TOOLS = [
    ("list_bookmarks", t_list_bookmarks,
     "List bookmarks with optional category/tag/read-later filters, sorted newest first.",
     {
         "type": "object",
         "properties": {
             "limit": {"type": "integer", "description": "Max bookmarks to return (default 50)", "default": 50},
             "offset": {"type": "integer", "description": "Skip first N bookmarks for pagination", "default": 0},
             "category": {"type": "string", "description": "Filter by category name"},
             "tag": {"type": "string", "description": "Filter by tag (case-insensitive)"},
             "read_later_only": {"type": "boolean", "description": "If true, only return read-later bookmarks", "default": False},
         },
     }),
    ("get_bookmark", t_get_bookmark,
     "Get a single bookmark by its numeric ID.",
     {
         "type": "object",
         "properties": {
             "bookmark_id": {"type": "integer", "description": "The bookmark ID"},
         },
         "required": ["bookmark_id"],
     }),
    ("search_bookmarks", t_search,
     "Keyword search across bookmark titles, URLs, tags, and descriptions. Supports boolean operators (AND, OR) and field prefixes (title:, url:, tag:, category:).",
     {
         "type": "object",
         "properties": {
             "query": {"type": "string", "description": "Search query string"},
             "limit": {"type": "integer", "description": "Max results (default 25)", "default": 25},
         },
         "required": ["query"],
     }),
    ("semantic_search", t_semantic_search,
     "Semantic vector search over ingested bookmark content. Requires running 'embed' first. Returns bookmarks ranked by meaning similarity.",
     {
         "type": "object",
         "properties": {
             "query": {"type": "string", "description": "Natural language query"},
             "k": {"type": "integer", "description": "Number of results (default 10)", "default": 10},
         },
         "required": ["query"],
     }),
    ("hybrid_search", t_hybrid_search,
     "Best-of-both-worlds search: fuses keyword and semantic results via Reciprocal Rank Fusion. Falls back to keyword-only if no embeddings exist.",
     {
         "type": "object",
         "properties": {
             "query": {"type": "string", "description": "Search query"},
             "limit": {"type": "integer", "description": "Max results (default 25)", "default": 25},
         },
         "required": ["query"],
     }),
    ("add_bookmark", t_add_bookmark,
     "Add a new bookmark with automatic categorization via 4,200+ pattern rules and URL tracking-param cleaning.",
     {
         "type": "object",
         "properties": {
             "url": {"type": "string", "description": "The URL to bookmark (required)"},
             "title": {"type": "string", "description": "Display title (auto-fetched if blank)"},
             "category": {"type": "string", "description": "Category name (auto-categorized if blank)"},
             "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags to apply"},
         },
         "required": ["url"],
     }),
    ("list_tags", t_list_tags,
     "List all tags with usage counts, sorted by most-used first.",
     {
         "type": "object",
         "properties": {
             "limit": {"type": "integer", "description": "Max tags to return (default 100)", "default": 100},
         },
     }),
    ("list_categories", t_list_categories,
     "List all categories with bookmark counts, sorted alphabetically.",
     {"type": "object", "properties": {}}),
    ("get_extracted_text", t_get_extracted_text,
     "Return the extracted readable text for a bookmark (requires prior ingest).",
     {
         "type": "object",
         "properties": {
             "bookmark_id": {"type": "integer", "description": "The bookmark ID"},
         },
         "required": ["bookmark_id"],
     }),
    ("chat_with_collection", t_chat,
     "Ask a question about your bookmark collection using RAG. Retrieves relevant bookmark content and generates an AI answer with source attribution.",
     {
         "type": "object",
         "properties": {
             "question": {"type": "string", "description": "Your question about saved bookmarks"},
             "restrict_ids": {"type": "array", "items": {"type": "integer"}, "description": "Optional: limit retrieval to these bookmark IDs"},
         },
         "required": ["question"],
     }),
    ("summarize_bookmark", t_summarize,
     "Generate an AI summary of a bookmark with inline [#cN] citations that link back to specific text spans in the source.",
     {
         "type": "object",
         "properties": {
             "bookmark_id": {"type": "integer", "description": "The bookmark ID to summarize"},
         },
         "required": ["bookmark_id"],
     }),
    ("daily_digest", t_daily_digest,
     "Generate a daily digest with sections: on-this-day, this-week-last-year, rediscover (random older saves), read-later queue, and stale-but-loved.",
     {"type": "object", "properties": {}}),
    ("list_dead_links", t_dead_links,
     "List bookmarks the scheduled dead-link scanner has flagged as broken or redirected.",
     {"type": "object", "properties": {}}),
    ("list_flows", t_list_flows,
     "List all research flows (ordered, annotated bookmark sequences for research trails).",
     {"type": "object", "properties": {}}),
    ("get_flow", t_get_flow,
     "Get a specific research flow with all its steps and associated bookmarks.",
     {
         "type": "object",
         "properties": {
             "flow_id": {"type": "string", "description": "The flow ID"},
         },
         "required": ["flow_id"],
     }),
    ("create_flow", t_create_flow,
     "Create a new research flow (ordered bookmark sequence for a topic deep-dive).",
     {
         "type": "object",
         "properties": {
             "name": {"type": "string", "description": "Flow name"},
             "description": {"type": "string", "description": "Optional description"},
         },
         "required": ["name"],
     }),
    ("append_to_flow", t_append_to_flow,
     "Add a bookmark to an existing research flow, optionally with a per-step note.",
     {
         "type": "object",
         "properties": {
             "flow_id": {"type": "string", "description": "The flow ID to append to"},
             "bookmark_id": {"type": "integer", "description": "Bookmark ID to add"},
             "note": {"type": "string", "description": "Optional note for this step"},
         },
         "required": ["flow_id", "bookmark_id"],
     }),
    ("export_zip", t_export_zip,
     "Export a bookmark as a portable ZIP archive containing metadata, snapshot, extracted text, and notes.",
     {
         "type": "object",
         "properties": {
             "bookmark_id": {"type": "integer", "description": "Bookmark ID to export"},
         },
         "required": ["bookmark_id"],
     }),
    ("list_snapshots", t_list_snapshots,
     "List captured HTML snapshots sorted by most recent first.",
     {
         "type": "object",
         "properties": {
             "limit": {"type": "integer", "description": "Max snapshots to return (default 50)", "default": 50},
         },
     }),
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
                inputSchema=schema,
            )
            for name, _, desc, schema in TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]) -> List[Any]:
        from mcp.types import TextContent
        impl = next((fn for tname, fn, _, _ in TOOLS if tname == name), None)
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


def _build_fastmcp_server():
    """Build an MCP server using FastMCP 3.x if available. Returns None if not installed."""
    fastmcp_mod = _try_import("fastmcp")
    if fastmcp_mod is None:
        return None
    FastMCP = getattr(fastmcp_mod, "FastMCP", None)
    if FastMCP is None:
        return None
    try:
        mcp_app = FastMCP("bookmark-organizer-pro")
    except Exception:
        return None

    @mcp_app.tool(description="List bookmarks with optional category/tag/read-later filters, sorted newest first.")
    def list_bookmarks(limit: int = 50, offset: int = 0, category: str | None = None,
                       tag: str | None = None, read_later_only: bool = False) -> list[dict]:
        return t_list_bookmarks(limit, offset, category, tag, read_later_only)

    @mcp_app.tool(description="Get a single bookmark by its numeric ID.")
    def get_bookmark(bookmark_id: int) -> dict | None:
        return t_get_bookmark(bookmark_id)

    @mcp_app.tool(description="Keyword search across bookmark titles, URLs, tags, and descriptions.")
    def search_bookmarks(query: str, limit: int = 25) -> list[dict]:
        return t_search(query, limit)

    @mcp_app.tool(description="Semantic vector search over ingested bookmark content.")
    def semantic_search(query: str, k: int = 10) -> list[dict]:
        return t_semantic_search(query, k)

    @mcp_app.tool(description="Hybrid keyword+semantic search via Reciprocal Rank Fusion.")
    def hybrid_search(query: str, limit: int = 25) -> list[dict]:
        return t_hybrid_search(query, limit)

    @mcp_app.tool(description="Add a new bookmark with auto-categorization and URL cleaning.")
    def add_bookmark(url: str, title: str = "", category: str = "",
                     tags: list[str] | None = None) -> dict | None:
        return t_add_bookmark(url, title, category, tags)

    @mcp_app.tool(description="List all tags with usage counts.")
    def list_tags(limit: int = 100) -> list[dict]:
        return t_list_tags(limit)

    @mcp_app.tool(description="List all categories with bookmark counts.")
    def list_categories() -> list[dict]:
        return t_list_categories()

    @mcp_app.tool(description="Return extracted readable text for a bookmark.")
    def get_extracted_text(bookmark_id: int) -> str:
        return t_get_extracted_text(bookmark_id)

    @mcp_app.tool(description="Conversational RAG over the bookmark library.")
    def chat_with_collection(question: str, restrict_ids: list[int] | None = None) -> dict:
        return t_chat(question, restrict_ids)

    @mcp_app.tool(description="AI summary with inline citations back to source spans.")
    def summarize_bookmark(bookmark_id: int) -> dict:
        return t_summarize(bookmark_id)

    @mcp_app.tool(description="Daily digest: on-this-day, rediscover, read-later, stale picks.")
    def daily_digest() -> dict:
        return t_daily_digest()

    @mcp_app.tool(description="List bookmarks flagged as broken/redirected by the dead-link scanner.")
    def list_dead_links() -> list[dict]:
        return t_dead_links()

    @mcp_app.tool(description="List all research flows.")
    def list_flows() -> list[dict]:
        return t_list_flows()

    @mcp_app.tool(description="Get a research flow with its steps and bookmarks.")
    def get_flow(flow_id: str) -> dict | None:
        return t_get_flow(flow_id)

    @mcp_app.tool(description="Create a new research flow.")
    def create_flow(name: str, description: str = "") -> dict:
        return t_create_flow(name, description)

    @mcp_app.tool(description="Add a bookmark to a research flow.")
    def append_to_flow(flow_id: str, bookmark_id: int, note: str = "") -> dict:
        return t_append_to_flow(flow_id, bookmark_id, note)

    @mcp_app.tool(description="Export a bookmark as a portable ZIP archive.")
    def export_zip(bookmark_id: int) -> dict:
        return t_export_zip(bookmark_id)

    @mcp_app.tool(description="List captured HTML snapshots.")
    def list_snapshots(limit: int = 50) -> list[dict]:
        return t_list_snapshots(limit)

    return mcp_app


def main():
    from bookmark_organizer_pro.constants import ensure_directories
    ensure_directories()
    log.info(f"{APP_NAME} MCP server v{APP_VERSION} starting (stdio)")

    fastmcp_app = _build_fastmcp_server()
    if fastmcp_app is not None:
        log.info("Using FastMCP transport (auto-schema + ToolAnnotations)")
        try:
            fastmcp_app.run(transport="stdio")
        except KeyboardInterrupt:
            pass
        return

    log.info("FastMCP not available, using raw mcp SDK fallback")
    try:
        sys.exit(asyncio.run(serve_stdio()))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
