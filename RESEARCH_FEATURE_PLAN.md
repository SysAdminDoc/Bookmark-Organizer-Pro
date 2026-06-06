# Project Research and Feature Plan

> **Date:** 2026-06-05 | **Version:** v6.4.2 | **Pass:** 5 (post-extension-MVP, full competitive rewrite)
> **Scope:** Source code audit (147 files, ~40K LOC), browser extension deep-dive, MCP server analysis, API security review, competitive landscape (120+ sources), ecosystem patterns.
> **Prior:** ROADMAP v4.0 (78 items, 120 sources) is the canonical planning doc. This plan identifies **new** opportunities and verifies existing roadmap claims.

---

## Executive Summary

Bookmark Organizer Pro v6.4.2 is a genuinely unique product: the **only open-source desktop bookmark manager** with local-first semantic search (LanceDB + FastEmbed), AI categorization (7,500+ patterns, 6 providers), a 20-tool MCP server, conversational RAG, and citation-aware summaries. No competitor occupies this exact intersection — every major alternative is either cloud SaaS (Raindrop.io, Burn 451), self-hosted Docker/web (Karakeep 25.9K stars, Linkwarden 18.5K, Wallabag 12.8K), or aging CLI-only (Buku 7.1K).

The v6.4.2 browser extension MVP establishes the save-from-browser pipeline, but it's skeletal: no offline category suggestions, no context menu, no keyboard shortcut, no icons, no read-later toggle. The MCP server remains the single biggest security gap — 20 tools exposed with zero authentication enforcement despite `MCPTokenManager` being fully built. Three OWASP-class vulnerabilities (XXE, stored XSS, unauthenticated GET) remain open.

**Top 10 highest-value opportunities:**

1. **Wire MCP authentication** — 20 tools exposed, auth module dead code (R-52, Now)
2. **Browser extension production hardening** — icons, context menu, category autocomplete, keyboard shortcut (extends R-01)
3. **Fix XXE + stored XSS + GET auth** — three OWASP vulnerabilities still open (R-53, R-54, R-56)
4. **MCP write tools** — delete, update, pin, tag mutation for agent curation parity (R-57)
5. **GUI chat panel** — RAG backend complete but GUI-invisible; most differentiating feature (R-60)
6. **Batch save context manager** — every mutation triggers full-file JSON serialization (R-73)
7. **Browser extension category autocomplete** — ship patterns as bundled JSON lookup (new, extends R-01)
8. **API endpoint for categories/tags lists** — enable extension autocomplete via local API (new)
9. **Context menu "Save to BOP"** — right-click save with selected text as notes (new)
10. **File-change watching** — MCP and GUI create independent managers; edits don't sync (R-74)

---

## Evidence Reviewed

### Local Files Inspected

| Area | Files | Lines | Key Findings |
|------|-------|-------|--------------|
| `browser-extension/` | 5 files | ~250 | MVP-complete but no icons, no context menu, no autocomplete, no read-later |
| `bookmark_organizer_pro/mcp_server.py` | 1 file | ~610 | 20 tools, zero auth enforcement, no write tools |
| `bookmark_organizer_pro/services/api.py` | 1 file | ~280 | GET endpoints unauthenticated, no pagination offset, no CORS for extension |
| `bookmark_organizer_pro/services/` | 35 files | ~8,000 | Well-structured; 27/35 modules untested |
| `bookmark_organizer_pro/ui/` | 40+ files | ~12,000 | Mixin architecture; about.py has false claims |
| `bookmark_organizer_pro/cli.py` | 1 file | ~500 | 37 subcommands, no per-subcommand --help |
| `tests/` | 6 files | ~1,800 | 255 tests; extension tests are static-only |
| `ROADMAP.md` | 1 file | ~530 | v4.0, 78 items, 120 sources — current and accurate |
| `CHANGELOG.md` | 1 file | ~840 | Full history v4.1.0 through v6.4.2 |
| `docs/` | 3 files | ~800 | ARCHITECTURE.md, COMPETITIVE_RESEARCH.md, REPOSITORY_STRUCTURE.md |

### Git History

30 commits reviewed. Recent focus: browser extension MVP (v6.4.2), CLI hardening (v6.4.1), bulk operations + GUI scaling (v6.4.0), roadmap v4.0 rewrite.

### External Sources

- 13 OSS competitors (Karakeep, Linkwarden, Wallabag, Linkding, ArchiveBox, Buku, Faved, Readeck, Grimoire, Eclaire, GoSuki, Floccus, LazyCat)
- 7 commercial services (Raindrop.io, Burn 451, Readwise, Bookmarkjar, ContextBolt, Markwise, mymind)
- MCP ecosystem (FastMCP 3.x, 2026-07-28 spec RC, IBM/AWS design guides)
- Chrome extension landscape (MV3 patterns, Prompt API, native messaging)
- Python packaging (Nuitka 4.0/4.1, tufup 0.10.0)
- Tkinter modernization (sv-ttk 2.6.1, CustomTkinter, tksheet 7.6.0)
- WCAG 2.2 (focus-appearance 2.4.11/2.4.13, target-size 2.5.8)

### Unverified

- Live behavior of GUI app (no Python GUI environment on this VM)
- PyInstaller binary build (no build toolchain available)
- Nuitka compilation of this specific codebase
- Extension behavior in Chrome/Firefox (no browser testing environment)
- LanceDB performance at scale (>10K bookmarks)

---

## Current Product Map

### Core Workflows

1. **Import** → bookmarks from 14 sources (browsers, files, services)
2. **Organize** → auto-categorize via 7,500+ patterns, manual category/tag, AI enrichment
3. **Search** → keyword (15+ filter types) + semantic (vector) + hybrid (RRF)
4. **Preserve** → HTML snapshots (4-backend chain), Wayback Machine, auto-scheduler
5. **Chat** → conversational RAG over collections with citation provenance
6. **Export** → 12 formats (HTML/JSON/CSV/OPML/XBEL/Markdown/ZIP/Obsidian/EPUB/Atom/JSON Feed/Zotero)
7. **MCP** → 20 tools for AI agent integration (read-only + add)
8. **Browser Save** → extension popup + bookmarklet → localhost API

### User Personas

| Persona | Primary Workflow | Key Features |
|---------|-----------------|--------------|
| Power organizer | Import thousands, auto-categorize, search | Pattern engine, bulk ops, hybrid search |
| AI-native user | MCP integration with Claude/Cursor | MCP server, RAG chat, semantic search |
| Privacy-conscious archivist | Local preservation, encrypted storage | Snapshots, AES-256-GCM, zero-cloud |
| Casual saver | Quick save from browser, occasional browse | Extension, bookmarklet, categories |
| Researcher | Build reading trails, annotate, export | Flows, Obsidian export, EPUB, citation summaries |

### Platforms & Distribution

- **Primary:** Windows (Tkinter, PyInstaller .exe)
- **Cross-platform:** macOS, Linux (same codebase, different binary)
- **Browser extension:** Chrome + Firefox (MV3 MVP, not yet published)
- **MCP:** stdio transport for Claude Desktop, Claude Code, Cursor
- **CLI:** 37 subcommands via `bop` / `python -m bookmark_organizer_pro.cli`

### Storage & Data Flow

```
~/.bookmark_organizer/
├── bookmarks.json          # Primary data store (JSON, atomic writes)
├── categories.json         # Category hierarchy
├── tags.json               # Tag state
├── snapshots/              # HTML archives per bookmark
├── extracted/              # Plain text per bookmark
├── embeddings/             # Vector store (LanceDB or JSON fallback)
├── exports/                # ZIP/EPUB/Obsidian output
├── flows.json              # Research trails
├── feeds.json              # RSS/Atom subscriptions
├── dead_links.json         # Scanner results
├── settings.json           # User preferences
├── ai_config.json          # AI provider credentials
├── api_token.txt           # REST API bearer token
├── mcp_tokens.json         # MCP auth tokens (dead code — unused)
└── backups/                # Rotated backups with SHA-256 hashes
```

---

## Feature Inventory

### Complete & Mature

| Feature | Entry Point | Code Location | Tests | Docs |
|---------|------------|---------------|-------|------|
| Pattern engine (7,500+ rules, 43 categories) | Auto on import/add | `core/pattern_engine.py`, `core/default_categories.py` | ✅ 20+ | README |
| Keyword search (15+ filter types) | GUI search bar, CLI `search` | `search.py` | ✅ 15+ | README |
| 14 importers (browsers + services) | GUI Import menu, CLI | `importers.py`, `importers_extra.py` | ✅ 10+ | README |
| 12 export formats | CLI subcommands | `services/*.py`, `io_formats/xbel.py` | ✅ 8+ | README |
| Undo/redo command stack | GUI Edit menu, Ctrl+Z/Y | `commands.py` | ✅ | — |
| Backup system (rotation + SHA-256) | Auto on save | `core/storage_manager.py` | ✅ | README |
| 11 themes (incl. WCAG AA high-contrast) | GUI theme dropdown | `theme_runtime.py`, `ui/theme.py` | — | README |
| Toast notifications | Auto on actions | `ui/widgets.py` | — | — |
| Zoom/DPI scaling | GUI toolbar, Ctrl+Scroll | `ui/density.py`, app mixins | — | — |
| Dashboard analytics | GUI sidebar | `ui/widget_dashboard.py` | — | — |

### Complete But GUI-Invisible (CLI/MCP Only)

| Feature | CLI Command | Code Location | Tests | GUI Surface |
|---------|------------|---------------|-------|-------------|
| Semantic search | `bop semantic` | `services/vector_store.py`, `services/embeddings.py` | ✅ 4 | ❌ None |
| Hybrid search (RRF) | `bop hybrid` | `services/hybrid_search.py` | ✅ 2 | ❌ None |
| Conversational RAG | `bop chat`, `bop ask` | `services/rag_chat.py` | ✅ 2 | ❌ None (R-60) |
| Citation-aware summaries | `bop summarize` | `services/citation_summarizer.py` | ✅ 1 | ❌ None |
| NL query translator | `bop nl-query` | `services/nl_query.py` | — | ❌ None |
| Read-later queue | `bop read-later` | `services/read_later.py` | ✅ 2 | ❌ None (R-67) |
| Research flows | `bop flow` | `services/flows.py` | ✅ 2 | ❌ None (R-67) |
| RSS/Atom ingestor | `bop feed` | `services/rss_feeds.py` | ✅ 2 | ❌ None (R-67) |
| Tag linter | `bop lint-tags` | `services/tag_linter.py` | ✅ 2 | ❌ None |
| Daily digest | `bop digest` | `services/digest.py` | ✅ 2 | ❌ None |
| Duplicate detector | `bop dups` | `services/dup_hybrid.py` | — | ❌ None |
| Smart Collections | `bop smart-collections` | `services/smart_collections.py` | ✅ 18 | ❌ None |
| Content ingest | `bop ingest` | `services/ingest.py` | — | ❌ None |
| Embedding generation | `bop embed` | `services/embeddings.py` | ✅ 2 | ❌ None |

### Partial / MVP

| Feature | Status | What's Missing |
|---------|--------|---------------|
| Browser extension | MVP shipped v6.4.2 | No icons, no context menu, no autocomplete, no read-later, no keyboard shortcut |
| MCP authentication | Module built (`services/mcp_auth.py`) | Never imported by `mcp_server.py` — zero enforcement |
| MCP write tools | `add_bookmark` only | No delete, update, pin, tag mutation |
| About dialog | Built (`ui/about.py`) | False feature claims; not wired to Help menu |
| Command palette | 18 of 40+ actions | Missing: Toggle Pin, Copy URL, Delete, About, AI tools |
| Bookmark editor | URL/title/category/tags | Missing: notes, description, pin, read-later fields |

### Dead Code

| Code | Location | Lines | Status |
|------|----------|-------|--------|
| KanbanView | `ui/` | ~200 | Never instantiated (R-66) |
| TimelineView | `ui/` | ~170 | Never instantiated (R-66) |
| ReadingListView | `ui/` | ~150 | Never instantiated (R-66) |
| TagCloudView | `ui/` | ~150 | Never instantiated (R-66) |

---

## Competitive and Ecosystem Research

### Direct Competitors

| Product | Key Advantage Over BOP | What BOP Should Learn | What BOP Should Avoid |
|---------|----------------------|----------------------|----------------------|
| **Karakeep** (25.9K★) | Mobile apps (iOS/Android), Ollama local AI, SingleFile in-extension, 3-browser coverage | Ollama integration UX, browser extension quality bar | Docker-first deployment; BOP's no-Docker stance is a differentiator |
| **Linkwarden** (18.5K★) | Reader view with highlights/annotations, team features, triple archive | Reader view UX (R-21), annotation model | Multi-user complexity; BOP is single-user by design |
| **Burn 451** (commercial) | 22 MCP tools, triage model (24hr deadline), polished Chrome extension | MCP tool breadth, extension UX, save-page AI summary | 24hr auto-delete causes data anxiety; contradicts archival philosophy |
| **Raindrop.io** (SaaS) | Stella AI chat, polished mobile apps, cross-browser extension, nested collections | Stella's conversational UX for RAG chat panel | Cloud dependency; BOP's local-first is the differentiator |
| **ContextBolt** (Chrome ext) | In-browser semantic search, MCP endpoint for Pro tier | Client-side embedding for privacy | Subscription model, Chrome-only |
| **Bookmarkjar** (SaaS) | Visual card layout, captures Twitter threads/Reddit/TikTok | Social media URL handlers, visual bookmarks | Cloud-only, subscription |
| **Buku** (7.1K★, CLI) | SQLite backend, shell completion (bash/zsh/fish), 7 formats | Shell completion scripts, SQLite migration approach | No GUI, no AI, no search beyond SQL LIKE |

### Adjacent-Domain Inspiration

| Product | Relevant Pattern | Application to BOP |
|---------|-----------------|-------------------|
| **Floccus** (browser sync) | XBEL round-trip over WebDAV/Nextcloud | Validate BOP's XBEL handler works with Floccus for free sync |
| **GoSuki** (FS monitoring) | Watches browser bookmark files via OS events, no extension needed | Alternative to extension; lower UX but zero install friction |
| **Markwise** (chat extension) | Chat-with-bookmarks as primary UX | Validates R-60 GUI chat panel priority |
| **Perplexica** (citations) | Inline `[1][2]` citation badges in responses | BOP already has `[#cN]` tokens; add rendered badges in GUI |
| **yt-dlp** (video metadata) | Transcript + metadata extraction from video URLs | BOP already ships this; verify YouTube detection covers all URL variants |

### MCP Ecosystem Positioning

BOP's MCP server is a genuine differentiator — only 4 bookmark tools have MCP (BOP, Burn 451, Karakeep, infinitepi-io). But the competitive window is narrowing:

- Burn 451: 22 tools (vs BOP's 20), includes write operations
- ContextBolt: Pro tier MCP endpoint with semantic search
- Chrome MCP extensions: 3+ new entrants in 2026

**Key MCP patterns BOP should adopt:**
- Design tools for agents, not REST 1:1 (high-level verbs like `find_related`, `summarize_recent`)
- Docstrings are agent instructions — specify when/how to use each tool
- STDIO servers must never write to stdout (corrupts JSON-RPC)
- Timeout all external calls (10s default)
- FastMCP 3.x: Provider/Transform architecture, OTEL spans, OAuth auto-enable

---

## Highest-Value New Features

### NF-01: Browser Extension Context Menu — "Save to BOP"

- **User problem:** Users must click the extension icon, wait for popup, then click Save. No way to save with selected text from right-click.
- **Evidence:** Every major competitor extension (Karakeep, Linkwarden, Raindrop.io) ships a context menu. Chrome MV3 `contextMenus` API is straightforward.
- **Proposed behavior:** Right-click any page → "Save to BOP" context menu item. Right-click selected text → "Save to BOP with selection" (populates notes field). Both save immediately with default category, show browser notification on success.
- **Implementation:**
  - Add `"contextMenus"` to `manifest.json` permissions
  - Create `background.js` service worker with `chrome.contextMenus.create()` and `chrome.contextMenus.onClicked` handler
  - Reuse save logic from popup.js (extract to shared module)
- **Data model:** No changes — uses existing POST `/bookmarks` API
- **Risks:** Service worker lifecycle in MV3 (must handle wakeup); Firefox WebExtension API differences for `browser.contextMenus`
- **Verification:** Load unpacked extension → right-click page → "Save to BOP" → verify bookmark appears in app
- **Complexity:** S
- **Priority:** P0 — table-stakes for any bookmark extension

### NF-02: Browser Extension Offline Category Autocomplete

- **User problem:** Category field in popup is a blank text input. Users must remember exact category names from the 43-category taxonomy. Friction causes defaulting to "Uncategorized."
- **Evidence:** ROADMAP R-01 mentions "offline category/tag suggestions from the 7,500-pattern engine (ship as bundled JSON lookup)" but the extension ships without this. Chrome 138+ Prompt API (Gemini Nano) enables in-browser AI categorization with zero API cost.
- **Proposed behavior:**
  1. Ship `categories.json` (43 category names) bundled in extension
  2. As user types in Category field, show filtered dropdown (prefix match)
  3. On popup open, attempt to auto-suggest category by matching current page URL against a simplified pattern lookup
  4. Future: Chrome Prompt API for AI-powered suggestion with zero API cost
- **Implementation:**
  - Generate `categories.json` from `default_categories.py` at build time (or maintain static copy)
  - Add `<datalist>` element to `popup.html` connected to category input
  - Add domain→category lookup from a top-500 domain mapping bundled as JSON
  - For tag suggestions: query existing tags from API endpoint (requires NF-03)
- **Risks:** Bundled JSON size (~50KB for 500 domains is fine); must stay in sync with desktop app categories
- **Verification:** Type "Dev" in category field → see "Development / Programming" suggestion
- **Complexity:** M
- **Priority:** P0 — directly reduces the biggest friction point in the save flow

### NF-03: API Categories and Tags List Endpoints for Extension

- **User problem:** Extension can't offer tag/category autocomplete because the API has no endpoint to list categories or tags. The REST API has `/categories` and `/tags` GET endpoints but they're unauthenticated (security issue) and the extension doesn't call them.
- **Evidence:** `api.py` lines 136-154 already implement `/categories` and `/tags` endpoints. Extension `popup.js` never fetches them. Extension has no mechanism to populate autocomplete from the live app.
- **Proposed behavior:**
  1. Add Bearer token auth to `/categories` and `/tags` GET endpoints (fixes R-56 partially)
  2. Extension fetches categories + tags on popup open (with token from options)
  3. Populate `<datalist>` elements for both fields
  4. Cache results in `chrome.storage.local` with 5-minute TTL
- **Implementation:**
  - `api.py`: Add `_check_auth()` call to `do_GET()` for `/categories`, `/tags`, `/bookmarks`, `/search` (addresses R-56)
  - `popup.js`: On load, fetch `/categories` and `/tags`, build datalist elements
  - `options.js`: Add "Test Connection" button that validates token + port
- **Risks:** API might not be running when extension popup opens — need graceful degradation to bundled static list
- **Verification:** Open popup → see autocomplete suggestions from live app data
- **Complexity:** M
- **Priority:** P1 — depends on NF-02 for the autocomplete UI

### NF-04: Browser Extension Keyboard Shortcut (Ctrl+Shift+B)

- **User problem:** No keyboard shortcut to save current tab. Must click extension icon.
- **Evidence:** Every major competitor extension supports a keyboard shortcut. Chrome MV3 supports `commands` API with `_execute_action` for the popup.
- **Proposed behavior:** Ctrl+Shift+B (configurable in `chrome://extensions/shortcuts`) opens popup. Alt+Shift+B as fallback if Ctrl+Shift+B conflicts.
- **Implementation:**
  ```json
  "commands": {
    "_execute_action": {
      "suggested_key": { "default": "Ctrl+Shift+B", "mac": "Command+Shift+B" },
      "description": "Save current tab to Bookmark Organizer Pro"
    }
  }
  ```
- **Risks:** Key conflict with Chrome's built-in Ctrl+Shift+B (bookmark bar toggle). Users can remap in `chrome://extensions/shortcuts`.
- **Verification:** Press Ctrl+Shift+B → popup opens → save bookmark
- **Complexity:** S
- **Priority:** P1

### NF-05: Browser Extension Icons

- **User problem:** Extension shows default puzzle-piece icon in toolbar. Looks unprofessional and is hard to find among other extensions.
- **Evidence:** `manifest.json` has no `icons` field. `assets/bookmark_organizer.png` exists at 256x256 but isn't referenced.
- **Proposed behavior:** Extension icon in toolbar, popup, and chrome://extensions page at 16/32/48/128px.
- **Implementation:**
  - Resize `assets/bookmark_organizer.png` to 16/32/48/128px PNGs
  - Copy to `browser-extension/icons/`
  - Add `"icons"` and `"action.default_icon"` to `manifest.json`
- **Risks:** None
- **Verification:** Load extension → see custom icon in toolbar
- **Complexity:** S
- **Priority:** P0 — required for Chrome Web Store submission

### NF-06: Extension Read-Later Toggle

- **User problem:** Read-later queue is a first-class feature (backend complete, CLI working) but the extension has no way to mark a bookmark as "read later" during save.
- **Evidence:** `services/read_later.py` exists with full CRUD. `popup.js` payload has no `read_later` field. API POST handler doesn't pass it through.
- **Proposed behavior:** Checkbox "Read Later" in popup, below notes field. Checked state sends `read_later: true` in payload.
- **Implementation:**
  - `popup.html`: Add checkbox input
  - `popup.js`: Include `read_later` boolean in POST payload
  - `api.py`: Pass `read_later` to `add_bookmark_clean()` (requires checking if BookmarkManager supports it on add)
- **Risks:** BookmarkManager.add_bookmark_clean() may not accept `read_later` — need to verify and possibly extend
- **Verification:** Save with "Read Later" checked → `bop read-later list` shows the bookmark
- **Complexity:** S
- **Priority:** P1

### NF-07: MCP High-Level Agent Tools

- **User problem:** Current MCP tools are CRUD-level (list, get, search, add). AI agents need higher-level verbs for natural workflows: "find related bookmarks," "what did I save about X this week," "summarize my recent saves."
- **Evidence:** FastMCP 3.x best practices (Phil Schmid/IBM): "Design tools for agents, not REST 1:1." Burn 451's 22 tools include high-level operations.
- **Proposed tools:**
  1. `find_related(bookmark_id, k=5)` — find semantically similar bookmarks
  2. `recent_activity(days=7)` — bookmarks added/visited in last N days with stats
  3. `collection_overview(category=None, tag=None)` — summary stats + top bookmarks for a scope
  4. `batch_tag(bookmark_ids, tags, action="add"|"remove")` — bulk tag operations
  5. `move_category(bookmark_ids, new_category)` — bulk recategorize
- **Implementation:** Pure functions in `mcp_server.py` using existing service layer
- **Risks:** Tool count inflation — should replace low-value tools rather than only adding
- **Verification:** Connect via MCP Inspector → call `find_related` → verify results are semantically relevant
- **Complexity:** M
- **Priority:** P1

### NF-08: Extension "Test Connection" Button in Options

- **User problem:** When API token or port is wrong, the extension silently fails on save with "Cannot reach the local API." No way to test the configuration beforehand.
- **Evidence:** `options.js` has save functionality but no connection test. Users must save a bookmark to discover misconfigurations.
- **Proposed behavior:** "Test Connection" button in options page. On click, fetches `http://127.0.0.1:{port}/` with Bearer token. Shows success (with app version) or specific error (wrong port, wrong token, API not running).
- **Implementation:**
  - `options.html`: Add "Test Connection" button
  - `options.js`: Fetch API root endpoint with auth header, display result
- **Risks:** None — read-only test
- **Verification:** Enter wrong port → click Test → see "Cannot reach API". Enter correct port → see "Connected to BOP v6.4.2"
- **Complexity:** S
- **Priority:** P1

### NF-09: API Pagination with Offset Support

- **User problem:** `/bookmarks` endpoint supports `limit` but ignores `offset` in response — can't paginate through large libraries. Extension or future web client can't efficiently browse.
- **Evidence:** `api.py` line 122 parses `limit` (clamps to 1-500) but the response always starts from index 0. No `offset` parameter parsing.
- **Proposed behavior:** `GET /bookmarks?limit=50&offset=100` returns bookmarks 100-149. Response includes `total`, `limit`, `offset`, `has_more` fields.
- **Implementation:**
  ```python
  offset = max(0, int(params.get('offset', [0])[0]))
  page = bookmarks[offset: offset + limit]
  self._send_json({"total": len(bookmarks), "count": len(page), 
                   "offset": offset, "limit": limit, 
                   "has_more": offset + limit < len(bookmarks),
                   "bookmarks": [asdict(bm) for bm in page]})
  ```
- **Risks:** None — backward compatible (offset defaults to 0)
- **Verification:** `curl http://127.0.0.1:8765/bookmarks?limit=10&offset=10` → returns bookmarks 10-19
- **Complexity:** S
- **Priority:** P2

### NF-10: Duplicate Check on Extension Save

- **User problem:** Extension receives HTTP 409 "Already saved" after attempting to save, but doesn't check beforehand. Could show "already saved" state immediately on popup open.
- **Evidence:** `popup.js` line 134 handles 409 response. API has `url_exists()` check. But popup doesn't pre-check.
- **Proposed behavior:** On popup open, after loading active tab URL, check if bookmark exists via API. If yes, show "Already saved ✓" badge and disable save button (or change to "Update" for future edit flow).
- **Implementation:**
  - Add `GET /bookmarks/check?url=<encoded_url>` endpoint to API (returns `{exists: true/false, bookmark_id: N}`)
  - `popup.js`: On load, fetch check endpoint, update UI accordingly
- **Risks:** Extra API call on every popup open — should be fast (in-memory URL lookup)
- **Verification:** Open popup on already-saved page → see "Already saved" badge
- **Complexity:** S
- **Priority:** P2

---

## Existing Feature Improvements

### EI-01: API GET Authentication (R-56)

- **Current behavior:** `do_GET()` never calls `_check_auth()`. All bookmark data readable by any local process via `curl http://127.0.0.1:8765/bookmarks`.
- **Problem:** Any malware or sibling process on localhost can dump entire bookmark library.
- **Recommended change:** Apply `_check_auth()` to all GET endpoints except the root `/` info endpoint.
- **Code locations:** `services/api.py` lines 86-173 (`do_GET` method)
- **Backward compatibility:** Extension already sends Bearer token on POST; must also send on GET. Update `popup.js` fetch calls.
- **Verification:** `curl http://127.0.0.1:8765/bookmarks` without token → 401
- **Complexity:** S
- **Priority:** P0

### EI-02: XBEL XXE Fix with defusedxml (R-53)

- **Current behavior:** `io_formats/xbel.py` line 129 uses `ET.fromstring(xml_bytes)` with a regex guard checking for `<!ENTITY`. `importers.py` uses `ET.parse()` with no guard at all.
- **Problem:** Regex guard is bypassable (case sensitivity, obfuscation, SYSTEM/PUBLIC identifiers). Standard `ET` parser resolves external entities.
- **Recommended change:** Replace `xml.etree.ElementTree` with `defusedxml.ElementTree` in all three locations (`xbel.py`, `importers.py` OPML parsing, any other XML paths). Add `defusedxml` to core requirements.
- **Code locations:** `io_formats/xbel.py:129`, `importers.py` (OPML import), `services/rss_feeds.py` (already has correct pattern to copy)
- **Backward compatibility:** defusedxml is a drop-in replacement for ET parsing APIs
- **Verification:** Create OPML with `<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>` → import should fail/sanitize
- **Complexity:** S
- **Priority:** P0

### EI-03: LocalArchiver HTML Sanitization (R-54)

- **Current behavior:** `web_tools.py` embeds fetched HTML via f-string with no script stripping. `<script>` tags execute in `file://` origin.
- **Problem:** Stored XSS: malicious page JS runs when user opens archived file. In `file://` context, scripts can read local files.
- **Recommended change:**
  1. Strip `<script>` tags and `on*=` event handlers from fetched HTML
  2. Add CSP meta header: `<meta http-equiv="Content-Security-Policy" content="script-src 'none'; object-src 'none'">`
  3. Sandbox the HTML within an iframe with `sandbox` attribute if opened in-app
- **Code locations:** `services/web_tools.py` (LocalArchiver class, HTML template section)
- **Backward compatibility:** Existing archives are already stored; add CSP to new archives only
- **Verification:** Archive a page with inline `<script>alert(1)</script>` → open archive → no alert
- **Complexity:** S
- **Priority:** P0

### EI-04: Windows ACL on Sensitive Files (R-55)

- **Current behavior:** `api.py` line 36-37: `if os.name != "nt": os.chmod(...)` — permission setting skipped on Windows entirely. `api_token.txt`, `ai_config.json`, `mcp_tokens.json` readable by all local users.
- **Problem:** Token files have default ACLs on Windows (primary platform). Any local user can read API tokens.
- **Recommended change:** After writing sensitive files, call `icacls` to restrict to current user:
  ```python
  if os.name == "nt":
      subprocess.run(["icacls", str(path), "/inheritance:r", 
                       "/grant:r", f"{os.environ.get('USERNAME', 'SYSTEM')}:F"],
                     capture_output=True, check=False)
  ```
- **Code locations:** `services/api.py:36`, `ai.py` (ai_config.json writes), `services/mcp_auth.py` (mcp_tokens.json writes)
- **Backward compatibility:** Only affects new writes; existing files retain current ACLs
- **Verification:** Create new API token → `icacls api_token.txt` shows only current user has access
- **Complexity:** S
- **Priority:** P1

### EI-05: About Dialog Accuracy (R-63, R-64)

- **Current behavior:** `ui/about.py` lists features that are removed (System Tray, drag-and-drop) or misleading (Undo/Redo scope), and has an AI attribution line.
- **Problem:** False feature claims erode user trust. AI attribution line (line ~290) should be removed per project rules.
- **Recommended change:**
  1. Remove "System Tray" and "Drag and Drop" from features list
  2. Clarify "Undo/Redo" as "Bookmark-level undo/redo"
  3. Remove AI attribution line
  4. Add note that AI features require API keys or Ollama
  5. Wire AboutDialog to Help menu (R-62)
- **Code locations:** `ui/about.py` lines 168-215, 290
- **Backward compatibility:** N/A (UI-only)
- **Verification:** Help → About → verify all listed features are real
- **Complexity:** S
- **Priority:** P1

### EI-06: Extension Error Recovery UX

- **Current behavior:** When API is unreachable, popup shows "Cannot reach the local API." with no troubleshooting guidance.
- **Problem:** User doesn't know if API isn't running, port is wrong, or token is invalid.
- **Recommended change:** Show specific error messages:
  - Network error → "API server not running. Start BOP or run `bop api-server`."
  - 401 → "Invalid API token. Check Options."
  - Other HTTP errors → Show status code and body.error
  - Add link to Options page in error state
- **Code locations:** `browser-extension/popup.js` lines 141-143
- **Backward compatibility:** N/A (extension-only)
- **Verification:** Stop API server → open popup → see actionable error message
- **Complexity:** S
- **Priority:** P1

### EI-07: Version Sync Across Files

- **Current behavior:** Version string appears in `constants.py` (6.4.2), `manifest.json` (6.4.2), `CLAUDE.md` (6.1.0), `pyproject.toml` (needs check), `packaging/bookmark_organizer.spec` (needs check), `packaging/version_info.txt` (needs check).
- **Problem:** Stale versions in build metadata cause confusion and incorrect binaries.
- **Recommended change:**
  1. Single source of truth: `constants.py` defines version
  2. CI reads version from `constants.py` (or `pyproject.toml`)
  3. `manifest.json` version can differ (extension version)
  4. Add version-sync check to test suite
- **Code locations:** `constants.py`, `pyproject.toml`, `packaging/bookmark_organizer.spec`, `packaging/version_info.txt`, `CLAUDE.md`
- **Verification:** `python -c "from bookmark_organizer_pro.constants import APP_VERSION; print(APP_VERSION)"` matches all files
- **Complexity:** S
- **Priority:** P2

### EI-08: Test Hardening for Browser Extension

- **Current behavior:** `test_browser_extension.py` (56 lines) only validates manifest structure and file existence. No tests for popup logic, options persistence, error handling, or save flow.
- **Problem:** Regressions in extension JS are undetectable. Version string is hardcoded in test.
- **Recommended change:**
  1. Test popup.js: validate `isSaveableUrl()` returns correctly for various protocols
  2. Test payload structure: ensure required fields are present
  3. Test error handling: verify status messages for various HTTP codes
  4. Read version from `constants.py` instead of hardcoding
  5. Use a JS testing framework (Jest or Vitest) for extension unit tests, or validate JS syntax with Node
- **Code locations:** `tests/test_browser_extension.py`
- **Verification:** `pytest tests/test_browser_extension.py -v` → all pass after changes
- **Complexity:** M
- **Priority:** P2

---

## Reliability, Security, Privacy, and Data Safety

### Critical Security Issues (Open)

| ID | Issue | OWASP | Location | Status |
|----|-------|-------|----------|--------|
| SEC-01 | MCP server: 20 tools with zero auth | A01:2021 Broken Access Control | `mcp_server.py:574-588` | Open (R-52) |
| SEC-02 | REST API: GET endpoints unauthenticated | A01:2021 Broken Access Control | `api.py:86-173` | Open (R-56) |
| SEC-03 | XXE in OPML/XBEL importers | A05:2017 XXE | `importers.py`, `io_formats/xbel.py` | Partial mitigation (R-53) |
| SEC-04 | Stored XSS in LocalArchiver HTML | A03:2021 Injection | `services/web_tools.py` | Open (R-54) |
| SEC-05 | Windows ACL missing on token files | A04:2021 Insecure Design | `api.py:36-37` | Open (R-55) |
| SEC-06 | `cryptography` CVEs (buffer overflow + cert bypass) | A06:2021 Vulnerable Components | `requirements.txt` | Open (R-51) |

### Data Safety Concerns

| Issue | Risk | Mitigation |
|-------|------|-----------|
| JSON file as primary datastore | Corruption on crash during write | Atomic write via tempfile + `os.replace()` ✅ |
| No file-change watching | MCP and GUI create independent managers; edits don't sync | Poll `mtime` every 5s (R-74) |
| Full-file serialization on every save | Slow with large libraries, increases corruption window | Batch save context manager (R-73) |
| Backup rotation with SHA-256 | Recovery possible | ✅ Complete |
| Encrypted DB passphrase | AES-256-GCM, PBKDF2 480K iterations | ✅ Solid implementation |

### Privacy Assessment

| Area | Status |
|------|--------|
| No telemetry | ✅ Verified — privacy banner confirms |
| AI calls require opt-in | ✅ Requires API key configuration |
| Screenshot API (thum.io) | ✅ Opt-in via setting |
| Extension permissions | ✅ Minimal: activeTab, scripting, storage, localhost only |
| Data stays local | ✅ All storage under `~/.bookmark_organizer/` |

---

## UX, Accessibility, and Trust

### Browser Extension UX Gaps

| Issue | Impact | Fix |
|-------|--------|-----|
| No extension icon | Unprofessional, hard to find | NF-05 (P0) |
| No context menu | Can't right-click save | NF-01 (P0) |
| No category autocomplete | Users default to "Uncategorized" | NF-02 (P0) |
| No keyboard shortcut | Power users can't save quickly | NF-04 (P1) |
| No read-later toggle | Feature gap vs backend | NF-06 (P1) |
| No connection test | Configuration errors are opaque | NF-08 (P1) |
| No duplicate check | Wasted save attempts | NF-10 (P2) |
| Dark-mode only CSS | No light theme for extension | Future |
| No "already saved" indicator | Tab icon doesn't reflect state | Future |

### Desktop GUI Gaps (from ROADMAP)

| Issue | Roadmap Item | Priority |
|-------|-------------|----------|
| 15+ features GUI-invisible | R-67, R-68 | Next |
| 35+ hardcoded Segoe UI fonts | R-65 | Now |
| Help menu missing | R-62 | Now |
| Command palette incomplete (18/40+) | R-69 | Next |
| Bookmark editor limited fields | R-70 | Next |
| 8 dialogs missing Escape-to-close | R-72 | Later |
| DependencyCheckDialog hardcoded colors | R-71 | Next |
| 4 dead UI view classes | R-66 | Now |

### Accessibility

| Issue | WCAG Criterion | Status |
|-------|---------------|--------|
| Tab order undefined | 2.4.3 Focus Order | Open (R-48) |
| Focus indicators inadequate | 2.4.7 Focus Visible | Open (R-48) |
| Click targets may be < 24×24px | 2.5.8 Target Size | Open (R-48) |
| Screen reader labels missing | 4.1.2 Name, Role, Value | Open (R-48) |
| High-contrast theme | 1.4.3 Contrast (Minimum) | ✅ WCAG AA |

---

## Architecture and Maintainability

### Module Boundaries

The project uses a **mixin-based architecture** for the main app (41 mixins in `app_mixins/`). This is workable but creates implicit coupling — mixins reference each other's attributes without contracts. The `ARCHITECTURE.md` doc already identifies the extraction direction.

### Refactor Candidates

| Area | Issue | Effort | Priority |
|------|-------|--------|----------|
| `main.py` → app.py forwarding | `main.py` is a thin wrapper; could be merged or simplified | S | Low |
| `default_categories.py` (5,768 lines) | Largest file in codebase; consider externalizing to JSON | M | Low (under consideration) |
| DEFAULTS duplication in extension | `popup.js` and `options.js` both define identical DEFAULTS object | S | P2 |
| Extension save logic | `popup.js` save flow should be extractable for context menu reuse | S | P1 (prerequisite for NF-01) |

### Test Gaps

| Module | Tests | Coverage |
|--------|-------|----------|
| `services/snapshot.py` | 0 | Critical — 4-backend chain untested |
| `services/rag_chat.py` | 2 | Low — multi-turn, scoped retrieval untested |
| `services/hybrid_search.py` | 2 | Low — RRF, cross-encoder untested |
| `services/nl_query.py` | 0 | None — NL→structured query untested |
| `services/dead_link_scanner.py` | 0 | None — daemon lifecycle untested |
| `services/ingest.py` | 0 | None — extraction pipeline untested |
| `services/dup_hybrid.py` | 0 | None — SimHash, embedding dedup untested |
| Extension JS | 0 | None — no JS test framework |
| 22 more service modules | 0 | See R-78 |

### Documentation Gaps

| Gap | Impact |
|-----|--------|
| No extension INSTALL.md | Users can't load unpacked extension |
| No MCP configuration guide | Users don't know how to connect Claude Desktop |
| `CLAUDE.md` at v6.1.0 | Stale working notes for developers |
| No API reference doc | Extension developers and integrators have no reference |

---

## Prioritized Roadmap

### Phase 1 — Security & Extension Foundation (Now)

- [ ] P0 - **SEC: Wire MCP authentication enforcement (R-52)**
  - Why: 20 tools exposed with zero auth; any MCP client can manipulate library
  - Evidence: `mcp_server.py:574-588` — `_call_tool()` never calls auth check; `services/mcp_auth.py` fully built but never imported
  - Touches: `mcp_server.py`
  - Acceptance: MCP tools reject calls without valid token
  - Verify: Connect via MCP without token → error; with token → success

- [ ] P0 - **SEC: Fix XXE in OPML/XBEL importers (R-53)**
  - Why: Standard OWASP A05 vulnerability; current regex guard is bypassable
  - Evidence: `importers.py` uses `ET.parse()`, `xbel.py` uses `ET.fromstring()` — neither uses defusedxml
  - Touches: `importers.py`, `io_formats/xbel.py`, `requirements.txt` (add defusedxml)
  - Acceptance: Import OPML with XXE payload → rejected or sanitized
  - Verify: `python -c "from defusedxml import ElementTree"` succeeds; XXE test case in test suite

- [ ] P0 - **SEC: Sanitize LocalArchiver HTML + CSP (R-54)**
  - Why: Stored XSS via unsanitized fetched HTML executing in file:// context
  - Evidence: `services/web_tools.py` embeds `page_text` raw via f-string
  - Touches: `services/web_tools.py` (LocalArchiver)
  - Acceptance: Archived HTML has no `<script>` tags and includes CSP meta header
  - Verify: Archive page with inline script → open archive → no script execution

- [ ] P0 - **SEC: Add GET auth to REST API (R-56)**
  - Why: Entire bookmark library readable by any local process without token
  - Evidence: `api.py:86` — `do_GET()` never calls `_check_auth()`
  - Touches: `api.py` (do_GET method), `browser-extension/popup.js` (add token to GET requests)
  - Acceptance: `curl http://127.0.0.1:8765/bookmarks` → 401
  - Verify: Manual curl test without/with Bearer token

- [ ] P0 - **SEC: Bump cryptography to ≥46.0.7 (R-51)**
  - Why: CVE-2026-39892 (buffer overflow) + CVE-2026-34073 (cert validation bypass)
  - Evidence: `requirements.txt` floor is 42.0; CVEs affect 45.0-46.0.6
  - Touches: `requirements.txt`, `pyproject.toml`
  - Acceptance: `pip show cryptography` shows ≥46.0.7
  - Verify: `python -c "import cryptography; print(cryptography.__version__)"`

- [ ] P0 - **EXT: Add extension icons (NF-05)**
  - Why: Required for Chrome Web Store submission; unprofessional without icon
  - Evidence: `manifest.json` has no `icons` field; `assets/bookmark_organizer.png` exists
  - Touches: `browser-extension/manifest.json`, new `browser-extension/icons/` directory
  - Acceptance: Extension shows custom icon in toolbar and extensions page
  - Verify: Load unpacked → icon visible in toolbar

- [ ] P0 - **EXT: Add context menu "Save to BOP" (NF-01)**
  - Why: Table-stakes for bookmark extensions; every competitor ships this
  - Evidence: No `background.js` service worker exists; no `contextMenus` permission
  - Touches: `browser-extension/manifest.json`, new `browser-extension/background.js`, `browser-extension/popup.js` (extract shared save logic)
  - Acceptance: Right-click → "Save to BOP" → bookmark created
  - Verify: Right-click on page → context menu → save → verify in app

- [ ] P0 - **EXT: Add category autocomplete (NF-02)**
  - Why: Biggest friction point in save flow; users default to "Uncategorized"
  - Evidence: Popup category field is plain text input; 43 categories exist but unreachable
  - Touches: `browser-extension/popup.html`, `browser-extension/popup.js`, new `browser-extension/categories.json`
  - Acceptance: Typing in category field shows filtered suggestions
  - Verify: Type "Dev" → see "Development / Programming" in dropdown

### Phase 2 — MCP & Extension Polish (Next)

- [ ] P1 - **MCP: Add 6 write tools (R-57)**
  - Why: Burn 451 has 22 tools with full CRUD; BOP has only `add_bookmark`
  - Evidence: `mcp_server.py` — no delete, update, pin, tag, or read-later tools
  - Touches: `mcp_server.py` (add `t_delete_bookmark`, `t_update_bookmark`, `t_toggle_pin`, `t_mark_read_later`, `t_add_tags`, `t_remove_tags`)
  - Acceptance: All 6 tools callable via MCP Inspector
  - Verify: Delete a bookmark via MCP → verify it's gone in CLI

- [ ] P1 - **MCP: Add high-level agent tools (NF-07)**
  - Why: Design tools for agents, not REST 1:1; FastMCP best practices
  - Evidence: MCP design guidelines (Phil Schmid, IBM); Burn 451's high-level tools
  - Touches: `mcp_server.py`
  - Acceptance: `find_related`, `recent_activity`, `collection_overview` tools callable
  - Verify: MCP Inspector → `find_related(bookmark_id=1)` → returns semantically similar bookmarks

- [ ] P1 - **EXT: Keyboard shortcut (NF-04)**
  - Why: Power users expect keyboard save
  - Evidence: Chrome MV3 `commands` API; all competitors support it
  - Touches: `browser-extension/manifest.json` (commands section)
  - Acceptance: Ctrl+Shift+B opens popup
  - Verify: Press shortcut → popup opens

- [ ] P1 - **EXT: Read-later toggle (NF-06)**
  - Why: Feature parity with CLI; read-later is a first-class backend feature
  - Touches: `browser-extension/popup.html`, `popup.js`, `services/api.py`
  - Acceptance: Save with "Read Later" → appears in read-later queue
  - Verify: `bop read-later list` shows bookmark

- [ ] P1 - **EXT: Connection test in Options (NF-08)**
  - Why: Configuration errors are opaque until first save attempt
  - Touches: `browser-extension/options.html`, `options.js`
  - Acceptance: "Test Connection" button shows success/failure with details
  - Verify: Wrong port → "Cannot reach API"; correct → "Connected to BOP vX.Y.Z"

- [ ] P1 - **EXT: Error recovery UX (EI-06)**
  - Why: "Cannot reach the local API" gives no troubleshooting path
  - Touches: `browser-extension/popup.js` lines 141-143
  - Acceptance: Specific error messages for each failure mode
  - Verify: Stop API → popup shows "Start BOP or run `bop api-server`"

- [ ] P1 - **GUI: Wire Help menu (R-62)**
  - Why: No Help menu exists; AboutDialog and search syntax docs are unreachable
  - Touches: `app.py` or `app_mixins/` (menu creation), `ui/about.py`
  - Acceptance: Help menu with Search Syntax, Keyboard Shortcuts, About
  - Verify: Help → About → dialog opens with correct information

- [ ] P1 - **GUI: Fix About dialog accuracy (R-63, R-64, EI-05)**
  - Why: False feature claims (System Tray, drag-and-drop) and AI attribution
  - Touches: `ui/about.py`
  - Acceptance: All listed features are real; no AI attribution line
  - Verify: Read About dialog → every feature is verifiable

- [ ] P1 - **SEC: Windows ACL on sensitive files (R-55, EI-04)**
  - Why: Token files readable by all local users on primary platform
  - Touches: `services/api.py`, `ai.py`, `services/mcp_auth.py`
  - Acceptance: After token creation, `icacls` shows only current user has access
  - Verify: `icacls %USERPROFILE%\.bookmark_organizer\api_token.txt`

- [ ] P1 - **PERF: Batch save context manager (R-73)**
  - Why: Every mutation triggers full-file JSON serialization; O(n) per operation
  - Touches: `managers/bookmarks.py` (add `batch()` context manager)
  - Acceptance: `with manager.batch(): [add 100 bookmarks]` triggers one save
  - Verify: Import 1000 bookmarks → measure time before/after

### Phase 3 — GUI Chat, Surfaces, and Polish (v7.0)

- [ ] P1 - **GUI: RAG chat panel (R-60)**
  - Why: Most differentiating feature; backend complete but GUI-invisible; Raindrop Stella and Markwise define the category
  - Touches: New UI module, `services/rag_chat.py` integration
  - Acceptance: Sidebar/dialog where user types question → gets cited answer with bookmark links
  - Verify: Ask "what did I save about Python?" → get relevant bookmarks with citations

- [ ] P1 - **GUI: Surfaces for Read Later, Flows, RSS (R-67)**
  - Why: 3 complete backend services with zero GUI exposure
  - Touches: `app.py` or `app_mixins/`, new sidebar sections
  - Acceptance: Collapsible sidebar sections for each feature
  - Verify: Click "Read Later" sidebar → see queued bookmarks

- [ ] P1 - **GUI: Import/export parity (R-68)**
  - Why: 7 importers and 6 export formats are CLI-only
  - Touches: Import menu, Export dialog
  - Acceptance: All 14 importers and 12 export formats accessible from GUI
  - Verify: File → Import → see Pocket, Readwise, Pinboard, etc.

- [ ] P1 - **GUI: Replace hardcoded Segoe UI fonts (R-65)**
  - Why: 35+ references bypass FONTS system; breaks macOS/Linux rendering
  - Touches: 12 UI files
  - Acceptance: `grep -r "Segoe UI" bookmark_organizer_pro/ui/` → 0 results
  - Verify: Run on macOS → fonts render correctly

- [ ] P2 - **GUI: Expand command palette to 35+ commands (R-69)**
  - Why: Only 18 of 40+ actions registered
  - Touches: `ui/` command palette module
  - Acceptance: Toggle Pin, Copy URL, Delete, About, AI tools all accessible via palette
  - Verify: Ctrl+K → type "pin" → see "Toggle Pin" action

- [ ] P2 - **GUI: Extend bookmark editor (R-70)**
  - Why: Editor only shows URL/title/category/tags; missing notes, description, pin, read-later
  - Touches: Bookmark edit dialog UI
  - Acceptance: All Bookmark model fields editable in GUI
  - Verify: Edit bookmark → see notes, pin toggle, read-later checkbox

- [ ] P2 - **EXT: API category/tag autocomplete (NF-03)**
  - Why: Autocomplete from live app data (not just static bundled list)
  - Touches: `api.py` (auth on GET), `popup.js` (fetch + datalist)
  - Acceptance: Extension fetches live categories/tags from API with auth
  - Verify: Add new category in app → extension shows it in autocomplete

- [ ] P2 - **EXT: Duplicate check on popup open (NF-10)**
  - Why: Pre-check saves wasted save attempts
  - Touches: `api.py` (new check endpoint), `popup.js`
  - Acceptance: Popup shows "Already saved" for existing bookmarks
  - Verify: Open popup on saved page → see indicator

- [ ] P2 - **QUAL: Remove 4 dead UI view classes (R-66)**
  - Why: ~670 lines of dead code (KanbanView, TimelineView, ReadingListView, TagCloudView)
  - Touches: `ui/` view files
  - Acceptance: Dead classes removed; test suite still passes
  - Verify: `grep -r "KanbanView\|TimelineView\|ReadingListView\|TagCloudView" bookmark_organizer_pro/` → 0 results

### Phase 4 — Architecture & Distribution (v7.x)

- [ ] P2 - **ARCH: File-change watching for MCP+GUI sync (R-74)**
  - Why: MCP and GUI create independent managers; concurrent edits don't sync
  - Touches: `managers/bookmarks.py`, `mcp_server.py`
  - Acceptance: Edit via MCP → GUI auto-refreshes within 5s
  - Verify: Add bookmark via MCP → see it appear in GUI

- [ ] P2 - **ARCH: SQLite migration (optional) (R-31)**
  - Why: JSON won't scale past 100K bookmarks; WAL mode enables concurrent access for web client
  - Touches: New storage backend, migration tool
  - Acceptance: opt-in `bop migrate-sqlite` → creates SQLite DB → all features work
  - Verify: Import 100K bookmarks → search performance acceptable

- [ ] P2 - **DIST: Nuitka compilation (R-40)**
  - Why: Fewer AV false positives than PyInstaller, 2-4x faster startup
  - Touches: Build scripts, CI/CD
  - Acceptance: `nuitka --standalone main.py` produces working binary
  - Verify: Run binary → all features work

- [ ] P2 - **TEST: Service module coverage expansion (R-78)**
  - Why: 27 of 35 service modules lack tests
  - Touches: `tests/` (new test files)
  - Acceptance: Priority modules (snapshot, hybrid_search, rag_chat, nl_query, dead_link_scanner) at ≥80% coverage
  - Verify: `pytest --cov=bookmark_organizer_pro/services/ tests/`

- [ ] P2 - **A11Y: Keyboard accessibility (R-48)**
  - Why: Tab order, focus indicators, screen reader labels are missing
  - Touches: All major UI widgets
  - Acceptance: Full keyboard navigation of treeview/sidebar/search/toolbar
  - Verify: Tab through all UI elements → each receives visible focus

- [ ] P2 - **MCP: 2026-07-28 spec migration (R-58)**
  - Why: Biggest MCP revision — stateless protocol, caching, OAuth 2.0
  - Touches: `mcp_server.py`, `requirements.txt`
  - Acceptance: Server complies with 2026-07-28 spec
  - Verify: Connect with updated MCP SDK → all tools work

- [ ] P2 - **API: Pagination with offset (NF-09)**
  - Why: Can't paginate through large libraries
  - Touches: `services/api.py`
  - Acceptance: `?offset=50&limit=50` returns bookmarks 50-99
  - Verify: `curl ...?limit=10&offset=10` → correct results

---

## Quick Wins

| Item | Effort | Impact | Location |
|------|--------|--------|----------|
| Add extension icons (NF-05) | S | High — Chrome Web Store required | `browser-extension/manifest.json`, `icons/` |
| Add keyboard shortcut (NF-04) | S | Medium — power user retention | `browser-extension/manifest.json` |
| Connection test button (NF-08) | S | Medium — reduces support burden | `browser-extension/options.js` |
| Error recovery messages (EI-06) | S | Medium — reduces confusion | `browser-extension/popup.js` |
| Fix About dialog (EI-05) | S | Low — trust signal | `ui/about.py` |
| Bump cryptography (R-51) | S | High — CVE closure | `requirements.txt` |
| CSP meta header in archives (EI-03) | S | High — defense in depth | `services/web_tools.py` |
| API pagination offset (NF-09) | S | Medium — future-proofing | `services/api.py` |
| Version sync check in tests (EI-07) | S | Low — prevents drift | `tests/` |
| Extract DEFAULTS in extension (refactor) | S | Low — DRY | `browser-extension/` |

---

## Larger Bets

| Item | Effort | Risk | Payoff |
|------|--------|------|--------|
| GUI chat panel (R-60) | L | Medium — Tkinter chat UX is hard to polish | Very high — most differentiating feature |
| SQLite migration (R-31) | XL | High — data migration, dual-backend | High — unlocks web client and concurrent access |
| Web client (R-02) | XL | High — new surface area, security | Very high — cross-device access |
| Nuitka compilation (R-40) | L | Medium — untested with this codebase | High — better distribution, fewer AV issues |
| Reader view with annotations (R-21) | L | Medium — complex UI | High — paywalled at competitors ($38-156/yr) |
| Graph view (R-22) | L | High — Tkinter canvas performance | Medium — niche appeal |
| MCP 2026-07-28 spec migration (R-58) | L | Medium — breaking changes | High — ecosystem compliance |

---

## Explicit Non-Goals

| Idea | Reason |
|------|--------|
| Multi-user / team features | Contradicts local-first single-user design; Linkwarden/Linkding serve teams |
| Docker as primary deployment | No-Docker is a differentiator; Docker support fine but never required |
| Cloud-hosted SaaS | Premature; stabilize desktop + MCP + extension first |
| Full language rewrite (Rust/Go/TS) | Python ecosystem (fastembed, lancedb, mcp, trafilatura) is the stack |
| Native mobile apps (iOS/Android) | PWA via future web client covers 90%; native too expensive |
| AI-only organization (no manual) | "AI assists, user decides" is core philosophy |
| Subscription pricing | BOP is free and local-first; compete on sovereignty, not price |
| 24-hour triage/auto-delete | Burn 451's model causes data anxiety; contradicts archival philosophy |
| CustomTkinter migration | ROADMAP already considered and rejected; sv-ttk is the path (R-18) |
| Browser extension for Safari | Requires entirely different architecture (App Extension); defer to web client |

---

## Open Questions

1. **Extension distribution strategy:** Chrome Web Store submission requires $5 developer fee + review process. Firefox Add-on submission is free. Should BOP target one first, or ship both simultaneously? (Decision needed before extension icons are finalized for store listing.)

2. **FastMCP 3.x compatibility:** ROADMAP targets FastMCP ≥3.4 (R-59). Current `mcp_server.py` uses raw `mcp` SDK with optional FastMCP. Does the migration require restructuring around Provider/Transform architecture, or is it a drop-in upgrade? (Requires reading FastMCP 3.x migration guide.)

3. **Extension category data sync:** Should extension categories be (a) bundled static JSON only, (b) API-fetched with static fallback, or (c) synced via native messaging? Option (b) is the recommended middle ground, but (c) enables real-time sync without API server dependency. (Architecture decision before NF-02/NF-03.)

4. **Service worker background save:** Should the context menu (NF-01) save immediately (background fetch in service worker) or open the popup pre-filled? Immediate save is faster but gives no feedback on category/tags. Competitors split: Raindrop saves immediately, Karakeep opens popup. (UX decision.)

---

## Relationship to ROADMAP.md

This research plan is a **companion** to ROADMAP.md v4.0, not a replacement. ROADMAP.md is the canonical planning document with 78 items across 10 themes and 120 cited sources. This plan adds:

- **10 new feature proposals** (NF-01 through NF-10) focused on browser extension and API improvements
- **8 existing feature improvements** (EI-01 through EI-08) with specific code locations and verification plans
- **Verified security findings** with exact line numbers and OWASP classifications
- **Competitive landscape update** including ContextBolt, Bookmarkjar, and Chrome MCP extensions
- **Implementation-ready acceptance criteria** for every roadmap item

Items identified here that overlap with ROADMAP are cross-referenced by R-number and not duplicated.
