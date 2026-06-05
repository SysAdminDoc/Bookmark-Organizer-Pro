# Bookmark Organizer Pro — Research and Feature Plan

**Date:** 2026-06-05
**Version Analyzed:** v6.0.0
**Codebase:** ~34,822 lines of Python across ~110 files, 142 test methods in `tests/test_core.py`

---

## 1. Executive Summary

Bookmark Organizer Pro (BOP) v6.0.0 is a genuinely differentiated product — the only open-source bookmark manager shipping an MCP server, conversational RAG over saved content, citation-aware AI summaries, hybrid keyword+vector search with RRF, and AES-256-GCM encrypted local database. It sits at the intersection of local-first privacy and AI-powered knowledge management, a niche no competitor occupies fully. The codebase, however, has accrued significant technical debt: two critical bugs that crash entire AI feature paths at runtime (`categorize_bookmark` singular method and `.settings` attribute access), an infinite-loop risk in the embedding chunker, thread-safety gaps across 5+ services, an MCP server with no typed schemas (defeating AI agent interoperability), a PyInstaller spec missing all v6.0 hidden imports (making the distributed binary unable to use any v6 feature), and a UI layer that blocks the main thread during network calls and chokes past ~10K bookmarks. The competitive landscape strongly validates BOP's direction — Pocket and Omnivore are dead, Karakeep/Linkwarden are heavy Docker stacks, and no competitor covers all three AI tiers (summary + organization + query). The highest-value investments are: (1) fix the 2 critical runtime crashers and the chunk overlap bug, (2) type the MCP server schemas, (3) move network calls off the main thread, (4) ship a browser extension for one-click save, (5) add a web client for mobile/remote access, and (6) migrate to FastMCP + Nuitka for distribution polish.

**Top 10 Opportunities (ordered by impact):**

1. **Fix 2 critical AI crashers** — `categorize_bookmark` (singular) does not exist, `.settings` attribute does not exist on AIConfigManager. Every AI batch/tag path is dead code at runtime. [S complexity, P0]
2. **Fix embedding chunk overlap infinite-loop risk** — `max(end - overlap, end)` always returns `end`, producing zero overlap and risking infinite loops. [S, P0]
3. **Type the MCP server tool schemas** — current `additionalProperties: true` gives AI agents zero parameter info; migrate to FastMCP 3.x or manually define JSON Schema per tool. [M, P0]
4. **Fix PyInstaller spec** — missing all v6.0 hidden imports; the shipped .exe cannot use any v6 feature. [M, P0]
5. **Move AI/link-check network calls off main thread** — 4 code paths block the Tkinter event loop with synchronous HTTP. [M, P1]
6. **Ship a browser extension** — the single biggest UX gap vs. every competitor. MV3 + native messaging to localhost MCP/API. [L, P1]
7. **Add web client** (FastAPI + HTMX) — enables mobile PWA, remote access, multi-device. Every competitor has this. [XL, P1]
8. **Implement list virtualization** — Treeview chokes past ~10K rows; tksheet or canvas-based virtual scrolling. [M, P1]
9. **Add per-domain rate limiting to link checker** — currently fires 10+ concurrent requests to the same domain with no delay. [M, P1]
10. **Add atomic writes to VectorStore and DeadLinkScanner** — crash during write loses all data. [S, P1]

---

## 2. Evidence Reviewed

| Source | Scope |
|--------|-------|
| Code audit: `bookmark_organizer_pro/services/` | 20 findings across embeddings, vector_store, ai_tools, dead_link_scanner, encryption, rss_feeds, snapshot, web_tools, api, tag_linter, dup_hybrid, favicons, local_state |
| Code audit: UI layer (Tkinter) | 25 findings across app_mixins, ui/ widgets, treeview, feedback, shell_widgets, themes, dashboard, lifecycle, categories, bookmarks, bookmark_crud, selection, tools, drag_drop, components |
| Code audit: Core data layer | 20 findings across models, storage, search, importers, pattern_engine, url utils, link_checker, managers |
| Code audit: Infrastructure | 15 findings across CLI, MCP server, packaging, tests, CI/CD, dependencies, logging, startup |
| Code audit: AI integration layer | 15 findings across ai.py, ai_tools.py, citation_summarizer, rag_chat, nl_query, ai_enrichment, ai_titles, ai_categorization |
| Competitive research: Round 1 | 11 products: Linkwarden, Karakeep, Raindrop.io, Readeck, ArchiveBox, Shiori, Wallabag, Linkding, Omnivore, Pinboard, Pocket |
| Competitive research: Round 2 | 15 products/tools: Raindrop.io, Linkwarden, Karakeep, Readwise Reader, Burn 451, mymind, CustomTkinter, sv-ttk, tksheet, FastMCP, LanceDB, FastEmbed, Nuitka, tufup, Ollama |
| Existing ROADMAP.md | 6 sections, ~35 planned items |
| README.md, CHANGELOG.md, ARCHITECTURE.md, pyproject.toml, requirements.txt, build.yml | Project metadata, CI/CD, packaging |
| `tests/test_core.py` | 22 test classes, 142 test methods |

---

## 3. Current Product Map

### 3.1 Workflows

| Workflow | Entry Point | Description |
|----------|-------------|-------------|
| Desktop GUI | `main.py` -> `FinalBookmarkOrganizerApp` in `app.py` | Tkinter app with 15 mixins |
| CLI | `python -m bookmark_organizer_pro.cli` | 30+ subcommands |
| MCP server | `python -m bookmark_organizer_pro.mcp_server` | stdio transport, 15 tools |
| REST API | `BookmarkAPI` in `services/api.py` | HTTP on 127.0.0.1, no auth |
| PyInstaller binary | `packaging/bookmark_organizer.spec` | Cross-platform .exe |

### 3.2 Features by Category

**Import/Export:** 13 importers (Chrome, Firefox, Edge, Safari, Pocket, Readwise, Pinboard, Instapaper, Reddit, Raindrop, OPML, OneTab, Netscape HTML), 6+ exporters (HTML, JSON, CSV, OPML, XBEL, Markdown, per-bookmark ZIP).

**Organization:** 4,224 categorization patterns across 32 categories, hierarchical categories, tags with color coding, flows/research trails, read-later queue, collections.

**AI:** 5 providers (OpenAI, Anthropic, Gemini, Groq, Ollama), auto-categorization, tag suggestions, title improvement, content summarization, citation-aware summaries, conversational RAG, NL-to-structured-query.

**Search:** Full-text with boolean operators, semantic vector search (LanceDB + FastEmbed), hybrid RRF fusion, fuzzy matching.

**Preservation:** Single-file HTML snapshots (monolith/single-file/BS4), dead-link scanner, Wayback Machine integration, favicon caching.

**Security:** AES-256-GCM encrypted DB, SSRF protection, URL normalization (strips 60+ tracking params), PBKDF2-HMAC-SHA256 key derivation.

**UI:** 10+ themes, custom theme creator, command palette, toast notifications, zoom, high-DPI support, system tray (stub).

### 3.3 Target Personas

1. **Power user / developer** — saves 50+ bookmarks/week, wants AI categorization, semantic search, MCP integration with Claude/Cursor
2. **Privacy-conscious researcher** — encrypted DB, local-first, no cloud dependency, Ollama for AI
3. **Pocket/Omnivore refugee** — needs import from dead services, reliable local preservation
4. **IT professional/sysadmin** — 4,200+ patterns cover IT/DevOps domains, CLI for scripting

### 3.4 Platforms

- Windows (primary, PyInstaller .exe)
- macOS (PyInstaller binary)
- Linux (PyInstaller binary)
- No mobile, no web client, no browser extension

### 3.5 Integrations

- MCP server (Claude Desktop, Claude Code, Cursor, Codex)
- REST API (localhost, unauthenticated)
- Browser profile auto-import (Chrome, Firefox, Edge, Brave — one-time, not live sync)
- Wayback Machine
- 5 AI provider APIs
- thum.io screenshot API (third-party, privacy concern)

---

## 4. Feature Inventory

### 4.1 Embedding Service

| Attribute | Value |
|-----------|-------|
| **Entry point** | CLI: `embed`, `hybrid`; MCP: `semantic_search`, `hybrid_search` |
| **Code** | `services/embeddings.py` (~188 lines) |
| **Maturity** | v6.0.0 — new. Three-backend chain (fastembed -> model2vec -> sentence-transformers) |
| **Tests** | Zero |
| **Bugs found** | **CRITICAL**: chunk overlap infinite loop (line 182: `max(end-overlap, end)` always returns `end`). Embedding model partial-init crash (lines 87-100). |
| **Improvements** | Fix overlap bug. Reset `self._embedder = None` in each loader's except. Add unit tests for chunk_text edge cases (empty, single-char, exactly chunk_size). |

### 4.2 MCP Server

| Attribute | Value |
|-----------|-------|
| **Entry point** | `python -m bookmark_organizer_pro.mcp_server` |
| **Code** | `mcp_server.py` (~382 lines) |
| **Maturity** | v6.0.0 — new. First OSS bookmark manager with MCP. |
| **Tests** | Zero |
| **Bugs found** | **HIGH**: All 15 tools use `inputSchema={"type": "object", "additionalProperties": True}` — no typed parameters. **MEDIUM**: Global singleton `SERVICES` with no async lock. Eager top-level imports crash if optional deps missing. |
| **Improvements** | Migrate to FastMCP 3.x for auto-schema from type hints, or manually define schemas. Add asyncio.Lock for mutating operations. Move imports to lazy init. Add `readOnlyHint` ToolAnnotations for safe queries. |

### 4.3 AI Batch Processor

| Attribute | Value |
|-----------|-------|
| **Entry point** | GUI: AI menu -> batch categorize |
| **Code** | `services/ai_tools.py` (AIBatchProcessor, lines 60-210) |
| **Maturity** | v6.0.0 — broken at runtime |
| **Tests** | Zero |
| **Bugs found** | **CRITICAL**: `self.ai_config.settings` (line 90) — AIConfigManager has no `.settings` attr; crashes with AttributeError. **CRITICAL**: `self._client.categorize_bookmark()` (line 183) — method does not exist on any AIClient subclass. **LOW**: `except Exception: pass` (line 200-201) swallows all errors silently. |
| **Improvements** | Replace `.settings.get(...)` with accessor methods. Replace `categorize_bookmark` with `categorize_bookmarks`. Log exceptions instead of swallowing. |

### 4.4 Vector Store

| Attribute | Value |
|-----------|-------|
| **Entry point** | Used by HybridSearch, CollectionChat, CitationSummarizer |
| **Code** | `services/vector_store.py` (~226 lines) |
| **Maturity** | v6.0.0 — new |
| **Tests** | Zero |
| **Bugs found** | **HIGH**: `_persist_memory()` writes JSON non-atomically (line 219-226); crash during write corrupts all vector data. |
| **Improvements** | Use atomic write (tempfile + os.replace). Add periodic `table.optimize()` for LanceDB backend. |

### 4.5 Dead Link Scanner

| Attribute | Value |
|-----------|-------|
| **Entry point** | CLI: `scan`; GUI: Tools menu |
| **Code** | `services/dead_link_scanner.py` (~170 lines) |
| **Maturity** | v6.0.0 — new |
| **Tests** | Zero |
| **Bugs found** | **HIGH**: Concurrent bookmark mutation without lock (lines 93-96 vs link_checker.py 135-141). **MEDIUM**: Non-atomic file persistence (line 166-168). |
| **Improvements** | Return results as data from workers, apply under lock. Use atomic write. |

### 4.6 Encryption

| Attribute | Value |
|-----------|-------|
| **Entry point** | CLI: `encrypt`, `decrypt`; Settings toggle |
| **Code** | `services/encryption.py` (~130 lines) |
| **Maturity** | v6.0.0 — new |
| **Tests** | Zero |
| **Bugs found** | **INFO**: Nonce handling is correct (fresh `os.urandom(12)` per encrypt). **MEDIUM**: `decrypt_file` can overwrite unrelated files (line 107-108). |
| **Improvements** | Validate `dst != src`. Refuse to overwrite if dst exists without backup. |

### 4.7 Pattern Engine

| Attribute | Value |
|-----------|-------|
| **Entry point** | Auto-categorization on bookmark add, CLI: `categorize` |
| **Code** | `core/pattern_engine.py` (~60 lines), `core/default_categories.py` (~2,200 lines) |
| **Maturity** | v5.0.0+ — stable, heavily expanded |
| **Tests** | 10+ tests in TestPatternEngine |
| **Bugs found** | **MEDIUM**: Duplicate patterns (retool.com on lines 40+56), cross-category conflicts (serverfault.com, hetzner.com), overly broad plain patterns ('porn.', 'click.', ':3000'). **MEDIUM**: No ReDoS timeout on regex patterns (line 52-56). |
| **Improvements** | Deduplicate patterns. Add priority/weight system. Convert ambiguous plain patterns to typed. Use re2 or add regex timeout. |

### 4.8 Search Engine

| Attribute | Value |
|-----------|-------|
| **Entry point** | GUI search bar, CLI: `search`, MCP: `search_bookmarks` |
| **Code** | `search.py` (~430 lines) |
| **Maturity** | v5.0.0+ — stable |
| **Tests** | 15+ tests in TestSearchQuery |
| **Bugs found** | **LOW**: Returns all bookmarks for empty query (line 237-239). **LOW**: Date filter silently includes bookmarks with bad timestamps (line 178-184). |
| **Improvements** | Return empty list for empty queries. Return False for unparseable timestamps when date filter active. |

### 4.9 Bookmark Manager

| Attribute | Value |
|-----------|-------|
| **Entry point** | Core manager used by all features |
| **Code** | `managers/bookmarks.py` (~650 lines) |
| **Maturity** | v4.0.0+ — mature core |
| **Tests** | 20+ tests in TestMainAppManagers |
| **Bugs found** | **HIGH**: `batch_refresh_metadata` mutates bookmarks from worker threads without lock (line 571-585). **MEDIUM**: `save_bookmarks` releases BookmarkManager lock before StorageManager.save(), creating a race (line 117-120). **LOW**: `get_stale_bookmarks` ignores its `days` parameter (line 336-338). |
| **Improvements** | Collect results from workers as dicts, apply under lock. Hold BM lock through storage.save(). Use `days` parameter in filtering. |

### 4.10 Link Checker

| Attribute | Value |
|-----------|-------|
| **Entry point** | GUI: Tools -> Check Links, CLI: `check` |
| **Code** | `link_checker.py` (~150 lines) |
| **Maturity** | v4.0.0+ — functional but aggressive |
| **Tests** | Basic import test only |
| **Bugs found** | **HIGH**: No per-domain rate limiting, no robots.txt, generic User-Agent. 10+ concurrent requests to same domain. |
| **Improvements** | Per-domain rate limit (2 concurrent, 1s delay). Add `BookmarkOrganizerPro/6.0 LinkChecker` UA. |

### 4.11 RSS Feed Ingestor

| Attribute | Value |
|-----------|-------|
| **Entry point** | CLI: `feeds`, `fetch-feeds` |
| **Code** | `services/rss_feeds.py` (~200 lines) |
| **Maturity** | v6.0.0 — new |
| **Tests** | Zero |
| **Bugs found** | **MEDIUM**: Uses `xml.etree.ElementTree.fromstring()` on untrusted network input (XML bomb vulnerability, line 150). **LOW**: `FeedRegistry.update()` allows arbitrary attribute mutation including 'id' (line 128-137). |
| **Improvements** | Use `defusedxml.ElementTree.fromstring()`. Whitelist mutable fields in update(). |

### 4.12 Snapshot Archiver

| Attribute | Value |
|-----------|-------|
| **Entry point** | CLI: `snapshot`; auto-snapshot planned |
| **Code** | `services/snapshot.py` (~190 lines) |
| **Maturity** | v6.0.0 — new |
| **Tests** | Zero |
| **Bugs found** | **MEDIUM**: HTML injection via unescaped URL in banner (lines 181-185). |
| **Improvements** | Use `html.escape(url, quote=True)` in banner f-string. |

### 4.13 REST API

| Attribute | Value |
|-----------|-------|
| **Entry point** | `BookmarkAPI` in `services/api.py` |
| **Code** | `services/api.py` (~260 lines) |
| **Maturity** | v6.0.0 — new |
| **Tests** | Zero |
| **Bugs found** | **MEDIUM**: No authentication, no CORS protection. Any local process or webpage can read/create/delete bookmarks. |
| **Improvements** | Add bearer token. Add CORS deny headers. Validate Origin on mutating requests. |

### 4.14 Importers

| Attribute | Value |
|-----------|-------|
| **Entry point** | GUI: Import button, CLI: `import` |
| **Code** | `importers.py` (~400 lines), `importers_extra.py` (~290 lines) |
| **Maturity** | v4.0.0+ — functional |
| **Tests** | Basic tests for OPML, Raindrop, TextURL |
| **Bugs found** | **MEDIUM**: No intra-file dedup. **LOW**: Firefox CTE `GROUP_CONCAT` order non-deterministic. |
| **Improvements** | Add seen-set for intra-file dedup. Use Python-side path construction for Firefox. |

### 4.15 Bookmark Model

| Attribute | Value |
|-----------|-------|
| **Entry point** | `models/bookmark.py` |
| **Code** | ~250 lines |
| **Maturity** | v4.0.0+ — mature |
| **Tests** | 15+ tests |
| **Bugs found** | **LOW**: `remove_tag` uses exact case vs `add_tag` case-insensitive. **LOW**: `age_days`/`is_stale` strip timezone causing up to 12h error. **LOW**: Category depth counts ' / ' in names. |
| **Improvements** | Case-insensitive remove_tag. UTC-consistent timestamps. Use parent chain for depth. |

---

## 5. Competitive and Ecosystem Research

### 5.1 Direct Competitors

| Product | Type | Stars | Key Capability | What to Learn | What to Avoid |
|---------|------|-------|----------------|---------------|---------------|
| **Linkwarden** | Self-hosted, Next.js+PG | 18.5K | Triple-format archive + reader view with highlights | Reader view with annotation; collection hierarchy | Docker-only; PostgreSQL requirement; cookie-based prefs |
| **Karakeep** (ex-Hoarder) | Self-hosted, bookmark-everything | 25.6K | AI tagging (Ollama/OpenAI) + full-text via Meilisearch | Ollama-first AI; save notes/images/PDFs alongside bookmarks; OCR | 4GB+ RAM; Docker-only; Meilisearch sidecar; fragile Ollama integration |
| **Raindrop.io** | Cloud SaaS, freemium | N/A | Best UX; cross-platform sync; smart collections; MCP server | Multiple view modes; duplicate-at-save alerts; custom collection icons | Cloud-only; FTS behind paywall; single-developer risk |
| **Readeck** | Self-hosted, Go binary | ~2K | YouTube transcript extraction; EPUB export; OPDS catalog | EPUB export; OPDS; YouTube transcript indexing; single-binary dist | No AI features at all; bookmarklet-only save |
| **ArchiveBox** | Self-hosted, multi-format archiver | ~22K | Most aggressive archival (HTML/JS/PDF/WARC/screenshot/DOM/media) | Archiver-as-separate-service pattern; WARC format; append-only log | Unbounded Chrome spawning; concurrent file deletion; no organization UX |
| **Linkding** | Self-hosted, minimalist | 10.5K | Sub-second search at 10K+ bookmarks; REST API; SSO | Performance benchmark target; auto-fetch metadata; REST API design | Too minimal; no archival; no AI |
| **Readwise Reader** | SaaS, read-it-later + highlights | N/A | Best highlight/annotation UX; browser extension with web highlights; MCP server | Keyboard-driven reading (H/T/N); annotated doc sharing; 4-color highlights | $9.99/mo; heavy reading-workflow dependency |
| **Burn 451** | Cloud, triage-focused | N/A | 24h auto-expire forces triage; 26-tool MCP server | Time-pressure triage mechanism; MCP-first design; measurable AI quality | Mandatory auto-delete causes data anxiety |
| **Wallabag** | Self-hosted, PHP | ~10K | Mature mobile apps; Pocket import; hosted option | Mobile apps validate mobile is table-stakes | Heavy PHP stack; memory limits on bulk import; aging UI |
| **Shiori** | Self-hosted, Go binary | ~9K | Dual CLI + web mode; single binary; multiple DB backends | Single-binary dist validation; dual CLI+web pattern | No AI; no screenshots; slow development |

### 5.2 Dead Competitors (Market Signals)

| Product | Died | Signal for BOP |
|---------|------|----------------|
| **Pocket** (Mozilla) | July 2025 | Strongest marketing story: "Your bookmarks survive any company's decisions." BOP already has Pocket importer. Target displaced users. |
| **Omnivore** | November 2024 | Acquihired by ElevenLabs. 1 month notice. Cloud-only = total loss. Validates local-first. |

### 5.3 Ecosystem Tools

| Tool | Version | Relevance to BOP |
|------|---------|------------------|
| **FastMCP** | 3.4.0 (June 2026) | Auto-generates JSON Schema from type hints; strict validation; ToolAnnotations. Should replace raw `mcp` SDK. |
| **LanceDB** | 0.33.0 (May 2026) | Hybrid search with pluggable rerankers (RRF, CrossEncoder). Periodic `table.optimize()` needed. 700M vectors proven on single machine. |
| **FastEmbed** | 0.8.0 | ONNX Runtime CPU inference. `bge-small-en-v1.5` (384-dim, 130MB) is the default. `nomic-embed-text` (768-dim, 274MB, 8K context) is better for full-page. |
| **sv-ttk** | Active | Windows 11 Sun Valley theme for ttk. Lightweight, actively maintained. Better than stagnating CustomTkinter. |
| **tksheet** | 7.6.0 | Virtual scrolling for hundreds of millions of cells. Pure Python. Solution for the 10K+ bookmark performance problem. |
| **Nuitka** | 2.8 | Python-to-C compiler. Fewer AV false positives than PyInstaller. 2-4x faster startup. Tkinter plugin. |
| **tufup** | 0.10.0 | TUF-based auto-update. Binary diff patches. Works with PyInstaller or Nuitka. |
| **Ollama** | Latest | `nomic-embed-text` (274MB, 768-dim, 8192 context, MTEB 62.39) for local embedding. OpenAI-compatible API. |

---

## 6. Highest-Value New Features

### 6.1 Browser Extension (MV3) with One-Click Save

**User problem:** Every competitor ships a browser extension. BOP requires opening the app and importing files. Saving a bookmark while browsing requires 5+ steps instead of 1 click.

**Evidence:** Linkwarden, Karakeep, Linkding, Raindrop, Wallabag, Readwise Reader all ship extensions. Competitive research round 1 identifies this as "the single biggest UX gap." Burn 451's MCP server with 26 tools shows the integration depth possible.

**Behavior:** MV3 service worker listens to `chrome.bookmarks.onCreated` for sync. Popup shows URL, auto-suggested tags (from 4,224 pattern rules — no network needed), and category picker. Saves via native messaging to a Python host process on localhost (or via the REST API with auth token).

**Implementation:**
- New directory: `extension/` with `manifest.json`, `popup.html`, `background.js`, `native-messaging-host.py`
- Native messaging host registered in Windows registry (COM-style) or macOS/Linux JSON manifest
- Pattern engine compiled to JSON for the extension popup to do offline tag suggestion
- 1MB native messaging message limit is well within bookmark payload size

**Risks:** Native messaging requires platform-specific host registration. MV3 service workers have 30-second lifetime limits. Chrome Web Store review process.

**Verification:** Install extension in Chrome, save a bookmark, verify it appears in BOP within 2 seconds. Test offline tag suggestions match BOP's pattern engine output.

**Complexity:** L | **Priority:** P1

**ROADMAP status:** Already planned as "Browser live sync via a tiny companion extension (MV3)"

### 6.2 Web Client (FastAPI + HTMX)

**User problem:** BOP is desktop-only. No mobile access, no remote access, no multi-device usage. Every competitor has a web interface.

**Evidence:** Competitive research: "60%+ of web browsing is on mobile. Tools without mobile are quickly abandoned." Linkding, Linkwarden, Karakeep, Readeck, Wallabag all have web UIs.

**Behavior:** FastAPI serves HTMX-driven pages reading the same SQLite/config as the desktop app. Read-only by default; mutating operations require auth token. PWA manifest for mobile install. Share-intent target on Android.

**Implementation:**
- `bookmark_organizer_pro/web/` package with FastAPI app
- Templates in `web/templates/` using Jinja2 + HTMX
- Reuses BookmarkManager, TagManager, CategoryManager, SearchEngine
- `python -m bookmark_organizer_pro.web` entry point
- PWA manifest + service worker for offline read access

**Risks:** SQLite concurrent access from Tkinter + FastAPI processes. Solution: WAL mode + read-only for web by default.

**Verification:** Start web server, open in mobile browser, search bookmarks, verify results match desktop.

**Complexity:** XL | **Priority:** P1

**ROADMAP status:** Already planned as "Web client — FastAPI + HTMX frontend"

### 6.3 Smart Collections with Auto-Matching Rules

**User problem:** Static categories require manual assignment. Users want dynamic collections that auto-populate based on rules (tag, keyword, URL pattern, date range).

**Evidence:** Raindrop.io's Smart Collections and Readeck's auto-matching rules are cited as standout features in both competitive research rounds. NL-to-structured-query already generates `StructuredQuery` objects that could power this.

**Behavior:** User defines a SmartCollection with filter criteria (tags, categories, domains, date ranges, content types, keywords). The collection auto-updates on every bookmark add/import. Displayed alongside static categories in the sidebar.

**Implementation:**
- New model: `SmartCollection(name, filters: StructuredQuery, icon, created_at)`
- Stored in `~/.bookmark_organizer/smart_collections.json`
- `services/nl_query.py` `execute_query()` already implements the filtering logic
- Sidebar shows smart collections with a distinct icon (auto-updating badge count)
- CLI: `smart-collection create "Recent Rust" --tags rust --after 2026-01-01`

**Risks:** Performance for many smart collections on large libraries — cache filter results with dirty-flag invalidation.

**Verification:** Create a smart collection "Python articles from last 30 days." Add a new Python bookmark. Verify it appears in the collection without manual assignment.

**Complexity:** M | **Priority:** P2

**ROADMAP status:** Net-new discovery.

### 6.4 Reader View with Highlight and Annotation

**User problem:** BOP captures snapshots but has no way to read, highlight, or annotate saved content. Linkwarden, Readwise, and Readeck all offer this.

**Evidence:** Competitive research identifies "No annotation/highlighting on saved content" as a feature gap. Omnivore's Obsidian sync of highlights was its killer feature.

**Behavior:** Open a bookmark's extracted text or snapshot in a reader view (simplified HTML). Select text to highlight (4 colors). Add per-highlight notes. Highlights stored in bookmark metadata. Highlights are searchable and exportable to Markdown.

**Implementation:**
- New widget: `ui/reader_view.py` using `tkinter.Text` with tag-based highlighting
- Highlight model: `Highlight(id, bookmark_id, text, note, color, char_start, char_end, created_at)`
- Stored in bookmark's `custom_data` dict or separate `highlights.json`
- Export: `highlight.to_markdown()` -> `> highlighted text\n\n*Note: user note*`

**Risks:** Tkinter Text widget is limited for rich HTML rendering. May need `tkinterweb` or defer to the web client.

**Verification:** Open a snapshot, highlight a paragraph, add a note. Close and reopen — highlight persists. Export to Markdown.

**Complexity:** L | **Priority:** P2

**ROADMAP status:** Net-new discovery. Related to existing "Reading-progress persistence" item.

### 6.5 EPUB Export of Collections

**User problem:** No way to read bookmark collections offline on e-readers. Readeck exports to EPUB + OPDS.

**Evidence:** Competitive research: "Readeck exports articles and collections as EPUB e-books, with OPDS catalog support for e-readers." Already in ROADMAP Nice-to-Haves.

**Behavior:** Select a collection or tag -> Export as EPUB. Each bookmark becomes a chapter with extracted text. Table of contents generated from bookmark titles. Cover page shows collection name and date range.

**Implementation:**
- Use `ebooklib` (Python EPUB library) or manual ZIP-based EPUB construction
- CLI: `epub-export --tag rust --output rust-articles.epub`
- GUI: Export menu -> EPUB option
- Reuse extracted text from `services/ingest.py`

**Risks:** Extracted text quality depends on trafilatura. Missing text falls back to title + URL.

**Verification:** Export a 10-bookmark collection as EPUB. Open in Calibre. Verify TOC, chapter content, metadata.

**Complexity:** M | **Priority:** P2

**ROADMAP status:** Already in Nice-to-Haves as "EPUB export of a collection for Kobo/Kindle sideload"

### 6.6 YouTube Transcript Capture and Indexing

**User problem:** Video bookmarks are opaque — only title and URL are searchable. Readeck extracts YouTube transcripts and makes them text-searchable.

**Evidence:** Competitive research: "combined with BOP's semantic search and RAG, you could ask 'what did that conference talk say about distributed consensus?' and get answers from video bookmarks."

**Behavior:** On save, detect YouTube URLs. Fetch transcript via `yt-dlp --write-auto-sub --skip-download`. Store transcript as extracted text. Embed for semantic search. RAG can answer questions from video content.

**Implementation:**
- Extend `services/ingest.py` to detect `youtube.com`/`youtu.be` URLs
- Shell out to `yt-dlp --write-auto-sub --sub-lang en --skip-download --print-to-file subtitle <path> <url>`
- Parse VTT/SRT to plain text, store in `extracted_text`
- Feed into embedding pipeline like article text

**Risks:** yt-dlp version compatibility. Not all videos have transcripts. Rate limiting by YouTube.

**Verification:** Save a YouTube URL with auto-captions. Run `hybrid "topic mentioned in video"`. Verify video bookmark appears in results.

**Complexity:** M | **Priority:** P2

**ROADMAP status:** Already in Nice-to-Haves as "YouTube-video metadata + transcript capture via yt-dlp"

### 6.7 Duplicate-at-Save-Time Detection

**User problem:** Raindrop alerts users when saving an already-bookmarked page. BOP's duplicate detector runs as a batch tool, not at save time.

**Evidence:** Competitive research: "No duplicate-at-save-time detection in the browser flow: Raindrop alerts users when they are about to save an already-bookmarked page."

**Behavior:** When adding a bookmark via GUI, CLI, MCP, or API, immediately check if the normalized URL already exists. Show the existing bookmark with a "View existing / Add anyway / Update existing" dialog.

**Implementation:**
- `BookmarkManager.find_by_url(url)` already exists via `find_duplicates` / URL normalization
- Add `BookmarkManager.get_existing(url) -> Optional[Bookmark]` using the normalized URL index
- GUI: show dialog before add. CLI: print warning. MCP: return `{"already_exists": true, "existing": {...}}`.
- Browser extension popup shows "Already saved" indicator

**Risks:** Normalization may produce false positives (http vs https). Use the `add_bookmark_clean` path which already handles this.

**Verification:** Add a bookmark. Try to add the same URL with different tracking params. Verify duplicate alert.

**Complexity:** S | **Priority:** P2

**ROADMAP status:** Net-new discovery.

### 6.8 Obsidian Vault Sync via MCP

**User problem:** PKM users (Obsidian, Logseq) want bookmarks and highlights synced to their knowledge vault. Omnivore's killer feature was this integration.

**Evidence:** Competitive research: "Rather than building a custom Obsidian plugin, BOP can sync to Obsidian vaults through the MCP server + a simple Claude Desktop workflow."

**Behavior:** New MCP tool `export_to_obsidian(vault_path, format)` writes bookmarks as Markdown files with YAML frontmatter (URL, tags, category, created, highlights). One file per bookmark. Bidirectional sync possible via Claude Desktop workflow.

**Implementation:**
- New MCP tool: `export_to_obsidian(vault_path, tag_filter, category_filter, since)`
- Markdown template: YAML frontmatter + extracted text + highlights
- CLI: `obsidian-export --vault ~/Notes --since 2026-06-01`
- Could also be a standalone script triggered by cron

**Risks:** Obsidian vault structure varies by user. Frontmatter format must be configurable. Bidirectional sync is complex.

**Verification:** Export 5 bookmarks to an Obsidian vault. Open in Obsidian. Verify frontmatter, links, tags render correctly.

**Complexity:** M | **Priority:** P3

**ROADMAP status:** Net-new discovery.

---

## 7. Existing Feature Improvements

### 7.1 AI Batch Processor — Fix Critical Runtime Crashes

**Current behavior:** `AIBatchProcessor._worker` accesses `self.ai_config.settings` (line 90) and calls `self._client.categorize_bookmark()` (line 183). Neither exists.

**Problem:** Every invocation of the batch AI processor crashes with AttributeError. The entire AI batch categorization feature path is dead code.

**Recommended change:**
- Line 90: Replace `self.ai_config.settings.get("batch_size", 5)` with `self.ai_config.get_batch_size()` (if method exists) or access `self.ai_config._config.get("batch_size", 5)`.
- Line 94: Replace `self.ai_config.settings.get("rate_limit_delay", 1.0)` with `60.0 / self.ai_config.get_rate_limit()`.
- Line 183: Replace `self._client.categorize_bookmark(bookmark.url, bookmark.title, [])` with `self._client.categorize_bookmarks([{"url": bookmark.url, "title": bookmark.title}], categories)`.
- Line 257 (AITagSuggester): Same fix for `categorize_bookmark`.
- Line 200-201: Replace `except Exception: pass` with `except Exception as e: log.warning(f"AI processing failed for {bookmark.url}: {e}")`.

**Code locations:** `bookmark_organizer_pro/services/ai_tools.py` lines 90, 94, 183, 200-201, 257. `bookmark_organizer_pro/ai.py` for reference API.

**Backward compat:** Fixes broken code; no backward compat concern.

**Verification:** Run AI batch categorization on 10 bookmarks. Verify categories and tags are applied. Check log for errors.

**Complexity:** S | **Priority:** P0 | **Status:** Verified bug (code inspection).

### 7.2 Embedding Chunk Overlap — Fix Infinite Loop Risk

**Current behavior:** `EmbeddingService.chunk_text()` line 182: `start = max(end - overlap, end)` always evaluates to `end` because `end - overlap < end`.

**Problem:** Zero overlap between chunks degrades RAG/citation quality. If sentence-boundary search pushes `end` backward to `<= start`, the function infinite-loops.

**Recommended change:**
```python
# Line 182: was: start = max(end - overlap, end)
start = end - overlap
# Also add after line 170 (sentence boundary search):
end = max(end, start + 1)  # Prevent backward/no-progress
```

**Code locations:** `bookmark_organizer_pro/services/embeddings.py` line 182, line 170.

**Backward compat:** Changes chunk boundaries — existing embeddings should be re-generated.

**Verification:** Call `chunk_text("A" * 3000, chunk_size=1000, overlap=200)`. Verify chunks[1] starts 200 chars before chunks[0] ends. Verify no infinite loop on edge cases.

**Complexity:** S | **Priority:** P0 | **Status:** Verified bug (code inspection).

### 7.3 MCP Server — Add Typed Tool Schemas

**Current behavior:** All 15 tools registered with `inputSchema={"type": "object", "additionalProperties": True}`.

**Problem:** MCP clients (Claude Desktop, Cursor) have zero information about expected parameters. LLM must guess arguments, leading to runtime TypeErrors.

**Recommended change:** Migrate to FastMCP 3.x which auto-generates JSON Schema from Python type hints and docstrings. Example:
```python
from fastmcp import FastMCP
app = FastMCP("bookmark-organizer-pro")

@app.tool()
def list_bookmarks(limit: int = 50, offset: int = 0, category: str | None = None, tag: str | None = None, read_later_only: bool = False) -> list[dict]:
    """List bookmarks with optional filtering."""
    ...
```
Or manually define schemas with `properties`, `required`, `type`, `description` for each of the 15 tools.

**Code locations:** `bookmark_organizer_pro/mcp_server.py` line 335 (schema registration), lines 114-298 (tool function signatures).

**Backward compat:** MCP protocol compatible. Clients get better schemas. No breaking change.

**Verification:** Start MCP server. Connect via Claude Desktop. Ask "list my bookmarks about Python" — verify Claude correctly passes `category` or `tag` parameters.

**Complexity:** M | **Priority:** P0 | **Status:** Verified gap (code inspection).

### 7.4 PyInstaller Spec — Add v6.0 Hidden Imports

**Current behavior:** `packaging/bookmark_organizer.spec` hidden_imports only covers tkinter + PIL + bs4 + requests + pystray. Zero v6.0 modules.

**Problem:** The distributed .exe binary cannot use any v6 feature (embeddings, encryption, MCP, RSS, snapshots, etc.) because PyInstaller's static analysis misses lazy imports.

**Recommended change:** Add to hidden_imports:
```python
# v6.0.0 service modules
'bookmark_organizer_pro.services',
'bookmark_organizer_pro.services.embeddings',
'bookmark_organizer_pro.services.ingest',
'bookmark_organizer_pro.services.vector_store',
'bookmark_organizer_pro.services.encryption',
'bookmark_organizer_pro.services.hybrid_search',
'bookmark_organizer_pro.services.rag_chat',
'bookmark_organizer_pro.services.citation_summarizer',
'bookmark_organizer_pro.services.rss_feeds',
'bookmark_organizer_pro.services.flows',
'bookmark_organizer_pro.services.snapshot',
'bookmark_organizer_pro.services.dead_link_scanner',
'bookmark_organizer_pro.services.digest',
'bookmark_organizer_pro.services.tag_linter',
'bookmark_organizer_pro.services.dup_hybrid',
'bookmark_organizer_pro.services.zip_export',
'bookmark_organizer_pro.services.read_later',
'bookmark_organizer_pro.services.nl_query',
# Optional libraries
'trafilatura',
'fastembed',
'lancedb',
'cryptography',
'mcp',
```

**Code locations:** `packaging/bookmark_organizer.spec` lines 42-80.

**Backward compat:** Increases binary size. No functional regression.

**Verification:** Build with updated spec. Run .exe. Execute `embed` and `encrypt` commands. Verify no ModuleNotFoundError.

**Complexity:** M | **Priority:** P0 | **Status:** Verified gap (code inspection).

### 7.5 Main Thread Blocking — Move Network Calls to Background Threads

**Current behavior:** `_ai_suggest_tags`, `_ai_summarize`, `_ai_improve_titles` (ai_enrichment.py, ai_titles.py) and `_check_all_links` (tools.py) perform synchronous HTTP on the main Tkinter thread.

**Problem:** UI freezes for seconds to minutes during these operations.

**Recommended change:** Use `threading.Thread(daemon=True)` + `root.after(0, callback)` pattern already used by `_import_from_browser`. Or use the existing `NonBlockingTaskRunner`.

**Code locations:**
- `bookmark_organizer_pro/app_mixins/ai_enrichment.py` lines 36, 105, 124-162
- `bookmark_organizer_pro/app_mixins/ai_titles.py` lines 47, 82-120
- `bookmark_organizer_pro/app_mixins/tools.py` lines 294-351

**Backward compat:** Functional behavior unchanged. UI responsiveness improved.

**Verification:** Start AI tag suggestion on 20 bookmarks. Verify the UI remains responsive (can scroll, search, resize) during processing.

**Complexity:** M | **Priority:** P1 | **Status:** Verified (code inspection).

### 7.6 AI Enrichment/Titles — Use Provider Abstraction Layer

**Current behavior:** `_ai_summarize` and `_ai_improve_titles` contain full provider switch/case blocks directly calling provider-specific internals.

**Problem:** Duplicates `AIClient.complete()` abstraction. Will break when new providers added.

**Recommended change:** Replace the provider switch blocks with `client.complete(prompt, system, max_tokens, temperature)`.

**Code locations:**
- `bookmark_organizer_pro/app_mixins/ai_enrichment.py` lines 124-162
- `bookmark_organizer_pro/app_mixins/ai_titles.py` lines 82-120

**Backward compat:** Same functional behavior through the abstraction layer.

**Verification:** Test summarize and title improvement with each of the 5 providers.

**Complexity:** M | **Priority:** P1 | **Status:** Verified (code inspection).

### 7.7 Cost Tracker — Update Stale Pricing Table

**Current behavior:** `AICostTracker.COSTS` (ai_tools.py lines 443-464) lists deprecated models (gpt-4, claude-3-opus, gemini-pro, llama2-70b) but none of the default models.

**Problem:** All cost tracking reports $0.00 for every cloud provider. Feature is non-functional.

**Recommended change:** Update to current models:
```python
COSTS = {
    'openai': {
        'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
        'gpt-4o': {'input': 2.50, 'output': 10.00},
        'default': {'input': 0.15, 'output': 0.60},
    },
    'anthropic': {
        'claude-sonnet-4-20250514': {'input': 3.00, 'output': 15.00},
        'default': {'input': 3.00, 'output': 15.00},
    },
    # ... etc
}
```

**Code locations:** `bookmark_organizer_pro/services/ai_tools.py` lines 443-464.

**Complexity:** S | **Priority:** P1 | **Status:** Verified (code inspection).

### 7.8 Treeview Virtualization

**Current behavior:** `_populate_list_view` (bookmarks.py line 133) deletes all items and re-inserts every bookmark on each refresh, including the 30-second polling timer.

**Problem:** Multi-second freezes at 10K+ bookmarks. Every filter change, search, and analytics poll triggers full rebuild.

**Recommended change:** Options (in order of preference):
1. **tksheet** (pure Python, virtual scrolling, handles millions of cells)
2. Canvas-based custom virtual list rendering only visible rows
3. Pagination (least preferred, changes UX)

Also: separate `_refresh_analytics` from `_refresh_bookmark_list` in the polling loop.

**Code locations:**
- `bookmark_organizer_pro/app_mixins/bookmarks.py` lines 133-193, 207-209, 233-235
- `bookmark_organizer_pro/app_mixins/lifecycle.py` lines 42, 98, 103

**Complexity:** L | **Priority:** P1

**ROADMAP status:** Already planned as "Virtualized list"

### 7.9 Link Checker — Add Per-Domain Rate Limiting

**Current behavior:** `LinkChecker` fires up to 10+ concurrent requests to the same domain with no delay, no robots.txt, generic User-Agent.

**Problem:** IP bans, WAF blocks, potential ToS violations.

**Recommended change:**
```python
# Per-domain semaphore with 1-second delay
from collections import defaultdict
import asyncio
_domain_semaphores = defaultdict(lambda: asyncio.Semaphore(2))
_domain_last_request = defaultdict(float)
```
Set User-Agent to `BookmarkOrganizerPro/6.0 LinkChecker`.

**Code locations:** `bookmark_organizer_pro/link_checker.py` lines 17, 50-55, 87.

**Complexity:** M | **Priority:** P1 | **Status:** Verified (code inspection).

### 7.10 Log Rotation

**Current behavior:** `logging.FileHandler` with no rotation. DEBUG level. Grows unbounded.

**Problem:** After months of use, log file can reach hundreds of MB.

**Recommended change:** Replace with `RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3)`.

**Code locations:** `bookmark_organizer_pro/logging_config.py` line 37.

**Complexity:** S | **Priority:** P1 | **Status:** Verified (code inspection).

---

## 8. Reliability, Security, Privacy, and Data Safety

### 8.1 Critical Reliability Issues

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| AIBatchProcessor crashes: `.settings` attr, `categorize_bookmark` method | Critical | `services/ai_tools.py:90,183,257` | Verified |
| Chunk overlap infinite loop risk | High | `services/embeddings.py:182` | Verified |
| `batch_refresh_metadata` mutates bookmarks from worker threads without lock | High | `managers/bookmarks.py:571-585` | Verified |
| Dead-link scanner mutates bookmarks from threads without lock | High | `services/dead_link_scanner.py:93-96`, `link_checker.py:135-141` | Verified |
| VectorStore non-atomic write -> data loss on crash | High | `services/vector_store.py:219-226` | Verified |
| Link checker no rate limiting -> IP bans | High | `link_checker.py:17,50-55` | Verified |

### 8.2 Security Issues

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| Prompt injection via unsanitized bookmark data in LLM prompts | High | `ai.py:473`, `citation_summarizer.py:104`, `rag_chat.py:88`, `nl_query.py:78` | Verified |
| RSS parser vulnerable to XML bomb (stdlib ET) | Medium | `services/rss_feeds.py:150` | Verified |
| Snapshot banner HTML injection via unescaped URL | Medium | `services/snapshot.py:182-184` | Verified |
| Web archive injects raw page content without sanitization | Medium | `services/web_tools.py:253` | Verified |
| API server has no auth or CORS protection | Medium | `services/api.py:255` | Verified |
| API keys stored plaintext, no protection on Windows | Medium | `ai.py:211-214` | Verified |
| No SSRF protection on Ollama URL | Medium | `ai.py:197-199` | Verified |
| `ensure_package` auto-installs pip packages at runtime | Medium | `ai.py:29-32` | Verified |
| Runtime pip install in DependencyCheckDialog | Medium | `ui/dependencies.py:190-197` | Verified |
| PatternEngine regex has no ReDoS timeout | Medium | `core/pattern_engine.py:52-56` | Verified |
| Screenshot capture sends URLs to thum.io without disclosure | Low | `services/web_tools.py:521-524` | Verified |

### 8.3 Data Safety Issues

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| VectorStore non-atomic write | High | `services/vector_store.py:219-226` | Verified |
| Dead-link scanner non-atomic write | Medium | `services/dead_link_scanner.py:166-168` | Verified |
| `decrypt_file` can overwrite unrelated files | Medium | `services/encryption.py:107-108` | Verified |
| `restore_backup` does not create pre-restore backup | Medium | `core/storage_manager.py:149` | Verified |
| `save_bookmarks` lock race with `storage.save()` | Medium | `managers/bookmarks.py:117-120` | Verified |
| TagManager has no thread safety | Medium | `managers/tags.py` (entire class) | Verified |
| No database size limit — JSON grows unbounded | Medium | `core/storage_manager.py:31-59` | Verified |
| URL normalization silently upgrades HTTP->HTTPS | Medium | `utils/url.py:97-98` | Verified |
| Importers no intra-file dedup | Medium | `importers.py`, `importers_extra.py` | Verified |

### 8.4 Privacy Issues

| Issue | File | Recommendation |
|-------|------|----------------|
| thum.io receives private bookmark URLs | `services/web_tools.py:521-524` | Make opt-in with disclosure |
| Ollama URL can be pointed at arbitrary hosts (SSRF) | `ai.py:197-199` | Restrict to localhost by default |
| API keys plaintext on Windows | `ai.py:211-214` | Use keyring library or DPAPI |

---

## 9. UX, Accessibility, and Trust

### 9.1 UX Issues

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| No list virtualization — freezes past 10K bookmarks | High | `app_mixins/bookmarks.py:133-193` | Verified |
| Main thread blocked by AI network calls | High | `app_mixins/ai_enrichment.py`, `ai_titles.py` | Verified |
| Main thread blocked by link checking | High | `app_mixins/tools.py:294-351` | Verified |
| Analytics refresh destroys/recreates all widgets every 30s | Medium | `app_mixins/dashboard.py:199-200` | Verified |
| Theme live-refresh is lossy (sidebar colors, ttk, menus) | Medium | `app_mixins/themes.py:38-39` | Verified |
| Single-bookmark delete has no confirmation | Medium | `app_mixins/bookmark_crud.py:108-112` | Verified |
| Command palette closes on FocusOut to own children | Medium | `ui/shell_widgets.py:398` | Verified |
| Drag-and-drop file import is a no-op stub | Medium | `app_mixins/lifecycle.py:84-88` | Verified |
| Rename category dialog missing window chrome/centering | Low | `app_mixins/categories.py:200-246` | Verified |

### 9.2 Accessibility Issues

| Issue | Severity | File |
|-------|----------|------|
| No keyboard focus for treeview, no tab order defined | Medium | `app_mixins/app_shell.py:412-416` |
| Column headers mouse-click-only for sorting | Medium | `ui/treeview.py:31` |
| No high-contrast theme, no WCAG AA validation | Medium | All themes |
| No screen reader labels on major sections | Medium | `app_mixins/app_shell.py` |

### 9.3 Trust Issues

| Issue | Impact |
|-------|--------|
| RAG chat does not validate hallucinated citations | LLM may output `[#c99]` when only 6 chunks exist |
| Cost tracker reports $0.00 for all cloud providers | Users cannot track spending |
| Health score calculated 3 different ways with different formulas | Inconsistent scores confuse users |
| 6+ copy-pasted model docstrings on widget classes | Misleads developers and IDE tooltips |

---

## 10. Architecture and Maintainability

### 10.1 Dead Code

| Dead Code | Lines | File |
|-----------|-------|------|
| GridView + BookmarkCard + ViewMode.GRID | ~350 | `ui/widget_grid.py`, `ui/shell_widgets.py` |
| BookmarkListView + CategorySidebar | ~450 | `ui/widget_lists.py` |
| MiniAnalyticsDashboard | ~150 | `ui/components.py` |
| 3 system tray implementations (none wired up) | ~300 | `ui/widget_tray.py`, `ui/shell_widgets.py` |
| CategoryDragDropManager (broken import, never instantiated) | ~60 | `ui/drag_drop.py` |
| `bg_color = color + "26"` (invalid Tk alpha, never used) | 1 | `ui/widget_controls.py:468` |
| `tag_linter.py` line 92 no-op expression | 1 | `services/tag_linter.py:92` |
| `_extract_text` conditional `'html_module' in dir()` always False | 1 | `services/web_tools.py:444` |
| **Total estimated dead code** | **~1,300 lines** | |

### 10.2 Architectural Concerns

| Concern | Description | File |
|---------|-------------|------|
| Constants module creates 10 directories at import time | Side effects on `import bookmark_organizer_pro` | `constants.py:19-52` |
| No pyproject.toml `[project]` — not installable as package | `pip install -e .` fails | `pyproject.toml` |
| No Python version lower bound declared | Uses 3.10+ features | `pyproject.toml`, `requirements.txt` |
| Dependencies not pinned to upper bounds | Breaking releases auto-installed | `requirements.txt` |
| CI builds only on Python 3.12, no matrix | Compatibility issues hidden | `.github/workflows/build.yml:24` |
| CI does not create release before uploading | `gh release upload` fails if release doesn't exist | `.github/workflows/build.yml:59-62` |
| 142 tests for ~35K LoC, zero v6.0 service tests | Critical code paths untested | `tests/test_core.py` |
| MCP server eagerly imports all services | Crashes if optional deps missing | `mcp_server.py:36-49` |
| Duplicate health score formulas (3 locations) | Inconsistent results | `dashboard.py`, `components.py`, `widget_analytics.py` |
| Favicon images accumulate without bounds | Memory leak | `ui/treeview.py:27-28` |

### 10.3 Recommendations

1. **Move directory creation to `ensure_directories()`** function called only from entry points (`launcher.py`, `mcp_server.py`). Keep Path constants as pure values.
2. **Add `[project]` and `[build-system]` to pyproject.toml** with `python_requires = ">=3.10"`, dependency groups, and entry points.
3. **Pin dependency upper bounds** for packages with unstable APIs: `fastembed>=0.4,<1.0`, `lancedb>=0.13,<1.0`, `mcp>=1.0,<2.0`.
4. **Add `gh release create` step** before matrix build jobs in CI.
5. **Extract health score** to a single function in `utils/health.py`.
6. **Add LRU cache or clear_images()** to SortableTreeview._favicon_images.
7. **Remove ~1,300 lines of dead code** (GridView, unused widgets, broken tray implementations).

---

## 11. Prioritized Roadmap

### P0 — Must-fix before next release (blocks core functionality)

- [ ] **BOP-001**: Fix AIBatchProcessor `.settings` AttributeError and `categorize_bookmark` AttributeError
  - Why: Every AI batch/tag path crashes at runtime — the entire feature is dead code.
  - Evidence: Code audit AI layer (verified via code inspection of `services/ai_tools.py`)
  - Touches: `services/ai_tools.py:90,94,183,200-201,257`, `ai.py` (reference API)
  - Acceptance: AI batch categorization completes without crash on 10+ bookmarks
  - Verify: Run batch categorize; check logs for applied categories

- [ ] **BOP-002**: Fix chunk overlap infinite-loop: `start = max(end-overlap, end)` -> `start = end - overlap` + end-backward guard
  - Why: Zero chunk overlap degrades RAG/citation quality; edge inputs can infinite-loop.
  - Evidence: Code audit services layer (verified: `max(end-overlap, end)` always returns `end`)
  - Touches: `services/embeddings.py:170,182`
  - Acceptance: `chunk_text("A"*3000, 1000, 200)` produces overlapping chunks; no infinite loop on edge inputs
  - Verify: Unit test with various chunk/overlap/text combinations

- [ ] **BOP-003**: Add typed JSON Schema to all 15 MCP tools (migrate to FastMCP 3.x or manual schemas)
  - Why: AI agents can't discover parameters — every call is a guess-and-crash.
  - Evidence: Code audit infrastructure (verified: all tools use `{"type": "object", "additionalProperties": True}`)
  - Touches: `mcp_server.py:335` (schema registration), lines 114-298 (functions), `requirements.txt`
  - Acceptance: Claude Desktop correctly infers parameters for `list_bookmarks`, `search_bookmarks`, `add_bookmark`
  - Verify: MCP inspector shows typed schemas; Claude passes correct args

- [ ] **BOP-004**: Update PyInstaller spec with v6.0 hidden imports (all services/* + optional libs)
  - Why: Shipped .exe cannot use any v6 feature — binary is fundamentally broken for new features.
  - Evidence: Code audit infrastructure (verified: zero v6 modules in hidden_imports)
  - Touches: `packaging/bookmark_organizer.spec:42-80`
  - Acceptance: Built .exe can run `embed`, `encrypt`, `snapshot`, `mcp-server` without ModuleNotFoundError
  - Verify: Build on CI; run each v6 subcommand

- [ ] **BOP-005**: Add `gh release create` step before matrix upload in CI
  - Why: Tag push fails to upload artifacts because release doesn't exist yet.
  - Evidence: Code audit infrastructure (verified: `build.yml` uploads without creating release)
  - Touches: `.github/workflows/build.yml`
  - Acceptance: Tag push creates release + uploads all 3 platform binaries
  - Verify: Push a test tag; verify release page has 3 artifacts

### P1 — High impact (significantly improves user experience or safety)

- [ ] **BOP-006**: Move AI network calls (suggest_tags, summarize, improve_titles) to background threads
  - Why: UI freezes for seconds to minutes during AI operations.
  - Evidence: Code audit UI layer (verified: synchronous HTTP on main Tkinter thread)
  - Touches: `app_mixins/ai_enrichment.py:36,105,124-162`, `app_mixins/ai_titles.py:47,82-120`
  - Acceptance: UI stays responsive during AI operations
  - Verify: Start AI summarize on 20 bookmarks; scroll and search simultaneously

- [ ] **BOP-007**: Move link checking HTTP requests to background thread
  - Why: Link check on 100+ bookmarks freezes UI for minutes.
  - Evidence: Code audit UI layer (verified: synchronous HTTP in tools.py)
  - Touches: `app_mixins/tools.py:294-351`
  - Acceptance: Link check runs without freezing UI
  - Verify: Check 100 bookmarks; UI stays responsive

- [ ] **BOP-008**: Add per-domain rate limiting to LinkChecker (max 2 concurrent/domain, 1s delay)
  - Why: Aggressive concurrent requests cause IP bans and WAF blocks.
  - Evidence: Code audit core data layer (verified: 10+ concurrent to same domain)
  - Touches: `link_checker.py:17,50-55,87`
  - Acceptance: No more than 2 concurrent requests to the same domain; honest User-Agent
  - Verify: Check 50 bookmarks from same domain; verify 1s delays in logs

- [ ] **BOP-009**: Fix `batch_refresh_metadata` thread safety — collect results, apply under lock
  - Why: Concurrent bookmark mutation from worker threads causes data corruption.
  - Evidence: Code audit core data layer (verified: direct mutation in workers)
  - Touches: `managers/bookmarks.py:571-585`
  - Acceptance: No concurrent bookmark mutation
  - Verify: Refresh metadata on 100 bookmarks; no data corruption

- [ ] **BOP-010**: Fix dead-link scanner thread safety — return data from workers, apply under lock
  - Why: Same thread-safety issue as BOP-009 but in dead-link scanner.
  - Evidence: Code audit services layer (verified: concurrent mutation without lock)
  - Touches: `services/dead_link_scanner.py:93-96`, `link_checker.py:135-141`
  - Acceptance: No concurrent bookmark object mutation
  - Verify: Scan 100 bookmarks; check all results persisted correctly

- [ ] **BOP-011**: Atomic writes for VectorStore and DeadLinkScanner
  - Why: Crash during write loses all vector data / dead-link results.
  - Evidence: Code audit services layer (verified: non-atomic JSON writes)
  - Touches: `services/vector_store.py:219-226`, `services/dead_link_scanner.py:166-168`
  - Acceptance: Kill process during write; restart; data intact
  - Verify: Write loop + kill test

- [ ] **BOP-012**: Add log rotation (RotatingFileHandler, 5MB, 3 backups)
  - Why: Log file grows unbounded, can reach hundreds of MB.
  - Evidence: Code audit infrastructure (verified: FileHandler with no rotation)
  - Touches: `logging_config.py:37`
  - Acceptance: Log file never exceeds ~5MB; old logs rotated
  - Verify: Write 10MB of log data; verify rotation

- [ ] **BOP-013**: Update AICostTracker pricing to current models
  - Why: Cost tracker reports $0.00 for all cloud providers — feature is non-functional.
  - Evidence: Code audit AI layer (verified: stale pricing table)
  - Touches: `services/ai_tools.py:443-464`
  - Acceptance: Cost tracker reports non-zero costs for default models
  - Verify: Run 10 categorizations; check cost report > $0

- [ ] **BOP-014**: Fix AI enrichment/titles to use `client.complete()` instead of provider switch
  - Why: Duplicated provider logic breaks when new providers added.
  - Evidence: Code audit AI layer (verified: full switch blocks bypass abstraction)
  - Touches: `app_mixins/ai_enrichment.py:124-162`, `app_mixins/ai_titles.py:82-120`
  - Acceptance: Summarize and title improvement work identically through abstraction
  - Verify: Test with each of 5 providers

- [ ] **BOP-015**: Add API server auth token + CORS deny headers
  - Why: Any local process or webpage can read/create/delete bookmarks.
  - Evidence: Code audit services layer (verified: no auth, no CORS)
  - Touches: `services/api.py:255`
  - Acceptance: Unauthenticated requests get 401; cross-origin requests blocked
  - Verify: curl without token -> 401; browser JS from different origin -> blocked

- [ ] **BOP-016**: Separate `_refresh_analytics` from `_refresh_bookmark_list` in polling loop
  - Why: Analytics poll triggers full bookmark list rebuild every 30s, causing freezes.
  - Evidence: Code audit UI layer (verified: coupled refresh)
  - Touches: `app_mixins/lifecycle.py:98,103`, `app_mixins/dashboard.py:199-200`
  - Acceptance: Analytics poll does not trigger full bookmark list rebuild
  - Verify: Add 10K bookmarks; verify 30s poll does not freeze UI

- [ ] **BOP-017**: Use `defusedxml.ElementTree.fromstring()` for RSS parsing
  - Why: Stdlib ET is vulnerable to XML bomb attacks on untrusted feeds.
  - Evidence: Code audit services layer (verified: stdlib ET on network input)
  - Touches: `services/rss_feeds.py:150`, `requirements.txt`
  - Acceptance: XML bomb input raises exception instead of consuming memory
  - Verify: Feed with billion-laughs entity -> clean rejection

- [ ] **BOP-018**: Add `html.escape(url, quote=True)` to snapshot banner
  - Why: HTML injection via crafted URLs in snapshot banner.
  - Evidence: Code audit services layer (verified: unescaped f-string)
  - Touches: `services/snapshot.py:182-184`
  - Acceptance: URL with `"><script>` in snapshot produces escaped HTML
  - Verify: Snapshot a URL containing HTML; view source; no unescaped tags

- [ ] **BOP-019**: Implement list virtualization (tksheet or canvas-based)
  - Why: Treeview chokes past ~10K rows; multi-second freezes on every refresh.
  - Evidence: Code audit UI layer + ROADMAP (already planned)
  - Touches: `app_mixins/bookmarks.py:133-193`
  - Acceptance: 50K bookmarks render in <1 second; scroll is smooth
  - Verify: Load 50K bookmarks; measure render time; scroll test

- [ ] **BOP-020**: Add `pyproject.toml` `[project]` table with metadata, deps, entry points, python_requires
  - Why: Project not installable via pip; no Python version constraint declared.
  - Evidence: Code audit infrastructure (verified: bare pyproject.toml)
  - Touches: `pyproject.toml`
  - Acceptance: `pip install -e .` works; `pip install .[ai]` installs optional AI deps
  - Verify: Fresh venv; pip install -e .; run main.py

### P2 — Medium impact (competitive parity, quality of life)

- [ ] **BOP-021**: Browser extension (MV3) with one-click save + offline tag suggestions
  - Why: Single biggest UX gap vs every competitor.
  - Evidence: Competitive research (all major competitors ship extensions)
  - Touches: New `extension/` directory
  - Acceptance: Save bookmark from Chrome popup; appears in BOP within 2s
  - Verify: Install in Chrome; save; verify in BOP

- [ ] **BOP-022**: Web client (FastAPI + HTMX) with PWA
  - Why: No mobile/remote access; every competitor has web UI.
  - Evidence: Competitive research (Linkding, Linkwarden, Karakeep, Readeck, Wallabag)
  - Touches: New `bookmark_organizer_pro/web/` package
  - Acceptance: Search bookmarks from mobile browser
  - Verify: Start web server; open on phone; search and verify results

- [ ] **BOP-023**: Smart Collections with auto-matching rules
  - Why: Static categories require manual assignment; users want dynamic collections.
  - Evidence: Competitive research (Raindrop.io Smart Collections, Readeck auto-matching)
  - Touches: New model + `services/` + sidebar widget
  - Acceptance: Create smart collection; add matching bookmark; auto-appears
  - Verify: Manual test with filter criteria

- [ ] **BOP-024**: Duplicate-at-save-time detection
  - Why: Raindrop alerts on duplicate save; BOP only detects duplicates in batch.
  - Evidence: Competitive research net-new discovery
  - Touches: `managers/bookmarks.py`, `app_mixins/bookmark_crud.py`, `mcp_server.py`
  - Acceptance: Adding existing URL shows "already saved" with options
  - Verify: Add same URL twice; verify alert

- [ ] **BOP-025**: Headless Chromium snapshot fallback via playwright
  - Why: JS-heavy SPAs produce empty shells with monolith.
  - Evidence: ROADMAP (already planned)
  - Touches: `services/snapshot.py`
  - Acceptance: Twitter/X bookmark produces readable snapshot
  - Verify: Snapshot a React SPA; verify content captured

- [ ] **BOP-026**: Cross-encoder re-rank after RRF
  - Why: Improves search relevance for ambiguous queries.
  - Evidence: ROADMAP (already planned)
  - Touches: `services/hybrid_search.py`
  - Acceptance: Top-10 results more relevant for ambiguous queries
  - Verify: A/B comparison of search results with and without re-ranker

- [ ] **BOP-027**: Reader view with highlight and annotation
  - Why: BOP captures content but can't read/highlight/annotate it.
  - Evidence: Competitive research (Linkwarden, Readwise, Readeck all offer this)
  - Touches: New `ui/reader_view.py`
  - Acceptance: Open snapshot; highlight text; add note; persists on reopen
  - Verify: Manual highlight workflow

- [ ] **BOP-028**: EPUB export of collections
  - Why: Offline e-reader access for bookmark collections.
  - Evidence: Competitive research (Readeck EPUB + OPDS)
  - Touches: New service + CLI subcommand + GUI export option
  - Acceptance: Export 10-bookmark collection; open in Calibre; verify TOC
  - Verify: EPUB validates with epubcheck

- [ ] **BOP-029**: YouTube transcript capture and indexing
  - Why: Video bookmarks are opaque — only title/URL searchable.
  - Evidence: Competitive research (Readeck extracts transcripts)
  - Touches: `services/ingest.py`
  - Acceptance: YouTube bookmark's transcript appears in semantic search
  - Verify: Save YouTube URL; run hybrid search for topic; verify result

- [ ] **BOP-030**: Sanitize user data in LLM prompts (truncate, strip control chars, XML delimiters)
  - Why: Prompt injection via malicious bookmark titles/descriptions.
  - Evidence: Code audit AI layer (verified: unsanitized data in prompts)
  - Touches: `ai.py:473`, `citation_summarizer.py:104`, `rag_chat.py:88`, `nl_query.py:78`
  - Acceptance: Bookmark with `</system>` in title doesn't break LLM behavior
  - Verify: Add bookmark with adversarial title; run summarize; verify clean output

- [ ] **BOP-031**: Fix URL normalization HTTP->HTTPS upgrade (preserve original scheme)
  - Why: Silent scheme change breaks bookmarks for HTTP-only sites.
  - Evidence: Code audit core data layer (verified: unconditional upgrade)
  - Touches: `utils/url.py:97-98`
  - Acceptance: HTTP URLs stay HTTP unless user explicitly changes
  - Verify: Add HTTP URL; verify scheme preserved

- [ ] **BOP-032**: Add pre-restore backup to `StorageManager.restore_backup`
  - Why: Restore from backup destroys current data without safety net.
  - Evidence: Code audit core data layer (verified: no pre-restore backup)
  - Touches: `core/storage_manager.py:149`
  - Acceptance: Restore creates `pre_restore_backup_<timestamp>.json`
  - Verify: Restore; verify backup file exists

- [ ] **BOP-033**: Add thread safety to TagManager
  - Why: No locking in TagManager while BookmarkManager is thread-safe.
  - Evidence: Code audit core data layer (verified: no locks)
  - Touches: `managers/tags.py`
  - Acceptance: Concurrent tag operations don't corrupt data
  - Verify: Parallel add/remove tags test

- [ ] **BOP-034**: Fix `save_bookmarks` lock race (hold BM lock through storage.save)
  - Why: Lock released before storage.save() creates race condition.
  - Evidence: Code audit core data layer (verified: lock/save ordering)
  - Touches: `managers/bookmarks.py:117-120`
  - Acceptance: Concurrent save operations are serialized
  - Verify: Concurrent save stress test

- [ ] **BOP-035**: Deduplicate cross-category patterns in default_categories.py
  - Why: Same domains appear in multiple categories, causing inconsistent categorization.
  - Evidence: Code audit core data layer (verified: retool.com, serverfault.com, hetzner.com)
  - Touches: `core/default_categories.py`
  - Acceptance: No domain appears in more than one category
  - Verify: Script to check for duplicates

- [ ] **BOP-036**: Fix overly broad plain patterns (convert to typed)
  - Why: Patterns like 'porn.', 'click.', ':3000' match too aggressively.
  - Evidence: Code audit core data layer (verified: broad substring matches)
  - Touches: `core/default_categories.py`, `core/pattern_engine.py`
  - Acceptance: `click.com` categorized correctly; `click.example.com` not false-positive
  - Verify: Test with edge-case domains

- [ ] **BOP-037**: Add intra-file dedup to importers
  - Why: Importing a file with duplicate URLs creates duplicates.
  - Evidence: Code audit core data layer (verified: no dedup within file)
  - Touches: `importers.py`, `importers_extra.py`
  - Acceptance: Import file with 5 identical URLs -> 1 bookmark created
  - Verify: Import test file with known duplicates

- [ ] **BOP-038**: Fix `GridView.bind_all('<MouseWheel>')` scroll stealing
  - Why: Grid view steals scroll events from all other widgets.
  - Evidence: Code audit UI layer (verified: bind_all instead of bind)
  - Touches: `ui/widget_grid.py:78`, `ui/components.py:633`
  - Acceptance: Scrolling in sidebar doesn't scroll grid view
  - Verify: Manual scroll test in different panels

- [ ] **BOP-039**: Fix command palette FocusOut closing before click registers
  - Why: Clicking a palette item closes it before the click registers.
  - Evidence: Code audit UI layer (verified: FocusOut handler)
  - Touches: `ui/shell_widgets.py:398`
  - Acceptance: Click on command palette item triggers the command
  - Verify: Open palette; click an item; verify action triggers

- [ ] **BOP-040**: Add undo support for bulk category moves and duplicate removal
  - Why: Destructive bulk operations have no undo path.
  - Evidence: Code audit UI layer (verified: no undo for bulk ops)
  - Touches: `app_mixins/bookmark_crud.py`, `app_mixins/selection.py`, `app_mixins/tools.py`
  - Acceptance: Bulk move 20 bookmarks; undo; all return to original categories
  - Verify: Manual undo test

### P3 — Nice-to-have (polish, future positioning)

- [ ] **BOP-041**: Obsidian vault sync via MCP export tool
  - Why: PKM users want bookmarks in their knowledge vault.
  - Evidence: Competitive research (Omnivore's killer feature)
  - Touches: `mcp_server.py`, new service module
  - Acceptance: Bookmarks exported as Markdown with YAML frontmatter
  - Verify: Export to Obsidian; verify rendering

- [ ] **BOP-042**: Nuitka compilation for distribution
  - Why: Fewer AV false positives, faster startup, native C compilation.
  - Evidence: Competitive research (Nuitka 2.8)
  - Touches: Build system, CI/CD
  - Acceptance: Nuitka-compiled binary runs without AV flags
  - Verify: Build; run; test with common AV

- [ ] **BOP-043**: tufup auto-update framework
  - Why: No auto-update mechanism — users must manually download new versions.
  - Evidence: Competitive research (tufup 0.10.0)
  - Touches: Build system, new update service
  - Acceptance: App checks for updates on launch; downloads binary diff
  - Verify: Release new version; verify update prompt

- [ ] **BOP-044**: sv-ttk theme migration
  - Why: Modern Windows 11 appearance without CustomTkinter dependency.
  - Evidence: Competitive research + ROADMAP (already planned)
  - Touches: `ui/theme.py`, `ui/style_manager.py`, all theme files
  - Acceptance: App renders with Windows 11 Sun Valley style
  - Verify: Visual comparison on Windows 11

- [ ] **BOP-045**: Behavioral triage: inbox with aging indicators (amber 7d, red 30d)
  - Why: Encourages users to categorize/review saved bookmarks.
  - Evidence: Competitive research (Burn 451's triage mechanism)
  - Touches: New UI section + filter logic
  - Acceptance: Uncategorized bookmarks show aging color indicators
  - Verify: Add bookmark; wait; verify color change

- [ ] **BOP-046**: Graph view of bookmarks
  - Why: Visual exploration of bookmark relationships.
  - Evidence: ROADMAP (already planned)
  - Touches: New `ui/graph_view.py`
  - Acceptance: Bookmarks as nodes, tags as edges, interactive layout
  - Verify: Open graph view with 100+ bookmarks; verify interactivity

- [ ] **BOP-047**: ATOM/JSON Feed output per collection
  - Why: Share collections as RSS feeds.
  - Evidence: ROADMAP (already planned)
  - Touches: New export service
  - Acceptance: Feed validates in feed reader
  - Verify: Export feed; open in RSS reader

- [ ] **BOP-048**: Matter/Omnivore/Zotero importers
  - Why: Support users migrating from dead/academic tools.
  - Evidence: ROADMAP (already planned)
  - Touches: `importers_extra.py`
  - Acceptance: Import from each format without errors
  - Verify: Import test data from each format

- [ ] **BOP-049**: MCP auth token with per-tool scopes
  - Why: Protect bookmark data from unauthorized MCP clients.
  - Evidence: ROADMAP (already planned)
  - Touches: `mcp_server.py`
  - Acceptance: Read-only token cannot use `add_bookmark`
  - Verify: Connect with scoped token; verify access control

- [ ] **BOP-050**: MCP streaming for `chat_with_collection`
  - Why: RAG responses currently block until complete.
  - Evidence: ROADMAP (already planned)
  - Touches: `mcp_server.py`, `services/rag_chat.py`
  - Acceptance: Chat response streams token-by-token
  - Verify: Connect via Claude Desktop; verify streaming

- [ ] **BOP-051**: Remove ~1,300 lines of dead code (GridView, unused widgets, broken tray)
  - Why: Dead code confuses developers and inflates binary size.
  - Evidence: Code audit architecture section (verified)
  - Touches: `ui/widget_grid.py`, `ui/widget_lists.py`, `ui/components.py`, `ui/widget_tray.py`, `ui/shell_widgets.py`, `ui/drag_drop.py`
  - Acceptance: All removed code unreferenced; app launches cleanly
  - Verify: Run app; verify all features still work

- [ ] **BOP-052**: Fix all copy-pasted model docstrings on widget classes
  - Why: Misleads developers and IDE tooltips.
  - Evidence: Code audit architecture section (verified)
  - Touches: Multiple UI files
  - Acceptance: Each class has accurate docstring
  - Verify: IDE tooltip check

- [ ] **BOP-053**: Move constants.py directory creation to `ensure_directories()`
  - Why: Side effects on import; directories created even when not needed.
  - Evidence: Code audit architecture section (verified)
  - Touches: `constants.py`, `launcher.py`, `mcp_server.py`, `cli.py`
  - Acceptance: `import bookmark_organizer_pro.constants` creates no directories
  - Verify: Import in fresh Python session; verify no dirs created

- [ ] **BOP-054**: Validate RAG citation IDs, strip hallucinated `[#cN]` tokens
  - Why: LLM may output citations referencing non-existent chunks.
  - Evidence: Code audit AI layer (verified: no validation)
  - Touches: `services/rag_chat.py:92-97`
  - Acceptance: `[#c99]` on 6-chunk context is stripped from output
  - Verify: Force LLM to hallucinate citation; verify stripped

- [ ] **BOP-055**: Extract health score to single shared utility
  - Why: 3 different formulas in 3 locations produce inconsistent scores.
  - Evidence: Code audit architecture section (verified)
  - Touches: `app_mixins/dashboard.py`, `ui/components.py`, `ui/widget_analytics.py`, new `utils/health.py`
  - Acceptance: All health score displays show identical values
  - Verify: Compare scores across all 3 locations

- [ ] **BOP-056**: Use keyring/DPAPI for API key storage on Windows
  - Why: API keys stored as plaintext JSON; any local process can read.
  - Evidence: Code audit security section (verified)
  - Touches: `ai.py:211-214`
  - Acceptance: API keys stored in Windows Credential Manager
  - Verify: Check `ai_config.json` contains no plaintext keys

- [ ] **BOP-057**: Add Ollama URL SSRF check (restrict to localhost by default)
  - Why: Ollama URL can be pointed at arbitrary hosts.
  - Evidence: Code audit security section (verified)
  - Touches: `ai.py:197-199`
  - Acceptance: Non-localhost Ollama URL rejected with warning
  - Verify: Set Ollama URL to external IP; verify rejection

- [ ] **BOP-058**: Remove `ensure_package` runtime pip install; require explicit install
  - Why: Supply chain risk — runtime pip install from untrusted PyPI.
  - Evidence: Code audit security section (verified)
  - Touches: `ai.py:21-37`
  - Acceptance: Missing package shows clear install instructions instead of auto-installing
  - Verify: Remove a dep; run feature; verify instruction message

- [ ] **BOP-059**: Make thum.io screenshot API opt-in with privacy disclosure
  - Why: Private bookmark URLs sent to third-party without disclosure.
  - Evidence: Code audit privacy section (verified)
  - Touches: `services/web_tools.py:521-524`
  - Acceptance: First use shows disclosure dialog; disabled by default
  - Verify: Trigger screenshot; verify disclosure dialog

- [ ] **BOP-060**: Add keyboard accessibility to treeview (tab focus, column sort shortcuts)
  - Why: No keyboard navigation for main bookmark list.
  - Evidence: Code audit accessibility section (verified)
  - Touches: `app_mixins/app_shell.py:412-416`, `ui/treeview.py:31`
  - Acceptance: Tab into treeview; arrow keys navigate; Enter opens; Shift+click sorts
  - Verify: Keyboard-only navigation test

---

## 12. Quick Wins

Items that can be fixed in under 30 minutes each, with high confidence and no risk:

| # | Item | File:Line | What to Do |
|---|------|-----------|------------|
| 1 | Chunk overlap bug | `services/embeddings.py:182` | Change `max(end - overlap, end)` to `end - overlap` |
| 2 | Dead `_extract_text` conditional | `services/web_tools.py:444` | Remove `if 'html_module' in dir() else text` — just call `html_module.unescape(text)` |
| 3 | Tag linter no-op line | `services/tag_linter.py:92` | Delete the line |
| 4 | Snapshot URL escaping | `services/snapshot.py:182-184` | Wrap `url` in `html.escape(url, quote=True)` |
| 5 | Log rotation | `logging_config.py:37` | Replace `FileHandler` with `RotatingFileHandler(maxBytes=5_000_000, backupCount=3)` |
| 6 | Logging fallback | `logging_config.py:36-46` | Add stderr handler in except block |
| 7 | `remove_tag` case sensitivity | `models/bookmark.py:159` | Change to case-insensitive: `self.tags = [t for t in self.tags if t.lower() != tag.lower()]` |
| 8 | `get_stale_bookmarks` ignores `days` | `managers/bookmarks.py:336-338` | Filter with `bm.age_days > days` instead of `bm.is_stale` |
| 9 | Search empty query | `search.py:237-239` | Return `[]` for empty query |
| 10 | Pre-restore backup | `core/storage_manager.py:149` | Add `self._create_backup()` before `shutil.copy2` |
| 11 | `bg_color` dead code | `ui/widget_controls.py:468` | Delete `bg_color = color + "26"` |
| 12 | Rename dialog chrome | `app_mixins/categories.py:200-246` | Add `apply_window_chrome(dialog)` |
| 13 | BookmarkCLI docstring | `cli.py:21-47` | Replace with accurate CLI description |
| 14 | Date filter includes bad timestamps | `search.py:178-184` | Change `pass` to `return False` in except |
| 15 | `decrypt_file` dst validation | `services/encryption.py:107-108` | Add `assert dst != src` and existence check |

---

## 13. Larger Bets

### 13.1 FastMCP 3.x Migration (Complexity: M, Timeline: 1-2 days)

**Thesis:** BOP's MCP server is its most unique feature but is crippled by untyped schemas. FastMCP 3.x auto-generates JSON Schema from type hints, adds strict validation, ToolAnnotations, and structured output. This transforms the MCP server from a proof-of-concept to a production-quality AI integration.

**Risk:** FastMCP dependency adds ~5MB. Version churn (3.0->3.4 in 3 months) may require pinning.

**Expected outcome:** Claude Desktop correctly infers all parameters. Zero runtime TypeErrors from malformed args.

### 13.2 Nuitka + tufup Distribution Pipeline (Complexity: L, Timeline: 3-5 days)

**Thesis:** PyInstaller's self-extracting archive pattern triggers AV false positives on ~30% of Windows machines. Nuitka compiles to native C, eliminating this. tufup adds TUF-based auto-update with binary diff patches. Together, they match the single-binary distribution polish of Go tools (Readeck, Shiori).

**Risk:** Nuitka builds take 5-15 minutes (vs 30s PyInstaller). Some packages need manual Nuitka plugin config.

**Expected outcome:** Zero AV false positives. 2-4x faster startup. Auto-update for users.

### 13.3 Web Client (Complexity: XL, Timeline: 2-4 weeks)

**Thesis:** Every successful bookmark tool has a web interface. Mobile browsing is 60%+ of usage. The web client enables PWA, share-intent, and multi-device access from a single codebase.

**Risk:** Largest single investment. SQLite concurrent access needs WAL mode. Two UI surfaces to maintain.

**Expected outcome:** BOP usable from any device. Mobile PWA captures the 60% mobile browsing use case.

### 13.4 Browser Extension (Complexity: L, Timeline: 1 week)

**Thesis:** The single biggest UX gap. One-click save with offline tag suggestions (4,200 patterns, no network needed) would be the fastest and smartest extension in the category.

**Risk:** Native messaging requires platform-specific registration. MV3 service worker lifetime limits.

**Expected outcome:** Save bookmarks without switching apps. Instant tag suggestions.

---

## 14. Explicit Non-Goals

1. **Multi-user / team features** — BOP is a personal tool. Multi-user adds authentication, authorization, conflict resolution, and deployment complexity that contradicts the local-first model. Linkwarden and Linkding cover the team use case.

2. **Docker deployment** — BOP's advantage is no-Docker-required. Adding Docker support is fine, but it should never be the primary or required deployment method.

3. **Full-text indexing via Meilisearch/Elasticsearch sidecar** — BOP's built-in FTS5 + LanceDB hybrid search is a key simplicity advantage over Karakeep's Meilisearch requirement. Do not add external search infrastructure.

4. **Cloud-hosted SaaS version** — Until the core product is stable (P0/P1 cleared), a hosted tier adds infrastructure cost and operational burden. Revisit after v7.0.

5. **Mobile native apps** (iOS/Android) — PWA via the web client covers 90% of mobile use. Native apps are a massive investment for a single-maintainer project.

6. **Rewrite in another language** — Python + Tkinter is the right stack for this project's constraints. The ecosystem (fastembed, lancedb, mcp, trafilatura) is Python-native. Migrate to Nuitka for performance, not to a new language.

7. **AI-only organization** (no manual control) — Unlike mymind, BOP should always support manual categorization and tags. AI assists; the user decides.

---

## 15. Open Questions

1. **Is `AIBatchProcessor` ever actually called from the GUI?** The 2 critical crashers suggest it may never have been tested at runtime. If no GUI path triggers it, the priority drops from P0 to P1. **Needs live validation.**

2. **What is the actual test coverage?** The README says 37 tests, but `test_core.py` has 142 test methods across 22 classes. Is 142 the current count? Are there additional test files not in `tests/`? **Verified:** 142 is correct per grep. Only one test file exists.

3. **Has the PyInstaller binary ever been tested with v6.0 features?** The missing hidden_imports suggest the v6 binary is fundamentally broken. Has anyone tested `embed`, `encrypt`, `mcp-server` from the .exe? **Needs live validation.**

4. **What is the actual bookmark count for the primary user?** Performance recommendations depend on whether the user has 500 or 50,000 bookmarks. The 10K threshold for virtualization may or may not be relevant today. **Assumption:** Based on the 4,200+ patterns and "power user" profile, likely 1,000-10,000.

5. **Is the REST API (services/api.py) used in production?** It has no auth and is bound to 127.0.0.1. If it is only used for local development, the security urgency is lower. If the browser extension will use it, auth is critical before the extension ships. **Needs user input.**

6. **Should BOP support SQLite as an alternative backend?** The current JSON file storage works for thousands of bookmarks but will not scale to 100K+. LanceDB already uses a directory-based format. A full SQLite migration is a major effort but would unlock WAL mode for concurrent access (web client) and vastly improve query performance. **Architecture decision needed.**

7. **Which embedding model should be the default?** Currently using FastEmbed's default (`bge-small-en-v1.5`, 384-dim, 130MB). `nomic-embed-text` (768-dim, 274MB, 8K context, MTEB 62.39) is 6 MTEB points better with 32x longer context, ideal for full-page content. Tradeoff: 2x model size, 2x vector storage. **Needs benchmarking.**

8. **Is the Google Gemini `system_instruction` parameter available in the installed SDK version?** The audit notes that `GoogleClient.complete()` concatenates system prompt into user message. If the installed `google-generativeai` version supports `system_instruction`, this is an easy quality win. **Needs version check.**

9. **Should `ensure_package` runtime pip install be removed entirely?** It is a supply chain risk, but removing it breaks the first-run experience for non-technical users who expect dependencies to auto-install. Possible middle ground: prompt user with exact package names and versions before installing, and pin with hashes. **Product decision needed.**

10. **What is the target for the CustomTkinter/sv-ttk migration?** CustomTkinter is stagnating (no releases in 12 months, maintainer absent). sv-ttk is lightweight and actively maintained but theme-only (no new widgets). tksheet solves the virtualization problem independently. Recommendation: sv-ttk + pywinstyles + darkdetect for theming, tksheet for the list view. **Architecture decision needed.**
