# Project Research and Feature Plan

> **Date:** 2026-06-05 | **Version:** v6.4.0 | **Pass:** 4 (full-spectrum 5-dimension audit)
> **Scope:** Architecture, feature inventory, security, UI/accessibility, competitive ecosystem.
> **Prior:** All P0/P1 from passes 1-3 resolved. This pass is a comprehensive ground-truth audit across 135 files (~44,370 lines) with deep-research competitive intelligence.

---

## Executive Summary

Bookmark Organizer Pro v6.4.0 is a genuinely differentiated product: the only serious open-source desktop bookmark manager with AI categorization (6 providers, 4,200+ patterns), semantic search (fastembed/LanceDB), and a 20-tool MCP server. It occupies an uncontested niche -- every major competitor is either cloud SaaS (Raindrop.io, Readwise Reader), self-hosted web (Karakeep 24K stars, Linkwarden 17.7K, Wallabag 12K), or aging CLI-only (Buku). BOP is the only one that is desktop-native, local-first, zero-Docker, and MCP-enabled simultaneously.

However, beneath the feature breadth lie structural issues that will compound: a critical MCP authentication gap (auth module exists but is dead code), nested lock deadlock risk, 15+ CLI-only features invisible to GUI users, 72 silently swallowed exceptions, stale version strings across 4 files, and hardcoded colors/fonts breaking cross-platform rendering. The competitive window is real but narrowing -- Karakeep, Raindrop, and Burn 451 all shipped MCP servers in 2026, and the MCP ecosystem now has 13,000+ servers with clear design conventions BOP should adopt.

**Top 10 opportunities in priority order:**

1. **Wire MCP authentication** -- 20 tools exposed with zero auth enforcement (critical security gap)
2. **Fix OPML/XBEL XXE vulnerability** -- unsafe XML parsing on user-supplied import files
3. **Sanitize LocalArchiver HTML output** -- stored XSS via unsanitized fetched content
4. **Sync version strings** -- PyInstaller spec at 6.2.1, CLAUDE.md at 6.1.0, app at 6.4.0
5. **Surface CLI-only features in GUI** -- 15+ features (importers, exports, search modes, chat) are GUI-invisible
6. **Add MCP write tools** -- delete, update, tag mutation needed for agent-driven curation
7. **Fix hardcoded Segoe UI fonts** -- 35+ references break macOS/Linux rendering
8. **Theme-aware DependencyCheckDialog** -- 40 hardcoded Catppuccin Mocha colors ignore active theme
9. **Add Help menu + About dialog wiring** -- AboutDialog is fully built but unreachable
10. **Batch save API** -- every single-bookmark mutation triggers full file serialization

---

## Evidence Reviewed

### Local Files Inspected (135 .py files total)

- `bookmark_organizer_pro/__init__.py` -- package re-exports, 186 symbols in `__all__`
- `bookmark_organizer_pro/app.py` -- 15-class mixin composition, FinalBookmarkOrganizerApp
- `bookmark_organizer_pro/app_mixins/` (22 files) -- all 14 mixins + AI sub-mixins
- `bookmark_organizer_pro/ai.py` -- AIConfigManager, 5 AI client classes, keyring fallback
- `bookmark_organizer_pro/cli.py` -- BookmarkCLI, 37 subcommands
- `bookmark_organizer_pro/mcp_server.py` -- 20 MCP tools, no auth enforcement
- `bookmark_organizer_pro/services/` (35 files) -- all service modules
- `bookmark_organizer_pro/ui/` (40 files) -- full widget/dialog/theme layer
- `bookmark_organizer_pro/models/` (4 files) -- Bookmark, Category, Tag dataclasses
- `bookmark_organizer_pro/core/` (5 files) -- PatternEngine, StorageManager, CategoryManager, default_categories
- `bookmark_organizer_pro/managers/` (3 files) -- BookmarkManager (933 lines), TagManager
- `bookmark_organizer_pro/importers.py`, `importers_extra.py` -- 13 importers
- `bookmark_organizer_pro/search.py` -- SearchEngine, FuzzySearchEngine, SearchQuery parser
- `bookmark_organizer_pro/url_utils.py` -- SSRF guards, URL utilities
- `bookmark_organizer_pro/constants.py` -- APP_VERSION = "6.4.0"
- `bookmark_organizer_pro/theme_runtime.py` -- 11 built-in themes
- `bookmark_organizer_pro/desktop_bootstrap.py` -- DPI awareness, dark title bar
- `bookmark_organizer_pro/launcher.py` -- CLI dispatch, privacy banner
- `packaging/bookmark_organizer.spec` -- PyInstaller config (stale at 6.2.1)
- `packaging/version_info.txt` -- Windows version info (likely stale)
- `pyproject.toml` -- version 6.4.0, requires-python >= 3.10
- `tests/` (5 files) -- 255 test methods
- `ROADMAP.md` v3.0 -- 50 items, many completed
- `CHANGELOG.md` -- current through v6.4.0
- `README.md` -- comprehensive, Python version mismatch (says 3.8+)
- `CLAUDE.md` -- stale at v6.1.0
- `.github/workflows/build.yml` -- CI/CD pipeline

### Git History Range

Last 20 commits on main branch (v6.1.0 through v6.4.0, June 2026).

### External Sources

- Raindrop.io (official MCP server, Stella AI assistant)
- Karakeep/Hoarder (~24K stars, MCP server, Ollama tagging)
- Linkwarden (~17.7K stars, triple archive, reader view)
- Wallabag (~12K stars, highlight API, Obsidian sync)
- Buku (v5.0, Python CLI, SQLite)
- Burn 451 (26-tool MCP server, triage model)
- Markwise (chat-with-bookmarks Chrome extension)
- Readwise Reader ($9.99/mo, MCP server, highlights)
- mymind (visual-first, folder-free AI)
- BookmarkOS ($2.50/mo, desktop metaphor)
- Diigo (academic annotations)
- AWS Labs MCP Design Guidelines (snake_case, Pydantic Field(), AI instructions)
- MCP ecosystem data (13,000+ servers, OAuth 2.1 trend)
- Nuitka 4.x benchmarks (AV false positive elimination)
- Embedding model landscape (jina-v5, Qwen3-Embedding, bge-m3, model2vec)
- Arc Browser shutdown (May 2025, migration tools)
- Pocket shutdown (July 2025, refugee migration)
- Omnivore shutdown (Nov 2024, ElevenLabs acquihire)

---

## Current Product Map

### Core Workflows

1. **Import -> Categorize -> Search** -- Import bookmarks from 13 sources, auto-categorize via 4,200+ pattern engine, search via boolean/semantic/hybrid
2. **AI Enrichment** -- 6 AI providers (OpenAI, Anthropic, Gemini, Groq, Ollama, DeepSeek) for categorization, tag suggestion, title improvement, summarization
3. **Content Preservation** -- Snapshot chain (monolith -> singlefile -> playwright -> python), extracted text, Wayback Machine integration
4. **Research Flows** -- Create research trails linking related bookmarks with annotations (CLI/MCP only)
5. **MCP Integration** -- 20 stdio tools for Claude Desktop/Cursor/Codex to query and add bookmarks
6. **CLI Power User** -- 37 subcommands for import, export, search, AI operations, encryption

### Existing Features (by surface)

| Surface | Feature Count | Notes |
|---------|--------------|-------|
| GUI (Tkinter) | ~20 features | Import (file/browser), export (5 formats), search, categories, themes, zoom, command palette, bulk ops |
| CLI | 37 subcommands | Full feature access including 15+ GUI-invisible features |
| MCP Server | 20 tools | Read-heavy (list/search/chat), limited write (add_bookmark, create_flow) |
| REST API | 8 endpoints | GET unauthenticated, POST/DELETE auth-gated, localhost only |

### User Personas

1. **Power User / Knowledge Worker** -- Thousands of bookmarks, needs AI categorization, semantic search, research flows, Obsidian export
2. **Privacy-Conscious User** -- Local-first, no cloud dependency, encrypted storage, no telemetry
3. **Developer / AI Agent Operator** -- MCP server integration, CLI automation, API access
4. **Casual User** -- Import browser bookmarks, basic search, clean up duplicates

### Platforms

- Windows (primary) -- DPI awareness, dark title bar via DwmSetWindowAttribute
- macOS -- supported via Tkinter, font fallback to SF Pro Display
- Linux -- supported via Tkinter, font fallback to DejaVu Sans

### Integrations

- **AI Providers:** OpenAI, Anthropic, Google Gemini, Groq, Ollama, DeepSeek
- **Embedding:** fastembed (ONNX), model2vec (static), sentence-transformers (PyTorch)
- **Vector Store:** LanceDB (preferred), JSON cosine store (fallback)
- **Content Extraction:** trafilatura, BeautifulSoup4
- **Snapshot:** monolith (Rust), single-file (Node), playwright, BS4 fallback
- **MCP:** fastmcp >= 2.0, mcp >= 1.0
- **Encryption:** cryptography (AES-256-GCM, PBKDF2)
- **Export Targets:** Obsidian, EPUB, Atom, JSON Feed, Zotero RDF, XBEL

---

## Feature Inventory

### 1. AI Categorization Engine

- **User Value:** Automatically assigns categories to bookmarks using 4,200+ URL patterns across 43 categories, then optional AI enhancement via 6 providers
- **Entry Points:** GUI: AI menu -> "Auto-Categorize"; CLI: `bop categorize`; MCP: implicit via `add_bookmark`
- **Code Locations:** `core/pattern_engine.py` (pattern matching), `core/default_categories.py` (5,768 lines of patterns), `services/ai_tools.py` (683 lines, AI categorization), `app_mixins/ai_categorization.py` (background worker)
- **Maturity:** High -- O(1) domain lookup, two-pass priority system, cross-category dedup completed
- **Tests:** 154 methods in `test_core.py` cover pattern engine, including two-pass priority tests (BUG-10/11)
- **Improvement Opportunities:**
  - `default_categories.py` at 5,768 lines should be externalized to JSON (finding #12)
  - Background AI worker mutates shared Bookmark objects without synchronization (finding #2)
  - 7 `except Exception: pass` in pattern_engine.py silently skip miscategorizations (finding #6)

### 2. Search System (Boolean + Semantic + Hybrid)

- **User Value:** 15+ filter types (domain:, tag:, category:, date:, is:, has:, regex, boolean), semantic vector search, hybrid RRF fusion with optional cross-encoder re-rank
- **Entry Points:** GUI: search bar; CLI: `bop search`, `bop semantic`, `bop hybrid`; MCP: `search_bookmarks`, `semantic_search`, `hybrid_search`
- **Code Locations:** `search.py` (492 lines, SearchQuery parser, SearchEngine, FuzzySearchEngine), `services/hybrid_search.py` (RRF fusion), `services/embeddings.py` (embedding generation), `services/vector_store.py` (LanceDB/JSON store)
- **Maturity:** High for keyword search; Medium for semantic (depends on optional deps)
- **Tests:** Covered in `test_core.py` (search tests), `test_services.py` (embeddings)
- **Improvement Opportunities:**
  - Saved searches and search history are in-memory only, never persisted (finding #23)
  - Search bar tooltip documents only 5 of 15+ filter types (finding #31)
  - `get_syntax_help()` returns comprehensive help text but is never shown in GUI (finding #27)
  - Semantic/hybrid search modes not exposed in GUI search bar (finding #19)

### 3. MCP Server

- **User Value:** 20 stdio tools for AI agents to query, search, add bookmarks, create flows, export data
- **Entry Points:** `python -m bookmark_organizer_pro.mcp_server`, `bop-mcp` console script
- **Code Locations:** `mcp_server.py` (728 lines), `services/mcp_auth.py` (token management -- dead code)
- **Maturity:** Medium -- tools work, but auth is unwired, no delete/update tools, no streaming
- **Tests:** 20 tests in `test_mcp_tools.py`
- **Improvement Opportunities:**
  - Auth module is dead code -- zero authentication enforcement (finding #37, critical)
  - No delete, update, or tag mutation tools (finding #20)
  - Tool descriptions lack AI instruction phrases per AWS Labs guidelines (finding #71)
  - Independent BookmarkManager instance -- no shared state with GUI (finding #10)

### 4. Bookmark Import (13 Importers)

- **User Value:** Import from Chrome/Firefox/Edge/Brave profiles, Pocket, Raindrop, Readwise CSV, Pinboard JSON, Instapaper, Reddit Saved, Matter CSV, Zotero RDF, OPML, Netscape HTML, OneTab, text URLs
- **Entry Points:** GUI: File -> Import (file-based and browser profiles only); CLI: `bop import-*` (all 13)
- **Code Locations:** `importers.py` (654 lines, 8 importers), `importers_extra.py` (322 lines, 5 importers), `services/zotero_interop.py`
- **Maturity:** High for file-based, Medium for service-specific (CLI-only)
- **Tests:** Basic coverage in `test_core.py`
- **Improvement Opportunities:**
  - GUI import dialog only exposes file-based and browser imports; 7 service importers are CLI-only (finding #19)
  - OneTab importer exists but is not wired to GUI or CLI (finding #34)
  - OPML importer uses unsafe XML parsing without defusedxml (finding #38, high severity)
  - Missing importers for Arc Browser, Wallabag, Linkwarden (finding #73)
  - Import backup file grows unboundedly with no rotation (finding #9)

### 5. Bookmark Export (7+ Formats)

- **User Value:** Export to HTML, JSON, CSV, Markdown, OPML, XBEL, ZIP archive, plus Obsidian, EPUB, Atom, JSON Feed, Zotero RDF
- **Entry Points:** GUI: File -> Export (HTML/JSON/CSV/Markdown/OPML only); CLI: `bop export`, `bop obsidian-export`, `bop epub-export`, `bop atom-export`, `bop json-feed`, `bop zotero-export`, `bop zip-export`
- **Code Locations:** `managers/bookmarks.py` (export_html/json/csv/markdown/txt/urls_only), `services/obsidian_export.py`, `services/epub_export.py`, `services/feed_export.py`, `services/zip_export.py`, `services/zotero_interop.py`, `io_formats/xbel.py`
- **Maturity:** High for basic formats, Medium for specialized (CLI-only)
- **Tests:** `test_services.py` covers zip_export
- **Improvement Opportunities:**
  - XBEL handler exists but is not accessible from GUI export dialog or CLI export command (finding #35)
  - 5 export formats (Obsidian, EPUB, Atom, JSON Feed, Zotero) are CLI-only (finding #19)
  - `export_html` hardcodes "v4" in HTML comment instead of APP_VERSION (finding #18)

### 6. Theme System (11 Built-in Themes)

- **User Value:** 11 themes (GitHub Dark/Light, Catppuccin Mocha, Dracula, Nord, Monokai, Tokyo Night, Gruvbox, High Contrast, Studio, Solarized Dark), custom theme CRUD, 40+ design tokens
- **Entry Points:** GUI: Themes button in toolbar; custom theme creation dialog
- **Code Locations:** `theme_runtime.py` (theme definitions), `ui/theme.py` (ThemeColors dataclass), `ui/style_manager.py` (ttk styles), `ui/foundation.py` (FontConfig, DesignTokens, readable_text_on), `app_mixins/themes.py` (live theme refresh)
- **Maturity:** Medium -- architecture is solid but application is inconsistent
- **Tests:** None
- **Improvement Opportunities:**
  - DependencyCheckDialog ignores active theme, hardcodes 40 Catppuccin Mocha colors (finding #51)
  - 35+ hardcoded `font=('Segoe UI', ...)` references bypass FONTS system (finding #52)
  - Live theme refresh naively resets all Labels to bg_primary (finding #53)
  - Privacy banner, SearchHighlighter, make_keyboard_activatable all use hardcoded colors (findings #55, #56, #57)
  - Dark title bar forced regardless of theme.is_dark (finding #58)
  - Duplicate bg_card/card_bg tokens, unused card_outline (finding #61)
  - Button foregrounds hardcoded to #ffffff, breaking on light-accent themes (finding #63)

### 7. About Dialog

- **User Value:** 4-tab dialog (About, Features, System, Credits) showing version, features, system info, technologies
- **Entry Points:** None -- fully implemented but unreachable (finding #21)
- **Code Locations:** `ui/about.py` (339 lines)
- **Maturity:** Complete implementation, zero accessibility
- **Tests:** None
- **Improvement Opportunities:**
  - No menu item or button links to it (finding #21)
  - Credits tab references "Claude (Anthropic)" violating no-AI-refs rule (finding #32)
  - Features tab lists system tray and drag-and-drop that no longer exist (finding #26)
  - Credits tab claims Python 3.8+ but pyproject.toml requires 3.10+ (finding #65)

### 8. Command Palette

- **User Value:** Quick access to actions via Ctrl+P fuzzy search
- **Entry Points:** Ctrl+P keyboard shortcut
- **Code Locations:** `app_mixins/command_palette.py`
- **Maturity:** Low -- only 18 of 40+ possible commands registered
- **Tests:** None
- **Improvement Opportunities:**
  - Only 18 commands registered; missing Toggle Pin, Copy URL, Delete, About, all Tools/AI actions (finding #28)

### 9. RAG Chat (Chat with Bookmarks)

- **User Value:** Ask questions about saved bookmarks, get cited answers from local collection
- **Entry Points:** CLI: `bop chat`, `bop ask`; MCP: `chat_with_collection`; GUI: none
- **Code Locations:** `services/rag_chat.py`, `services/citation_summarizer.py`
- **Maturity:** Medium -- backend complete, zero GUI surface
- **Tests:** None
- **Improvement Opportunities:**
  - No GUI chat panel -- the most differentiating feature is invisible to GUI users (finding #70)
  - Answer caching (R-11) is shipped but only accessible via CLI/MCP

### 10. Read Later Queue

- **User Value:** Save bookmarks for later reading with position tracking
- **Entry Points:** CLI: `bop read-later`; GUI: none
- **Code Locations:** `services/read_later.py`
- **Maturity:** Low -- backend exists, zero GUI surface
- **Tests:** Covered in `test_services.py`
- **Improvement Opportunities:**
  - No GUI panel or sidebar section for read-later (finding #19)
  - No aging indicators or triage workflow (finding #78)

### 11. Research Flows

- **User Value:** Create research trails linking related bookmarks with annotations
- **Entry Points:** CLI: `bop flow`; MCP: `create_flow`, `append_to_flow`, `list_flows`, `get_flow`; GUI: none
- **Code Locations:** `services/flows.py`
- **Maturity:** Medium -- backend and MCP surface complete, zero GUI
- **Tests:** Covered in `test_services.py`
- **Improvement Opportunities:**
  - No GUI panel for flow creation, viewing, or management (finding #19)

### 12. Dead Link Scanner

- **User Value:** Detect broken links with redirect tracking and per-domain rate limiting
- **Entry Points:** CLI: `bop scan`; MCP: `list_dead_links`; GUI: none
- **Code Locations:** `services/dead_link_scanner.py`, `link_checker.py`
- **Maturity:** Medium -- concurrent scanning with rate limiting, but CLI-only
- **Tests:** None
- **Improvement Opportunities:**
  - No GUI trigger or results panel (finding #19)

### 13. Encryption

- **User Value:** AES-256-GCM encrypted database with PBKDF2 key derivation, passphrase rotation
- **Entry Points:** CLI: `bop encrypt`, `bop decrypt`; GUI: none
- **Code Locations:** `services/encryption.py`
- **Maturity:** High -- correct crypto (random salt/nonce, 480K iterations), passphrase rotation shipped
- **Tests:** Covered in `test_services.py`
- **Improvement Opportunities:**
  - No encryption toggle in GUI settings (finding #47)
  - No recovery phrase mechanism (finding #47)

### 14. Bookmark Editor Dialog

- **User Value:** Edit bookmark URL, title, category, and tags
- **Entry Points:** Ctrl+E or context menu
- **Code Locations:** `ui/widget_bookmark_editor.py`, `app_mixins/bookmark_crud.py`
- **Maturity:** Low -- only exposes 4 of 25+ Bookmark model fields
- **Tests:** None
- **Improvement Opportunities:**
  - Missing fields: notes, description, read-later toggle, pin status, flow assignment (finding #33)
  - Fixed 600x700 geometry with no scroll fallback (finding #62)

---

## Competitive and Ecosystem Research

### Raindrop.io (Cloud SaaS, #1 ranked)

- **Capabilities:** AI assistant "Stella" for NL organization, official MCP server, visual bookmark thumbnails, full-text search (Pro), cross-device sync, browser extensions for all browsers
- **Lessons:** NL organizational commands are the UX model for BOP's nl_query.py. Visual thumbnails (page screenshots) increase engagement. MCP server sets the SaaS benchmark.
- **What to Avoid:** Subscription pricing model. Cloud-only architecture. BOP's advantage is local-first with no subscription.

### Karakeep (formerly Hoarder, ~24K stars, self-hosted)

- **Capabilities:** MCP server (v0.24.0), auto-tagging via OpenAI/Anthropic/Ollama, multi-type inbox (links + notes + images + PDFs), per-user tag style enforcement (case/separator normalization), Docker deployment
- **Lessons:** Tag style enforcement is a feature BOP should match -- `tag_linter.py` surfaces duplicates but does not enforce naming conventions on save. Multi-type inbox (notes + images) is a differentiator BOP lacks.
- **What to Avoid:** Docker requirement. Web-only UI (no desktop app).

### Linkwarden (~17.7K stars, self-hosted)

- **Capabilities:** Triple archive (screenshot + PDF + SingleFile HTML), reader view with highlights/annotations, AI tagging, Wayback Machine push, PWA, collaborative collections
- **Lessons:** Triple archive is the preservation gold standard. Reader view with highlights is table stakes for serious bookmark tools (Linkwarden, Wallabag, Readwise all ship this). BOP has single-file snapshots but lacks PDF capture and per-page screenshots.
- **What to Avoid:** Collaborative/team features (contradicts BOP's single-user design).

### Wallabag (~12K stars, self-hosted)

- **Capabilities:** Highlight/annotation API, Obsidian sync pipeline, boolean tagging rules, ePub/PDF export, mature mobile apps
- **Lessons:** Wallabag-to-Obsidian pipeline is the gold standard for PKM integration. BOP already has Obsidian export; the missing piece is the highlight/annotation layer that feeds into it. Wallabag is the primary Pocket refugee destination.
- **What to Avoid:** Docker/PHP infrastructure complexity.

### Buku (v5.0, Python CLI + SQLite)

- **Capabilities:** Encrypted DB (AES-256), Wayback fallback, import/export HTML/XBEL/Markdown/Orgfile, shell completion (Bash/Fish/Zsh), tmux/Rofi/Emacs integration, bukuserver web UI
- **Lessons:** Shell completion scripts for 30+ subcommands would benefit BOP's CLI. Orgfile export serves the Emacs niche. Stagnating development (no significant releases since v5.0) -- BOP has already surpassed it on every AI/search/preservation axis.
- **What to Avoid:** Basic web UI (bukuserver). Stagnation.

### Burn 451 (AI-first, 26-tool MCP server)

- **Capabilities:** 24-hour triage model, per-article AI summaries, vault collections, 26-tool MCP server, free tier
- **Lessons:** Three-layer AI architecture (summary on save, organization with auto-tags, query via chat) -- BOP has all three layers implemented but the chat/query layer is CLI-only. 26 tools exceeds BOP's 20 -- review whether BOP should add bulk operations and tag management CRUD.
- **What to Avoid:** Data-anxiety-inducing auto-deletion. Cloud-only.

### Markwise (Chrome extension + web app)

- **Capabilities:** Chat with bookmark library using semantic search, YouTube timestamp saving, AI-generated answers with cited sources
- **Lessons:** "Chat with your bookmarks" is an emerging category BOP should own. No other desktop bookmark manager has a GUI chat panel. BOP has the backend (`rag_chat.py`) but it is CLI-only.
- **What to Avoid:** Chrome-extension-only (no desktop app).

### Readwise Reader ($9.99/mo, premium SaaS)

- **Capabilities:** Ghostreader AI summaries, highlight-based Q&A, spaced repetition, official MCP server, deepest highlight/annotation system
- **Lessons:** Defines the ceiling for bookmark+reading+highlighting tools. BOP should position as "the self-hosted Readwise Reader alternative" once reader view with highlights ships. The highlight-to-Obsidian pipeline is the gold standard.
- **What to Avoid:** $120/yr subscription. Cloud-only. Closed-source.

### MCP Ecosystem (13,000+ servers)

- **Capabilities:** OAuth 2.1 winning auth model (21/56 servers), AWS Labs design guidelines (snake_case, Pydantic Field(), AI instruction phrases), streaming support in July 2026 RC
- **Lessons:** BOP's MCP server should be audited against AWS Labs guidelines. Tool descriptions should include "Usage Requirements" and "Interpretation Guidelines" sections. Register on Smithery and PulseMCP for discoverability.

### Embedding Model Landscape (2026)

- **Capabilities:** jina-embeddings-v5-text (0.2B/0.6B, outperforms 7-14B models), Qwen3-Embedding-8B (highest MTEB), bge-m3 (reliable lightweight), model2vec (8-30MB, 500x CPU speedup)
- **Lessons:** BOP's fastembed integration should document recommended models by tier in README/settings UI. Model download progress indicator needed for first-time setup friction.

---

## Highest-Value New Features

### NF-01: GUI Chat Panel (Chat with Your Bookmarks)

- **User Problem:** BOP has a complete RAG chat backend (`rag_chat.py`) that lets users ask questions about their bookmark collection and get cited answers, but it is only accessible via CLI (`bop chat`, `bop ask`) and MCP (`chat_with_collection`). GUI users -- the majority -- never discover this differentiating feature. No other desktop bookmark manager has a GUI chat panel.
- **Evidence:** Finding #70 (competitive analysis -- Markwise and Burn 451 define the category), finding #19 (CLI-only features invisible to GUI). `services/rag_chat.py` and `services/citation_summarizer.py` are complete backends.
- **Proposed Behavior:** A sidebar panel or dialog accessible via Help menu or toolbar button. User types a question (e.g., "what articles did I save about Python async?"), gets cited answers with bookmark links. Supports follow-up questions. Shows chunk provenance per R-08.
- **Implementation Areas:** New `ui/widget_chat_panel.py` widget; new mixin `app_mixins/chat.py`; wire to `services/rag_chat.py`
- **Data/API/UI Implications:** Requires optional embedding deps (fastembed/LanceDB). Show graceful fallback message when deps missing. Stream responses token-by-token if possible.
- **Risks:** Requires embedding setup (first-time friction). May be slow on large collections without GPU.
- **Verification:** Open GUI, click Chat button, type a question, receive a cited answer referencing bookmarks in the library
- **Complexity:** L
- **Priority:** P1

### NF-02: MCP Write Tools (Delete, Update, Tag Mutation)

- **User Problem:** AI agents can add bookmarks and create flows via MCP but cannot delete, update, re-categorize, tag, pin, or archive existing bookmarks. This makes MCP useless for curation workflows.
- **Evidence:** Finding #20. `mcp_server.py` TOOLS list (lines 363-536) has 20 tools but only `add_bookmark`, `create_flow`, and `append_to_flow` are write operations.
- **Proposed Behavior:** Add 6 new tools: `delete_bookmark(bookmark_id)`, `update_bookmark(bookmark_id, title?, category?, tags?, notes?)`, `toggle_pin(bookmark_id)`, `mark_read_later(bookmark_id)`, `add_tags(bookmark_id, tags)`, `remove_tags(bookmark_id, tags)`. All wrap existing BookmarkManager methods.
- **Implementation Areas:** `mcp_server.py` -- add 6 tool registrations with Pydantic-like schemas
- **Data/API/UI Implications:** All methods already exist on BookmarkManager. MCP auth (if wired) should gate these as read-write scope.
- **Risks:** Data loss if agent deletes wrong bookmarks. Mitigate: add confirmation parameter or soft-delete default.
- **Verification:** Use Claude Desktop to ask "delete bookmark X" and verify it is removed from the library
- **Complexity:** M
- **Priority:** P1

### NF-03: Browser Extension (MV3)

- **User Problem:** Saving a bookmark requires: copy URL, switch to BOP, paste, click save. Every major competitor ships a one-click browser extension. "No extension" is the #1 complaint in self-hosted bookmark threads.
- **Evidence:** Finding #69 (browser built-ins stagnant), ROADMAP R-01 (Now tier, L effort). Every competitor review cites browser extension as essential.
- **Proposed Behavior:** Chrome MV3 + Firefox WebExtension. One-click popup with title pre-filled, category suggestion from pattern engine (shipped as bundled JSON), optional tag input. Sends to localhost REST API with auth token. Works offline (queues saves).
- **Implementation Areas:** New `extension/` directory with manifest.json, popup.html, background.js. Native messaging to localhost API. Pattern engine subset compiled to JS or shipped as JSON lookup.
- **Data/API/UI Implications:** Depends on REST API (`services/api.py`) being running. Auth token exchange flow needed. Offline queue with sync.
- **Risks:** Chrome Web Store review delays. Native messaging requires separate installer. AV false positives on native host.
- **Verification:** Install extension in Chrome, navigate to a webpage, click extension icon, see category suggestion, click Save, bookmark appears in BOP desktop app
- **Complexity:** L
- **Priority:** P1

### NF-04: GUI Surfaces for Read Later, Flows, and RSS

- **User Problem:** Three complete backend services (read_later.py, flows.py, rss_feeds.py) have zero GUI exposure. Power users must use CLI for research workflows.
- **Evidence:** Finding #19 (massive GUI-CLI parity gap), finding #78 (power user workflows center on triage/flows/PKM)
- **Proposed Behavior:** (1) Read Later sidebar section showing bookmarks sorted by age with amber/red aging indicators. (2) Flows sidebar section with flow list, click-to-expand with drag-to-reorder and inline annotation editing. (3) RSS sidebar section showing feed list with unread count.
- **Implementation Areas:** New `ui/widget_read_later.py`, `ui/widget_flows.py`, `ui/widget_rss.py`; wire into `app_mixins/app_shell.py` sidebar
- **Data/API/UI Implications:** Sidebar may become crowded -- consider collapsible sections or tab strip. Data already exists in `~/.bookmark_organizer/` JSON files.
- **Risks:** Aging indicators may cause "data anxiety" (per ROADMAP Under Consideration). Make indicators optional.
- **Verification:** Open GUI, see Read Later section in sidebar with age-colored indicators, click a flow to see its bookmarks
- **Complexity:** L
- **Priority:** P2

### NF-05: GUI Import/Export Parity

- **User Problem:** GUI import dialog only offers file-based import and browser profiles. 7 service-specific importers (Pocket, Readwise, Pinboard, Instapaper, Reddit, Matter, Zotero) are CLI-only. GUI export dialog supports 5 formats but not Obsidian, EPUB, Atom, JSON Feed, Zotero, or XBEL.
- **Evidence:** Finding #19 (GUI-CLI parity gap). `app_mixins/import_export.py` `_show_import_dialog` only shows file and browser options. `ui/workflow_selective_export.py` format list is html/json/csv/md/opml.
- **Proposed Behavior:** Add service-specific import options to the import menu. Add all 6 additional export formats to the SelectiveExportDialog.
- **Implementation Areas:** `app_mixins/import_export.py` (import menu), `ui/workflow_selective_export.py` (export dialog format list)
- **Data/API/UI Implications:** Service importers need credential/file-path input dialogs. Export formats need appropriate file extension defaults.
- **Risks:** Import dialogs for API-based services (Pocket, Readwise) need API key configuration which may confuse users.
- **Verification:** Open Import menu, see Pocket/Readwise/Pinboard options. Open Export dialog, see Obsidian/EPUB/XBEL options.
- **Complexity:** M
- **Priority:** P2

### NF-06: Help Menu with Search Syntax, Shortcuts, and About

- **User Problem:** No Help menu exists. `get_syntax_help()` returns comprehensive documentation for 15+ search filter types but is never shown. Keyboard shortcuts are undocumented in the GUI. AboutDialog is fully implemented but unreachable.
- **Evidence:** Finding #27 (no Help menu), finding #21 (About dialog unreachable), finding #31 (search syntax hidden). `app_shell.py` lines 70-97 create File, Edit, View menus only.
- **Proposed Behavior:** Add Help menu with: "Search Syntax" (shows `get_syntax_help()` text), "Keyboard Shortcuts" (shows all 13 bindings), "About" (opens existing AboutDialog).
- **Implementation Areas:** `app_mixins/app_shell.py` `_create_menu()` -- add Help menu with 3 items
- **Data/API/UI Implications:** Minimal -- all content already exists. Search syntax help could be a scrollable dialog or tooltip.
- **Risks:** None
- **Verification:** Click Help -> Search Syntax, see full filter documentation. Click Help -> About, see the 4-tab AboutDialog.
- **Complexity:** S
- **Priority:** P0

### NF-07: Batch Save API (Context Manager)

- **User Problem:** Every single-bookmark mutation (pin toggle, category change, visit recording) triggers full serialization and write of the entire bookmarks file. Bulk operations like `_send_to_category` produce N full writes for N bookmarks.
- **Evidence:** Finding #3. `managers/bookmarks.py`: `update_bookmark()` (line 143) calls `self.storage.save()` inside the lock. `selection.py` `_toggle_pin` (lines 90-97) loops calling `update_bookmark` per bookmark.
- **Proposed Behavior:** Add `BookmarkManager.batch()` context manager that suppresses per-operation saves. `with bm.batch(): ...` performs all mutations in memory, then does a single save on exit.
- **Implementation Areas:** `managers/bookmarks.py` -- add `_batch_depth` counter, `batch()` context manager; suppress save when `_batch_depth > 0`; save on exit from outermost batch
- **Data/API/UI Implications:** All callers doing bulk operations should wrap in `with self.bookmark_manager.batch():`. Existing single-mutation callers unaffected.
- **Risks:** If batch context exits abnormally, changes may be lost. Mitigate: save in `__exit__` even on exception.
- **Verification:** Time a bulk categorize of 100 bookmarks before/after -- should be ~100x faster (1 write vs 100)
- **Complexity:** M
- **Priority:** P1

### NF-08: File-Change Watching for MCP+GUI Co-existence

- **User Problem:** MCP server and GUI create independent BookmarkManager instances. Changes made via MCP are not reflected in GUI until restart, and vice versa.
- **Evidence:** Finding #10. `mcp_server.py` lines 87-100 create new managers. `app.py` lines 115-121 create separate managers.
- **Proposed Behavior:** GUI polls `master_bookmarks.json` mtime every 5 seconds (piggyback on existing `_poll_analytics` every 30s). If mtime changed, reload bookmarks and refresh the UI.
- **Implementation Areas:** `app_mixins/lifecycle.py` `_poll_analytics` -- add mtime check; `managers/bookmarks.py` -- add `reload_if_changed()` method
- **Data/API/UI Implications:** Reload must preserve current selection and scroll position. Toast notification: "Library updated by external process."
- **Risks:** Conflict if both GUI and MCP write simultaneously. JSON storage is atomic (temp + replace), so this is safe at the file level.
- **Verification:** Open GUI and run `bop add https://example.com` from CLI. Bookmark appears in GUI within 5 seconds without restart.
- **Complexity:** M
- **Priority:** P2

### NF-09: Arc Browser Importer

- **User Problem:** Arc Browser shut down May 2025, leaving users with StorableSidebar.json files. Community export tools have 1,200+ stars. BOP should be the landing pad for migrating Arc users.
- **Evidence:** Finding #73 (missing 2026 migration sources). Arc shutdown confirmed in competitive research. Community tools (arc-export, arc2zen) parse StorableSidebar.json.
- **Proposed Behavior:** `ArcBrowserImporter` class that parses Arc's `StorableSidebar.json` format, extracting URLs, titles, folders (as categories), and pinned status. CLI: `bop import-arc <path>`.
- **Implementation Areas:** New class in `importers_extra.py`; add to CLI commands dict in `cli.py`
- **Data/API/UI Implications:** Arc uses a nested JSON structure with "items" containing "data" with "tab" objects. Map Arc folders to BOP categories.
- **Risks:** Time-limited opportunity as Arc users settle elsewhere. Format may vary by Arc version.
- **Verification:** Export StorableSidebar.json from Arc, run `bop import-arc StorableSidebar.json`, verify bookmarks appear with correct categories
- **Complexity:** S
- **Priority:** P2

### NF-10: Shell Completion Scripts

- **User Problem:** BOP's CLI has 37 subcommands with no tab completion. Buku ships Bash/Fish/Zsh completion.
- **Evidence:** Finding #74 (Buku advantages worth adopting). `cli.py` uses argparse with 37 registered commands.
- **Proposed Behavior:** Generate shell completion scripts via `shtab` or `argcomplete`. Ship `completions/bop.bash`, `completions/bop.zsh`, `completions/bop.fish`. Add `bop completions` subcommand that prints the appropriate script.
- **Implementation Areas:** `pyproject.toml` -- add shtab as optional dev dependency; `cli.py` -- add `completions` subcommand; new `completions/` directory
- **Data/API/UI Implications:** None -- pure CLI UX improvement
- **Risks:** Minimal. shtab generates completions from argparse automatically.
- **Verification:** `eval "$(bop completions bash)"`, then type `bop imp<TAB>` and see `import-pocket import-readwise import-pinboard...`
- **Complexity:** S
- **Priority:** P3

### NF-11: Wallabag JSON Importer

- **User Problem:** Wallabag (12K stars) is the primary Pocket refugee destination. Users wanting to try BOP cannot import their Wallabag library.
- **Evidence:** Finding #73 (missing importers). Wallabag exports JSON/CSV/XML. Large Pocket-refugee user base.
- **Proposed Behavior:** `WallabagImporter` that parses Wallabag's JSON export format (title, url, content, tags, is_archived, is_starred, created_at). Maps is_starred to pinned, tags to BOP tags.
- **Implementation Areas:** New class in `importers_extra.py`; add to CLI commands in `cli.py`
- **Data/API/UI Implications:** Wallabag JSON includes full article content -- optionally store as extracted text.
- **Risks:** Format may vary between Wallabag versions.
- **Verification:** Export from Wallabag, run `bop import-wallabag export.json`, verify bookmarks with correct tags and pin status
- **Complexity:** S
- **Priority:** P3

### NF-12: Embedding Model Tier Selection in Settings

- **User Problem:** First-time embedding model download is a friction point. Users don't know which model to choose for their hardware.
- **Evidence:** Finding #72 (embedding landscape has advanced). `services/embeddings.py` supports configurable models via fastembed.
- **Proposed Behavior:** AI Settings dialog adds an "Embedding Model" section with three tiers: "Fast/Small" (model2vec, 8-30MB), "Balanced" (bge-m3, 200-500MB), "Best Quality" (jina-v5-0.6B, 500MB-1GB). Shows download progress bar on first use.
- **Implementation Areas:** `app_mixins/ai_settings.py` -- add model tier picker; `services/embeddings.py` -- add model download progress callback
- **Data/API/UI Implications:** Model files stored in `~/.bookmark_organizer/embeddings/models/`. Progress callback via Tkinter `after()`.
- **Risks:** Large model downloads may fail. Need retry and resume support.
- **Verification:** Open AI Settings, select "Balanced" tier, see download progress, then run semantic search and get results
- **Complexity:** M
- **Priority:** P2

---

## Existing Feature Improvements

### EI-01: Wire MCP Authentication (Finding #37)

- **Current Behavior:** `MCPTokenManager` class exists in `services/mcp_auth.py` with token creation, validation, and scope checking. `mcp_server.py` never imports or calls it. All 20 tools accept any invocation from any MCP client.
- **Problem:** Any MCP client can add arbitrary bookmarks, export the entire library, create flows, and trigger AI API calls without authentication.
- **Change:** Import `MCPTokenManager` in `mcp_server.py`. Add middleware/decorator that validates a token from request context before executing any tool. Reject unauthorized calls with error response.
- **Code Locations:** `mcp_server.py` (add auth check), `services/mcp_auth.py` (already implemented)
- **Backward Compat:** MCP clients that previously connected without auth will need to provide a token. Add a `--no-auth` flag for local development.
- **Verification:** Start MCP server, attempt to call `add_bookmark` without a token, receive auth error. Generate token via `bop mcp-token create`, provide it, call succeeds.
- **Complexity:** M
- **Priority:** P0

### EI-02: Safe XML Parsing for OPML/XBEL Importers (Finding #38)

- **Current Behavior:** `importers.py` line 507 uses `ET.parse(filepath).getroot()` and `io_formats/xbel.py` line 129 uses `ET.fromstring(xml_bytes)` directly, without defusedxml.
- **Problem:** Malicious OPML/XBEL files can trigger XXE expansion to read local files or billion-laughs DoS.
- **Change:** Apply the same defusedxml pattern from `rss_feeds.py` (lines 21-30): try `import defusedxml.ElementTree`, fall back to custom parser with `parser.entity = {}`.
- **Code Locations:** `importers.py` (OPML import method), `io_formats/xbel.py` (import method)
- **Backward Compat:** No change in behavior for well-formed files.
- **Verification:** Create a malicious OPML with entity expansion, import it, verify it is rejected or safely parsed without expanding entities.
- **Complexity:** S
- **Priority:** P0

### EI-03: Sanitize LocalArchiver HTML Output (Finding #40)

- **Current Behavior:** `web_tools.py` line 253 embeds raw fetched HTML into archive file via f-string `f"...{page_text}"` with no sanitization.
- **Problem:** Archived HTML preserves all scripts, iframes, and event handlers. Opening in a browser executes them in file:// origin.
- **Change:** Strip `<script>` tags and event handler attributes from page_text using BeautifulSoup (already a dependency). Add CSP meta tag: `<meta http-equiv="Content-Security-Policy" content="script-src 'none'">`.
- **Code Locations:** `services/web_tools.py` `LocalArchiver.archive_page()` (line 253)
- **Backward Compat:** Existing archives unchanged (re-archive to fix). New archives will be script-free.
- **Verification:** Archive a page with JavaScript (e.g., any SPA), open the archive in a browser, verify no scripts execute.
- **Complexity:** S
- **Priority:** P0

### EI-04: Sync Version Strings (Finding #14)

- **Current Behavior:** `constants.py` and `pyproject.toml` say 6.4.0. PyInstaller spec says 6.2.1. CLAUDE.md says v6.1.0 throughout. `export_html` says "v4". `about.py` says Python 3.8+. README says Python 3.8+.
- **Problem:** Built binaries report wrong version. Documentation is stale and misleading.
- **Change:** Update all 6 locations to 6.4.0 and Python 3.10+: `packaging/bookmark_organizer.spec`, `packaging/version_info.txt`, `CLAUDE.md`, `managers/bookmarks.py` export_html comment, `ui/about.py` credits tab, `README.md` requirements section.
- **Code Locations:** See above
- **Backward Compat:** No functional change
- **Verification:** `grep -r "6.2.1\|v6.1\|3\.8" --include="*.py" --include="*.md" --include="*.spec"` returns zero matches
- **Complexity:** S
- **Priority:** P0

### EI-05: Replace Hardcoded Segoe UI Fonts with FONTS System (Finding #52)

- **Current Behavior:** 35+ widget declarations across 12 UI files use `font=('Segoe UI', N, ...)` bypassing the centralized FONTS system in `ui/foundation.py`.
- **Problem:** On macOS (no Segoe UI), these widgets fall back to an ugly substitute. On Linux, same issue.
- **Change:** Replace all hardcoded `font=('Segoe UI', N)` with `FONTS.body()`, `FONTS.heading()`, or `FONTS.custom(N)` as appropriate. Import FONTS from `ui.foundation` in each affected file.
- **Code Locations:** `ui/management_dialogs.py`, `ui/secondary_views.py`, `ui/widget_analytics.py`, `ui/widget_dashboard_panel.py`, `ui/widget_bookmark_editor.py`, `ui/workflow_detail_panel.py`, `ui/workflow_bulk_tags.py`, `ui/workflow_quick_add.py`, `ui/workflow_smart_filters.py`, `ui/widget_theme_dialogs.py`, `ui/about.py`, `app_mixins/ai_menu_data.py`
- **Backward Compat:** No visual change on Windows. Improved rendering on macOS/Linux.
- **Verification:** Run on macOS or Linux, verify all text renders in the system-appropriate font family
- **Complexity:** M
- **Priority:** P1

### EI-06: Theme-Aware DependencyCheckDialog (Finding #51)

- **Current Behavior:** `ui/dependencies.py` uses ~40 hardcoded hex colors (#1e1e2e, #313244, #cdd6f4, etc.) -- always Catppuccin Mocha regardless of active theme.
- **Problem:** On light themes (Studio, GitHub Light), a dark dialog is jarring and visually broken.
- **Change:** Replace all hardcoded colors with `get_theme()` token lookups: `theme.bg_primary`, `theme.bg_secondary`, `theme.text_primary`, etc. Add Escape binding and `apply_window_chrome()`.
- **Code Locations:** `ui/dependencies.py` (241 lines, ~35 color references)
- **Backward Compat:** No change on Catppuccin Mocha theme. Correct rendering on all other themes.
- **Verification:** Switch to GitHub Light theme, trigger dependency check dialog, verify it renders in light colors
- **Complexity:** M
- **Priority:** P1

### EI-07: Remove AI Reference from About Dialog Credits (Finding #32)

- **Current Behavior:** `about.py` line 290 contains "Developed with assistance from Claude (Anthropic)".
- **Problem:** Violates the repo's no-AI-references rule in CLAUDE.md.
- **Change:** Remove the Claude/Anthropic line from the credits tab.
- **Code Locations:** `ui/about.py` line 290
- **Backward Compat:** No functional change
- **Verification:** `grep -i "claude\|anthropic" bookmark_organizer_pro/ui/about.py` returns zero matches
- **Complexity:** S
- **Priority:** P0

### EI-08: Fix About Dialog Feature Claims (Finding #26)

- **Current Behavior:** Features tab lists "System Tray: Quick access from tray icon" and "Categories: Nested hierarchy with drag-and-drop" -- both removed in v6.3.0 (R-46).
- **Problem:** False feature claims visible to users.
- **Change:** Remove the System Tray feature entry. Change drag-and-drop description to "Categories: Nested hierarchy with click-to-manage".
- **Code Locations:** `ui/about.py` lines 202-215
- **Backward Compat:** No functional change
- **Verification:** Open About dialog Features tab, verify no mention of system tray or drag-and-drop
- **Complexity:** S
- **Priority:** P1

### EI-09: Extend Bookmark Editor with Notes, Description, Pin (Finding #33)

- **Current Behavior:** BookmarkEditorDialog only exposes URL, title, category, and tags. 20+ Bookmark model fields are inaccessible from GUI.
- **Problem:** Users cannot set notes, description, read-later status, or pin status without CLI.
- **Change:** Add Text widget for notes (height=4), Entry for description, Checkbutton for pin, Checkbutton for read-later. Wrap content in scrollable frame.
- **Code Locations:** `ui/widget_bookmark_editor.py`, `app_mixins/bookmark_crud.py`
- **Backward Compat:** Existing bookmarks unchanged. New fields are optional.
- **Verification:** Open bookmark editor (Ctrl+E), see notes and pin fields, edit them, verify they persist after save
- **Complexity:** M
- **Priority:** P2

### EI-10: Add Escape-to-Close on All Modal Dialogs (Finding #54)

- **Current Behavior:** 8+ modal dialogs lack Escape key binding: BulkTagEditorDialog, EmojiPicker, AnalyticsDashboard, ThemeSelectorDialog, AI Categorization Live, AI Tag Suggestions Live, AI Summaries Live, AI Statistics.
- **Problem:** Users cannot dismiss modal dialogs with Escape, violating standard desktop UX.
- **Change:** Add `self.bind('<Escape>', lambda e: self.destroy())` (or the existing cancel handler for AI dialogs).
- **Code Locations:** `ui/workflow_bulk_tags.py`, `ui/workflow_emoji_picker.py`, `ui/widget_analytics.py`, `ui/widget_theme_dialogs.py`, `app_mixins/ai_categorization.py`, `app_mixins/ai_enrichment.py`, `app_mixins/ai_menu_data.py`
- **Backward Compat:** No change -- adds behavior that was missing
- **Verification:** Open each dialog, press Escape, verify it closes
- **Complexity:** S
- **Priority:** P1

### EI-11: Expand Command Palette (Finding #28)

- **Current Behavior:** Command palette registers only 18 commands of 40+ available actions.
- **Problem:** Users cannot discover most actions through the palette.
- **Change:** Add at least 15 more commands: Toggle Pin, Copy URL, Delete Selected, Mark as Broken, all Tools menu items (Flatten, Clear Categories, Clear Tags, Backup, Check Links, Redownload Favicons), AI Provider Settings, About, Search Syntax Help.
- **Code Locations:** `app_mixins/command_palette.py` (lines 14-34, fixed command list)
- **Backward Compat:** Additive only
- **Verification:** Press Ctrl+P, type "pin", see "Toggle Pin" command. Type "about", see "About" command.
- **Complexity:** M
- **Priority:** P2

### EI-12: Deduplicate Settings Gear / Tools Menu (Finding #30)

- **Current Behavior:** "Manage Categories", "Backup Now", and "Flatten All Folders" appear in both the Settings gear menu and the Tools menu. "AI Provider Settings" appears in Settings gear, AI menu, and command palette.
- **Problem:** Decision paralysis from duplicate menu items.
- **Change:** Settings gear: only configuration items (AI settings, themes, preferences). Tools: only maintenance actions (backup, flatten, clear, check links, redownload favicons). Remove duplicates from one or the other.
- **Code Locations:** `app_mixins/tools.py` `_show_settings_menu` (lines 29-45) and `_show_tools_menu` (lines 47-81)
- **Backward Compat:** Actions remain accessible via the surviving menu
- **Verification:** Click Settings gear, then Tools. No items appear in both menus.
- **Complexity:** S
- **Priority:** P2

### EI-13: REST API Auth on GET Endpoints (Finding #49)

- **Current Behavior:** `api.py` `do_GET` handler never calls `_check_auth()`. All GET endpoints (/bookmarks, /search, /stats, /categories, /tags) are unauthenticated.
- **Problem:** Any local process can enumerate the user's entire bookmark collection.
- **Change:** Add `_check_auth()` call at the top of `do_GET()`, matching `do_POST`/`do_DELETE`.
- **Code Locations:** `services/api.py` `do_GET` method (line 86)
- **Backward Compat:** Breaking for unauthenticated clients. Add deprecation warning first or a `--public-reads` flag.
- **Verification:** `curl http://localhost:8765/bookmarks` returns 401 without token, 200 with token
- **Complexity:** S
- **Priority:** P1

### EI-14: Persist Search History and Expose in GUI (Finding #23)

- **Current Behavior:** `SearchEngine._search_history` (list) and `_saved_searches` (dict) are in-memory only. Lost on app close. Never surfaced in GUI.
- **Problem:** Users cannot access search history or save frequent searches.
- **Change:** Persist search history to `settings.json`. Show a dropdown when search bar is focused. Add "Save this search" option. Show saved searches as sidebar quick filters.
- **Code Locations:** `search.py` (persist/load methods), `app_mixins/filters.py` (search bar focus handler), `app_mixins/app_shell.py` (sidebar)
- **Backward Compat:** Additive -- new data in settings.json
- **Verification:** Search for "python", close app, reopen, focus search bar, see "python" in history dropdown
- **Complexity:** M
- **Priority:** P2

### EI-15: Remove Dead UI View Classes (Finding #7)

- **Current Behavior:** KanbanView, TimelineView, ReadingListView, TagCloudView (~666 lines) in `ui/secondary_views.py` are defined and exported but never instantiated. `_populate_grid_view` and `_load_next_grid_batch` are pass stubs.
- **Problem:** 670+ lines of dead code adding import weight and maintenance burden.
- **Change:** Remove the 4 unused classes from `secondary_views.py`. Remove their exports from `ui/__init__.py`. Remove the stub methods from `app_mixins/bookmarks.py`.
- **Code Locations:** `ui/secondary_views.py`, `ui/__init__.py`, `app_mixins/bookmarks.py` (lines 207-213)
- **Backward Compat:** No consumer exists -- safe to remove
- **Verification:** `grep -r "KanbanView\|TimelineView\|ReadingListView\|TagCloudView" bookmark_organizer_pro/` returns zero matches
- **Complexity:** S
- **Priority:** P1

### EI-16: Theme-Aware Title Bar (Finding #58)

- **Current Behavior:** `set_dark_title_bar()` in `desktop_bootstrap.py` unconditionally sets DwmSetWindowAttribute to value=1 (dark). Light themes get a dark title bar.
- **Problem:** Dark title bar clashes with Studio and GitHub Light theme content areas.
- **Change:** Accept an `is_dark` parameter. When `is_dark=False`, pass `value=0` for light title bar. Wire through `apply_window_chrome()`.
- **Code Locations:** `desktop_bootstrap.py` (lines 183-194), `launcher.py` (line 87)
- **Backward Compat:** Dark themes unchanged. Light themes get correct light title bar.
- **Verification:** Switch to GitHub Light theme, verify title bar is light. Switch to Dracula, verify title bar is dark.
- **Complexity:** M
- **Priority:** P2

### EI-17: Windows ACL on Sensitive Files (Findings #39, #41, #42)

- **Current Behavior:** `ai_config.json`, `api_token.txt`, and `mcp_tokens.json` have no Windows ACL restriction. The `if os.name != 'nt'` guard skips file permission hardening on Windows.
- **Problem:** Any local process can read API keys and auth tokens on the primary target platform.
- **Change:** After writing each file on Windows, call `icacls <file> /inheritance:r /grant:r "%USERNAME%":F` to restrict to current user only.
- **Code Locations:** `ai.py` (line 225), `services/api.py` (line 37), `services/mcp_auth.py` (line 55-64)
- **Backward Compat:** Existing files need one-time ACL update on next write
- **Verification:** Write a config file, check with `icacls` that only current user has access
- **Complexity:** S
- **Priority:** P1

---

## Reliability, Security, Privacy, and Data Safety

### Critical

1. **MCP server zero-auth (finding #37):** `mcp_server.py` exposes 20 tools including `add_bookmark`, `create_flow`, `export_to_obsidian`, `export_zip` with no authentication. `MCPTokenManager` in `services/mcp_auth.py` is complete but never imported by the server. Any MCP client can modify the library and trigger AI API calls.

### High Severity

2. **XXE in OPML/XBEL import (finding #38):** `importers.py` line 507 uses `ET.parse()` directly. `io_formats/xbel.py` line 129 uses `ET.fromstring()` directly. Neither uses defusedxml. The XBEL `b'<!ENTITY'` string check is trivially bypassable. `rss_feeds.py` has the correct pattern (lines 21-30) that should be copied.

3. **Stored XSS in LocalArchiver (finding #40):** `web_tools.py` line 253 embeds raw fetched HTML into archive via `f"...{page_text}"`. No script stripping, no CSP header. Opening archived HTML in browser executes all embedded JavaScript in file:// origin.

4. **API keys in plaintext on Windows (finding #39):** `ai.py` line 225 skips `os.fchmod` on Windows (`if os.name != 'nt'`). Keys stored in `ai_config.json` readable by any local process. Keyring fallback exists but `keyring` is optional and commonly unavailable.

5. **Nested lock deadlock risk (finding #1):** `BookmarkManager` holds its RLock and calls `StorageManager.save()` which acquires a separate `threading.Lock`. If any code path acquires StorageManager lock first, deadlock occurs. StorageManager's Lock is non-reentrant.

6. **Background thread data races (finding #2):** AI categorization (`ai_categorization.py` lines 260-318), link checking, and import workers directly mutate Bookmark fields in background threads while the UI thread reads them.

### Medium Severity

7. **Ollama installer pipes remote script to bash (finding #43):** `ollama_manager.py` line 213 runs `curl -fsSL https://ollama.com/install.sh | sh` with no checksum verification.

8. **Bookmark URLs logged with sensitive query params (finding #44):** Multiple modules log full URLs that may contain auth tokens, session IDs, or API keys in query parameters.

9. **SSRF allow-list accepts unvalidated regex (finding #45):** `url_utils.py` `set_ssrf_allow_list()` accepts arbitrary regex patterns. A pattern like `.*` disables SSRF protection entirely.

10. **REST API GET endpoints unauthenticated (finding #49):** Any local process can enumerate the full bookmark library without a token.

11. **API token file unprotected on Windows (finding #41):** `api.py` line 37 skips `os.chmod` on Windows.

12. **MCP tokens stored in plaintext JSON (finding #42):** `mcp_auth.py` `_save()` writes tokens without file permissions. Should hash tokens (store SHA-256, validate by hashing input).

### Low Severity

13. **Import backup file grows unboundedly (finding #9):** `import_export.py` `_save_import_backup()` has no size limit, no rotation, and non-atomic writes.

14. **BackupScheduler lacks SHA-256 hashes (finding #46):** `local_state.py` line 118 creates backups without hash files, unlike `StorageManager._create_backup()`.

15. **Favicon fetching leaks domains to 7 third-party services (finding #48):** `favicons.py` lines 46-54 send each domain to Google, DuckDuckGo, FaviconKit, Favicone, Icon.horse without opt-out.

16. **Encryption entirely optional with no GUI toggle (finding #47):** Most users will never discover or enable encryption.

17. **Favicon shutdown leaves partial files (finding #16):** `shutdown(wait=False)` in `favicons.py` line 453 abandons in-flight downloads.

---

## UX, Accessibility, and Trust

### Onboarding

1. **First-time user gets minimal guidance (finding #29):** Only the privacy banner and empty-state CTA exist. No tutorial, no feature walkthrough, no "What's New" panel. After first bookmark is added, all guidance disappears.

2. **Drag-and-drop area is misleading (finding #24):** `DragDropImportArea` says "Drop files here or click to browse" but `_try_enable_window_dnd()` is a no-op (pass). Only click-to-browse works. Either implement DnD via tkinterdnd2 or change the label.

### States and Feedback

3. **Search syntax not discoverable (finding #31):** Search bar tooltip mentions 5 of 15+ filter types. Full documentation exists in `get_syntax_help()` but is never shown.

4. **Single-item View menu is confusing (finding #22):** View menu has only "List View" with no alternative after grid view removal. The menu item is a no-op.

### Destructive Actions

5. **72 silent exception swallows (finding #6):** `except Exception: pass` in 34 files including data-critical paths (importers, saves, loads). Failures are invisible.

### Settings and Configuration

6. **Duplicate menu items (finding #30):** Settings gear and Tools menu share 3 items, AI settings appears in 3 places.

7. **Python version claims inconsistent (finding #25):** README, about.py, runtime.py say 3.8+; pyproject.toml requires 3.10+.

### Accessibility

8. **No screen reader support (finding #59):** Treeview has no accessible name. ModernButton is tk.Frame (invisible to MSAA). Custom widgets lack role metadata.

9. **High Contrast theme WCAG failures (finding #60):** White text (#ffffff) on pure green (#00ff00) `accent_success` has ~1.4:1 contrast ratio. `Success.TButton` foreground hardcoded to #ffffff in `style_manager.py` line 172 instead of using `readable_text_on()`.

10. **Fixed-geometry dialogs overflow at high DPI (finding #62):** BookmarkEditorDialog (600x700), QuickAddDialog (560x420), and others have fixed geometry with no scroll fallback.

### Theme Consistency

11. **DependencyCheckDialog ignores theme (finding #51):** 40 hardcoded Catppuccin Mocha colors.

12. **35+ hardcoded Segoe UI references (finding #52):** Breaks macOS/Linux font rendering.

13. **Live theme refresh destroys semantic styling (finding #53):** `_apply_theme_live` resets all Labels to bg_primary.

14. **Privacy banner hardcoded colors (finding #55):** `launcher.py` uses bg='#0f766e', fg='#ffffff'.

15. **Focus color hardcoded #5b8cff (finding #57):** `make_keyboard_activatable` in `tk_interactions.py` uses hardcoded blue that clashes with Monokai, Gruvbox, High Contrast.

---

## Architecture and Maintainability

### Module Improvements

1. **Lazy imports in `__init__.py` (finding #5):** Top-level package imports CLI, all 87+ service symbols, and 186 names. Every entry point pays full import cost. Use `__getattr__` lazy loading for heavyweight subsystems.

2. **Lazy imports in `ui/__init__.py` (finding #17):** Imports from 18 submodules, pulling the entire widget toolkit on any UI reference.

3. **Externalize `default_categories.py` (finding #12):** 5,768 lines of inline Python data should be a JSON file. Enables user customization without code changes.

### Refactor Candidates

4. **BookmarkManager God class (finding #8):** 933 lines combining CRUD, import, export, search, stats, dedup, health scoring. Extract BookmarkExporter, BookmarkImporter, AnalyticsService.

5. **Mixin interface contracts (finding #4):** 15-class composition with pure implicit coupling. Add Protocol or ABC declaring required interface per mixin.

6. **Mutable references from get_all_bookmarks (finding #13):** Returns live Bookmark objects. Callers can mutate without triggering save. Consider frozen dataclass or defensive copies.

7. **Nested lock removal (finding #1):** Remove StorageManager's own lock (let BookmarkManager be sole synchronization point), or upgrade to RLock with documented ordering.

### Test Gaps

8. **27 of 35 service modules untested (finding #11):** Major untested: `ai_tools` (683 lines), `web_tools` (749 lines), `favicons` (594 lines), `snapshot`, `dead_link_scanner`, `hybrid_search`, `vector_store`, `rag_chat`, `nl_query`, `organization` (551 lines).

9. **Zero UI tests:** Entire UI layer (40 files) has no test coverage.

10. **Zero concurrency tests:** 15+ threading patterns with no concurrent test coverage despite known data race issues.

### Doc Gaps

11. **CLAUDE.md stale at v6.1.0:** Says 37 tests (actual: 255), 15 MCP tools (actual: 20), missing services added since v6.1.

12. **ROADMAP.md inconsistency:** Body checkmarks contradict bottom-tier open-square markers for 30+ items. Bottom tier lists show R-07, R-08, R-09, R-10, R-12, R-13, R-24, R-25, R-27, R-30, R-35, R-37, R-45, R-49 as open but they are marked ✅ in the body tables.

---

## Prioritized Roadmap

### P0 -- Ship Before Next Release

- [ ] P0 - Wire MCP authentication enforcement
  - Why: 20 tools exposed with zero auth, including data-mutating operations
  - Evidence: Finding #37. `mcp_server.py` never imports `MCPTokenManager`. Grep for `mcp_auth` in `mcp_server.py` returns zero.
  - Touches: `mcp_server.py`, `services/mcp_auth.py`
  - Acceptance: All tool invocations require valid token; unauthenticated calls return error
  - Verify: Start MCP server, call `add_bookmark` without token, get auth error

- [ ] P0 - Fix XXE vulnerability in OPML/XBEL importers
  - Why: User-supplied XML files can trigger entity expansion attacks
  - Evidence: Finding #38. `importers.py` line 507 uses `ET.parse()` without defusedxml
  - Touches: `importers.py`, `io_formats/xbel.py`
  - Acceptance: OPML/XBEL import uses defusedxml when available, custom parser fallback with entity expansion disabled
  - Verify: Import a file containing `<!ENTITY xxe SYSTEM "file:///etc/passwd">`, verify it is rejected or neutralized

- [ ] P0 - Sanitize LocalArchiver HTML output
  - Why: Stored XSS -- raw fetched HTML embedded in archive files executes in browser
  - Evidence: Finding #40. `web_tools.py` line 253 embeds `{page_text}` without sanitization
  - Touches: `services/web_tools.py`
  - Acceptance: Archived HTML has script tags stripped and CSP meta tag blocking script execution
  - Verify: Archive a page with JS, open archive in browser, confirm no script execution

- [ ] P0 - Sync all version strings to 6.4.0
  - Why: PyInstaller spec at 6.2.1 means built binaries report wrong version
  - Evidence: Finding #14. `packaging/bookmark_organizer.spec` hardcodes 6.2.1
  - Touches: `packaging/bookmark_organizer.spec`, `packaging/version_info.txt`, `CLAUDE.md`, `managers/bookmarks.py` (export_html v4 comment), `ui/about.py`, `README.md`, `utils/runtime.py`
  - Acceptance: All version strings say 6.4.0; all Python version claims say 3.10+
  - Verify: `grep -rn "6\.2\.1\|v6\.1\|3\.8" --include="*.py" --include="*.md" --include="*.spec"` returns zero

- [ ] P0 - Remove AI reference from About dialog credits
  - Why: Violates repo's no-AI-references rule
  - Evidence: Finding #32. `about.py` line 290: "Developed with assistance from Claude (Anthropic)"
  - Touches: `ui/about.py`
  - Acceptance: No mention of Claude, Anthropic, or any AI tool in committed source
  - Verify: `grep -ri "claude\|anthropic" bookmark_organizer_pro/ui/about.py` returns zero

- [ ] P0 - Add Help menu with Search Syntax, Shortcuts, About
  - Why: No Help menu exists; comprehensive search syntax help and full About dialog are unreachable
  - Evidence: Findings #21, #27. `app_shell.py` creates only File/Edit/View menus
  - Touches: `app_mixins/app_shell.py`
  - Acceptance: Help menu with 3 items; About dialog opens; search syntax help displayed
  - Verify: Click Help -> About, see 4-tab dialog. Click Help -> Search Syntax, see full filter docs.

### P1 -- High Priority

- [ ] P1 - Replace 35+ hardcoded Segoe UI font references with FONTS system
  - Why: Breaks cross-platform rendering on macOS and Linux
  - Evidence: Finding #52. 12 UI files with hardcoded `font=('Segoe UI', ...)`
  - Touches: 12 files in `ui/` and `app_mixins/ai_menu_data.py`
  - Acceptance: Zero instances of hardcoded 'Segoe UI' in any .py file
  - Verify: `grep -rn "Segoe UI" bookmark_organizer_pro/ --include="*.py"` returns zero

- [ ] P1 - Theme-aware DependencyCheckDialog
  - Why: 40 hardcoded Catppuccin Mocha colors ignore active theme
  - Evidence: Finding #51. `ui/dependencies.py` uses ~35 hardcoded hex colors
  - Touches: `ui/dependencies.py`
  - Acceptance: Dialog renders correctly in all 11 themes
  - Verify: Switch to GitHub Light, trigger dependency check, verify light colors

- [ ] P1 - Add Escape-to-close on 8 modal dialogs
  - Why: Standard desktop UX expectation
  - Evidence: Finding #54. 8 grab_set() dialogs lack Escape binding
  - Touches: `ui/workflow_bulk_tags.py`, `ui/workflow_emoji_picker.py`, `ui/widget_analytics.py`, `ui/widget_theme_dialogs.py`, `app_mixins/ai_categorization.py`, `app_mixins/ai_enrichment.py`, `app_mixins/ai_menu_data.py`
  - Acceptance: Pressing Escape closes each dialog
  - Verify: Open each dialog, press Escape, verify it closes

- [ ] P1 - Add batch save context manager to BookmarkManager
  - Why: Bulk operations produce N full file writes for N bookmarks
  - Evidence: Finding #3. `update_bookmark()` calls `storage.save()` per mutation
  - Touches: `managers/bookmarks.py`
  - Acceptance: Bulk categorize 100 bookmarks produces 1 write, not 100
  - Verify: Time bulk categorize before/after; verify single file write via log

- [ ] P1 - Add MCP write tools (delete, update, tag mutation)
  - Why: MCP server is read-heavy; agents cannot curate collections
  - Evidence: Finding #20. Only `add_bookmark`, `create_flow`, `append_to_flow` are write operations
  - Touches: `mcp_server.py`
  - Acceptance: 6 new tools: delete_bookmark, update_bookmark, toggle_pin, mark_read_later, add_tags, remove_tags
  - Verify: Use MCP client to delete a bookmark, verify it is removed

- [ ] P1 - Remove 4 dead UI view classes (~670 lines)
  - Why: KanbanView, TimelineView, ReadingListView, TagCloudView are never instantiated
  - Evidence: Finding #7. Grep for class names shows only definitions and exports, zero usage
  - Touches: `ui/secondary_views.py`, `ui/__init__.py`, `app_mixins/bookmarks.py`
  - Acceptance: Classes removed; stub methods removed; imports cleaned
  - Verify: `grep -r "KanbanView\|TimelineView\|ReadingListView\|TagCloudView" bookmark_organizer_pro/` returns zero

- [ ] P1 - Fix About dialog false feature claims
  - Why: Features tab lists System Tray and drag-and-drop that were removed in v6.3.0
  - Evidence: Finding #26. ROADMAP R-46 confirms removal
  - Touches: `ui/about.py` lines 202-215
  - Acceptance: No mention of system tray or drag-and-drop in features list
  - Verify: Open About dialog Features tab, verify accurate feature list

- [ ] P1 - Windows ACL restriction on sensitive files
  - Why: API keys, auth tokens, MCP tokens unprotected on primary platform
  - Evidence: Findings #39, #41, #42. `if os.name != 'nt'` skips permissions
  - Touches: `ai.py`, `services/api.py`, `services/mcp_auth.py`
  - Acceptance: Sensitive files restricted to current user on Windows
  - Verify: Write a config file, run `icacls <file>`, verify only current user has access

- [ ] P1 - Require Bearer token auth on REST API GET endpoints
  - Why: Entire bookmark library readable by any local process without auth
  - Evidence: Finding #49. `do_GET` never calls `_check_auth()`
  - Touches: `services/api.py`
  - Acceptance: All endpoints require Bearer token
  - Verify: `curl http://localhost:8765/bookmarks` returns 401 without token

- [ ] P1 - Use readable_text_on() for button foregrounds
  - Why: Hardcoded #ffffff breaks on light-accent themes (Gruvbox, High Contrast success)
  - Evidence: Finding #63. `style_manager.py` lines 156, 172, 186 hardcode white
  - Touches: `ui/style_manager.py`
  - Acceptance: Button text readable on all themes
  - Verify: Switch to Gruvbox Dark, verify Primary/Success/Danger buttons have readable text

### P2 -- Next Priority

- [ ] P2 - GUI chat panel for RAG search
  - Why: Most differentiating feature (chat with bookmarks) is GUI-invisible
  - Evidence: Finding #70. `rag_chat.py` is complete; CLI-only
  - Touches: New `ui/widget_chat_panel.py`, new mixin, `app_mixins/app_shell.py`
  - Acceptance: Users can ask questions about their bookmarks from the GUI and get cited answers
  - Verify: Open chat panel, type "what articles did I save about Python?", get cited response

- [ ] P2 - GUI surfaces for Read Later, Flows, RSS
  - Why: Three complete backend services have zero GUI exposure
  - Evidence: Finding #19 (GUI-CLI parity gap), finding #78 (power user workflows)
  - Touches: New UI widgets, `app_mixins/app_shell.py` sidebar
  - Acceptance: Read Later section in sidebar; Flows section in sidebar; RSS section in sidebar
  - Verify: See read-later bookmarks with age indicators; click a flow to see its contents

- [ ] P2 - GUI import/export parity
  - Why: 7 importers and 6 export formats are CLI-only
  - Evidence: Finding #19. `import_export.py` only shows file/browser import
  - Touches: `app_mixins/import_export.py`, `ui/workflow_selective_export.py`
  - Acceptance: Import menu shows Pocket/Readwise/Pinboard options; Export dialog shows Obsidian/EPUB/XBEL
  - Verify: Open Import menu, see service-specific options. Open Export dialog, see 11 format options.

- [ ] P2 - Expand command palette to 35+ commands
  - Why: Only 18 of 40+ actions registered
  - Evidence: Finding #28. `command_palette.py` has a fixed 18-command list
  - Touches: `app_mixins/command_palette.py`
  - Acceptance: All menu items and toolbar actions accessible via palette
  - Verify: Ctrl+P, type "pin" -> "Toggle Pin". Type "about" -> "About".

- [ ] P2 - Persist search history and add search bar dropdown
  - Why: Search history lost on app close; saved searches never surfaced
  - Evidence: Finding #23. In-memory only, never persisted
  - Touches: `search.py`, `app_mixins/filters.py`
  - Acceptance: Search history survives app restart; dropdown on focus
  - Verify: Search "python", close app, reopen, focus search bar, see "python" in dropdown

- [ ] P2 - File-change watching for MCP+GUI co-existence
  - Why: MCP and GUI operate on independent in-memory copies
  - Evidence: Finding #10. `mcp_server.py` and `app.py` create separate managers
  - Touches: `app_mixins/lifecycle.py`, `managers/bookmarks.py`
  - Acceptance: Changes via MCP/CLI appear in GUI within 5 seconds
  - Verify: Run `bop add https://example.com`, bookmark appears in GUI without restart

- [ ] P2 - Theme-aware title bar (light/dark)
  - Why: Dark title bar forced on light themes
  - Evidence: Finding #58. `set_dark_title_bar()` always sets value=1
  - Touches: `desktop_bootstrap.py`, `launcher.py`
  - Acceptance: Light themes get light title bar on Windows
  - Verify: Switch to GitHub Light, verify title bar matches

- [ ] P2 - Extend bookmark editor with notes, description, pin fields
  - Why: 20+ Bookmark model fields inaccessible from GUI
  - Evidence: Finding #33. Editor only shows URL/title/category/tags
  - Touches: `ui/widget_bookmark_editor.py`, `app_mixins/bookmark_crud.py`
  - Acceptance: Notes, description, pin, read-later editable in dialog
  - Verify: Open editor (Ctrl+E), see notes field, edit it, verify persistence

### P3 -- Later

- [ ] P3 - Lazy imports in package __init__.py
  - Why: Every import triggers loading CLI, all services, 186 symbols
  - Evidence: Finding #5. `__init__.py` imports BookmarkCLI (pulls requests)
  - Touches: `__init__.py`
  - Acceptance: `from bookmark_organizer_pro import Bookmark` loads in <100ms
  - Verify: `python -c "import time; t=time.time(); from bookmark_organizer_pro import Bookmark; print(time.time()-t)"`

- [ ] P3 - Externalize default_categories.py to JSON
  - Why: 5,768 lines of inline data; pattern updates require code changes
  - Evidence: Finding #12. Largest file in codebase
  - Touches: `core/default_categories.py`, new `data/categories.json`
  - Acceptance: Categories loaded from JSON at runtime; Python file removed
  - Verify: App starts with JSON categories; `bop categorize` works correctly

- [ ] P3 - Arc Browser importer
  - Why: Arc died May 2025; catch migrating users
  - Evidence: Finding #73. Community tools have 1,200+ stars
  - Touches: `importers_extra.py`, `cli.py`
  - Acceptance: `bop import-arc StorableSidebar.json` imports bookmarks with correct categories
  - Verify: Export from Arc, import into BOP, verify bookmark count and categories

- [ ] P3 - Wallabag JSON importer
  - Why: Primary Pocket refugee destination (12K stars)
  - Evidence: Finding #73. Wallabag exports JSON/CSV/XML
  - Touches: `importers_extra.py`, `cli.py`
  - Acceptance: `bop import-wallabag export.json` imports with tags and pin status
  - Verify: Export from Wallabag, import, verify tags preserved

- [ ] P3 - Shell completion scripts
  - Why: 37 CLI subcommands with no tab completion
  - Evidence: Finding #74. Buku ships Bash/Fish/Zsh completion
  - Touches: `pyproject.toml`, `cli.py`, new `completions/` dir
  - Acceptance: `eval "$(bop completions bash)"` enables tab completion
  - Verify: Type `bop imp<TAB>`, see import subcommands

- [ ] P3 - Embedding model tier selection in AI settings
  - Why: First-time model download is a friction point
  - Evidence: Finding #72. Three clear tiers: Fast/Balanced/Best
  - Touches: `app_mixins/ai_settings.py`, `services/embeddings.py`
  - Acceptance: AI Settings shows model tiers with download progress
  - Verify: Select "Balanced", see download progress, then semantic search works

---

## Quick Wins

1. **Fix export_html version comment** -- Replace hardcoded "v4" with `APP_VERSION` in `managers/bookmarks.py` line 745. (S, finding #18)

2. **Wire OneTab importer to CLI** -- Add `import-onetab` to CLI commands dict in `cli.py`. Class exists in `importers.py` lines 550-583. (S, finding #34)

3. **Wire XBEL to export dialog and CLI** -- Add XBEL to `ui/workflow_selective_export.py` format list and `cli.py` export handler. Handler exists at `io_formats/xbel.py`. (S, finding #35)

4. **Fix drag-drop area label** -- Change "Drop files here or click to browse" to "Click to import files" in `ui/components.py` line 211 since true DnD is not implemented. (S, finding #24)

5. **Remove single-item View menu** -- `app_shell.py` line 91 shows only "List View" with no alternative. Remove the menu or the dead entry. (S, finding #22)

6. **Fix privacy banner hardcoded colors** -- Replace `bg='#0f766e'`, `fg='#ffffff'` in `launcher.py` lines 48-63 with theme tokens. (S, finding #55)

7. **Fix SearchHighlighter hardcoded colors** -- Replace `highlight_color='#ffeb3b'` in `ui/navigation.py` line 314 with `get_theme().accent_warning`. (S, finding #56)

8. **Fix make_keyboard_activatable focus color** -- Replace `focus_color='#5b8cff'` in `ui/tk_interactions.py` line 12 with lazy `get_theme().accent_primary` resolution. (S, finding #57)

9. **Add SHA-256 hashes to BackupScheduler** -- `local_state.py` line 118 creates backups without integrity hashes. Add hash generation matching `StorageManager._create_backup()`. (S, finding #46)

10. **Consolidate bg_card/card_bg tokens** -- Merge into single `card_bg` token. Remove unused `card_outline`. Update `ui/feedback.py` references. (S, finding #61)

---

## Larger Bets

### LB-01: Browser Extension (R-01)

The single highest-impact feature for adoption. Every competitor ships one. Every review cites it as essential. Requires: Chrome MV3 + Firefox WebExtension, native messaging to localhost API, pattern engine subset for offline categorization, auth token exchange. Estimated effort: L (3-5 days for MVP).

Key risk: Native messaging requires separate installer component on Windows. PyInstaller/Nuitka must bundle the native messaging host manifest. Chrome Web Store review adds delay.

### LB-02: Nuitka Compilation (R-40)

Eliminates the #1 Windows distribution problem: AV false positives on PyInstaller executables. Nuitka 4.x compiles Python to C, producing executables that look like normal applications to AV scanners. 2-4x faster startup. Tkinter plugin is available. ROADMAP references Nuitka 2.x -- now at 4.x.

Key risk: Nuitka compilation time is slower than PyInstaller (10-30 min vs 2-5 min). CI build time increases. Some optional deps may need Nuitka plugins.

### LB-03: Reader View with Highlights (R-21)

Table stakes for serious bookmark tools (Linkwarden, Wallabag, Readwise Reader all ship this). Enables the bookmark -> read -> highlight -> export-to-PKM workflow. BOP has extracted text (`~/.bookmark_organizer/extracted/`) and Obsidian export; the missing piece is the highlight/annotation layer.

Key risk: Building a reader view in Tkinter is constrained. May need a tk.Text widget with tag-based highlighting or an embedded browser widget (tkinterweb). Highlight data model (bookmark_id, text, color, note, char_start, char_end) needs schema design.

### LB-04: SQLite Migration (R-31)

JSON file storage works for thousands of bookmarks but will not scale to 100K+. WAL mode SQLite unlocks concurrent access for web client (R-02). Migration tool converts JSON to SQLite on opt-in. JSON remains default for backward compat.

Key risk: Largest architectural change in the project. Migration tool must be bulletproof. All managers need dual-backend support. Testing matrix doubles.

### LB-05: Web Client (R-02)

FastAPI + HTMX, read/search/add from any device. PWA manifest for mobile install. Read-only by default, auth-gated mutations. Depends on SQLite migration (R-31) for concurrent access.

Key risk: Largest feature in the roadmap (XL). Requires auth system, responsive UI, PWA manifest, and concurrent data access. May distract from desktop app quality.

---

## Explicit Non-Goals

1. **Multi-user / team features** -- Contradicts local-first single-user design. Linkwarden and Linkding serve teams. BOP is a personal power tool.

2. **Docker as primary deployment** -- No-Docker is a differentiator. Docker support is acceptable as an option but never required.

3. **Cloud-hosted SaaS** -- Premature. Stabilize desktop + MCP first. Revisit post-v7.

4. **Native mobile apps (iOS/Android)** -- PWA via web client covers 90% of use cases. Native is too expensive for a single maintainer.

5. **Full language rewrite (Rust/Go/TS)** -- Python ecosystem (fastembed, lancedb, mcp, trafilatura) is the stack. Nuitka handles performance. Rewriting would lose 2+ years of feature development.

6. **AI-only organization (no manual control)** -- "AI assists, user decides" is core philosophy. mymind's folder-free approach contradicts BOP's power-user positioning. Never remove manual control.

7. **Browser history import (full)** -- Privacy risk too high. One-off migration aid only if explicitly requested.

8. **CustomTkinter migration** -- Stagnating (no releases in 12+ months, maintainer absent). sv-ttk (R-18) is the correct alternative.

9. **Meilisearch/Elasticsearch sidecar** -- Built-in FTS + LanceDB is a simplicity advantage. No external search infrastructure.

10. **Subscription pricing model** -- BOP is free and local-first. Competing on price with Raindrop ($0 free tier) is a losing proposition. Compete on sovereignty and features.

---

## Open Questions

1. **MCP auth mechanism for stdio transport:** The MCP spec does not define a standard authentication mechanism for stdio transport (OAuth 2.1 is for HTTP transport). How should BOP's MCP server authenticate clients? Options: (a) environment variable with token, (b) token file path passed as argument, (c) header in MCP session metadata. Need to survey what Karakeep and Readwise Reader do.

2. **Nuitka + Tkinter + optional deps compatibility:** Has anyone successfully compiled a Tkinter app with LanceDB, fastembed, and cryptography optional deps using Nuitka 4.x? The Tkinter plugin exists, but the combination of ONNX runtime (fastembed) + Arrow (LanceDB) + OpenSSL (cryptography) may surface linking issues. Needs a test build before committing to R-40.

3. **Reader view widget choice:** Tkinter has limited rich-text support. Options: (a) tk.Text with tag-based highlighting (simplest, most constrained), (b) tkinterweb (embedded browser, heavy dependency), (c) tkhtmlview (lightweight HTML renderer, limited maintenance). Which approach best balances capability vs dependency weight for R-21?

4. **XBEL + Floccus round-trip:** BOP exports XBEL via `io_formats/xbel.py`. Has anyone verified this round-trips cleanly with Floccus (the de facto cross-browser sync gateway)? If it does, BOP gets cross-browser bookmark sync for free without building any sync infrastructure.

5. **Tag normalization on save:** Karakeep enforces per-user tag style (case normalization, separator standardization). BOP's `tag_linter.py` surfaces duplicates but does not auto-normalize. Should BOP add an optional "normalize tags on save" toggle? Risk: users may intentionally use mixed-case tags for visual distinction. Need user feedback.
