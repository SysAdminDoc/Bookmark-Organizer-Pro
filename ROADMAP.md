# Bookmark Organizer Pro — Roadmap

> **Version:** 5.0 · **Date:** 2026-06-05 · **Covers:** v6.5.0 → v8.x
> **Single source of truth** for all planned work.
> Supersedes ROADMAP v4.x. Prior research archived under `docs/research/`.

---

## How to Read This

| Symbol | Meaning |
|--------|---------|
| ✅ | Done (shipped in v6.4.1 or earlier) |
| 🔲 | Open — implementation not started |
| 🚧 | In progress or partially shipped |
| S/M/L/XL | Effort estimate (days: 0.5 / 1-2 / 3-5 / 1-2 weeks) |

**Tiers:** Now (ship before next release) → Next (v7.0) → Later (v7.x+) → Under Consideration → Rejected

**Every item is traceable** to a source in the [Appendix](#appendix-sources). Items without sources are rejected.

---

## State of the Project (v6.4.1)

Bookmark Organizer Pro is a **local-first, privacy-centric** Python/Tkinter bookmark manager. At v6.4.1:

- **AI:** 6 providers (OpenAI, Anthropic, Gemini, Groq, Ollama, DeepSeek), auto-categorization with 7,500+ patterns across 43 categories, tag suggestions, title improvement, citation-aware summaries, conversational RAG, NL-to-structured-query
- **Search:** Full-text boolean (15+ filter types) + semantic vector (LanceDB + FastEmbed) + hybrid RRF + optional cross-encoder re-rank
- **MCP server:** 20 typed tools — one of ~4 bookmark managers with MCP (alongside Raindrop.io, Karakeep, Burn 451) [S-60][S-74][S-78]
- **Preservation:** Single-file HTML snapshots (4-backend chain: monolith → singlefile → playwright → python), dead-link scanner, Wayback Machine, auto-snapshot scheduler
- **Security:** AES-256-GCM encrypted DB, SSRF guards, prompt sanitization, API auth tokens, keyring storage
- **Import/Export:** 14 importers (incl. Pocket, Readwise, Pinboard, Instapaper, Reddit, Matter, Zotero), 12 export formats (HTML/JSON/CSV/OPML/XBEL/Markdown/ZIP/Obsidian/EPUB/Atom/JSON Feed/Zotero RDF)
- **UI:** 11 themes (incl. WCAG AA high-contrast), command palette, toast notifications, zoom, high-DPI, dashboard analytics
- **CLI:** 37 subcommands, 255 tests across 5 files
- **Desktop:** Python ≥3.10, Tkinter, PyInstaller binary, cross-platform (Windows primary, macOS/Linux)

### Competitive Position (June 2026)

| Competitor | Stars | MCP | Browser Ext | Semantic Search | AI Tag | Local-First | Desktop GUI |
|-----------|-------|-----|-------------|-----------------|--------|-------------|-------------|
| Karakeep | 25.9K | ✅ | ✅ Chrome/FF/Safari | Meilisearch FTS | ✅ | ❌ Docker | ❌ Web |
| Linkwarden | 18.5K | Community | ✅ Chrome/FF | Meilisearch FTS | ✅ | ❌ Docker | ❌ Web |
| Wallabag | 12.8K | ❌ | ✅ Chrome/FF | FTS | ❌ | ❌ Docker | ❌ Web |
| Linkding | 10.7K | Community | ✅ Chrome/FF | FTS | ❌ | ❌ Docker | ❌ Web |
| ArchiveBox | 27.6K | Community | ❌ | ❌ | Plugin | ❌ Docker | ❌ Web |
| Buku | 7.1K | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ CLI |
| Faved | 1.1K | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ Web/PWA |
| Raindrop.io | N/A | ✅ | ✅ All | ✅ (Pro) | ✅ Stella | ❌ Cloud | ❌ Web |
| Burn 451 | N/A | ✅ 22 tools | ✅ Chrome | ✅ | ✅ | ❌ Cloud | ❌ Web |
| Bookmark Lens | small | ✅ | ❌ | ✅ LanceDB | ✅ | ✅ | ❌ MCP-only |
| **BOP** | public | ✅ 20 tools | ❌ | ✅ LanceDB | ✅ 6 providers | ✅ | ✅ Tkinter |

**BOP's uncontested niche:** Desktop-native + local-first + MCP + semantic search + AI. No competitor occupies this exact intersection. **BOP is the only OSS bookmark manager with semantic/vector search** — zero competitors ship embeddings or vector similarity. The threat is not direct competition — it's Karakeep/Linkwarden web UIs accessed via local Docker, and Burn 451/Raindrop.io MCP servers that integrate better with AI workflows.

**Competitive window narrowing:** Karakeep shipped MCP (v0.24.0), browser extensions (Chrome/FF/Safari + SingleFile-in-extension), and grew to 25.9K stars. Raindrop.io launched Stella (AI chat over bookmarks + MCP). Burn 451 has 22 MCP tools vs BOP's 20. Bookmark Lens entered the local-first + LanceDB + MCP niche. New entrants: Faved (1.1K stars, local-first), LazyCat Bookmark Cleaner (1.8K stars, AI extension), Eclaire (864 stars, local-first AI PKM). The browser extension gap (R-01) and GUI chat panel are critical differentiators to ship.

**What BOP offers free that commercial tools paywall ($38-156/yr):** Full-text search, AI auto-tagging, semantic search, page archiving, MCP server, conversational RAG, citation-aware summaries, dead-link scanning. The biggest missing feature vs commercial tools is highlights/annotations (R-21) — paywalled at Raindrop ($38/yr), Readwise ($120/yr), and Diigo ($40/yr).

### Cycle Note — v4.0 (2026-06-05)

This roadmap revision is a ground-up rewrite informed by 120 cited sources across OSS competitors (13+), commercial services (14), adjacent-domain projects (10), dependency changelogs (10), CVE databases (6 CVEs), MCP spec evolution, community forums (Reddit/HN/Lobsters/dev.to), awesome-lists, and review articles. Key changes from v3.x:

- **Elevated security:** 2 new CVEs in `cryptography` (buffer overflow + cert bypass). MCP zero-auth and XXE vulnerabilities escalated to Now tier.
- **MCP ecosystem shift:** MCP is no longer unique — Raindrop.io, Karakeep, Burn 451, and Bookmark Lens all ship MCP servers. BOP must add write tools and migrate to the 2026-07-28 stateless spec to stay competitive.
- **Commercial intelligence:** Features BOP offers free (full-text search, AI tagging, page archiving, MCP) are paywalled at $38-156/year across commercial tools. Highlights/annotations (R-21) is the biggest gap vs Readwise Reader ($120/yr) and Linkwarden.
- **New items:** 28 new roadmap items (R-51 through R-78). 40 completed items collapsed into summary.
- **Web client dropped to Later:** XL effort + SQLite prerequisite chain makes it unrealistic before v7.x.
- **Nuitka promoted:** 4.0/4.1 release (April 2026) with 1500% compile speedup and confirmed Tkinter support makes it production-ready. Promoted from Later to Next.

### Hard Constraints

- MIT license
- Python ≥ 3.10, Tkinter GUI (no Electron/Tauri rewrite)
- Local-first: no mandatory server, no cloud dependency, no Docker requirement
- Optional deps must degrade gracefully — core works with zero extras installed
- Windows-primary, cross-platform (macOS, Linux)
- User data sovereignty: AI assists, user decides; never auto-delete or auto-merge

---

## Theme 1 — Security & Hardening

*Three critical vulnerabilities identified in the v6.4.0 audit remain open. Two new CVEs affect core dependencies.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-51 | **Bump `cryptography` to ≥46.0.7** — CVE-2026-39892 and CVE-2026-34073. Floor bumped in requirements.txt + pyproject.toml. | Done | S | [S-75][S-76] |
| ✅ R-52 | **Wire MCP authentication enforcement** — MCPTokenManager imported and wired into `_call_tool`. Open mode when no tokens configured; enforces read-only/read-write scopes otherwise. | Done | M | [S-1] |
| ✅ R-53 | **Fix XXE in OPML/XBEL importers** — defusedxml integrated in importers.py and xbel.py with try/except fallback. defusedxml added to core deps. | Done | S | [S-1][S-38] |
| ✅ R-54 | **Sanitize LocalArchiver HTML output** — `<script>` tags and `on*` handlers stripped. CSP `script-src 'none'` meta header added. | Done | S | [S-1] |
| ✅ R-55 | **Windows ACL on sensitive files** — `api_token.txt` now uses `icacls` to restrict to current user on Windows. | Done | S | [S-1] |
| ✅ R-56 | **REST API GET auth** — `_check_auth()` now required for all GET endpoints except root `/`. | Done | S | [S-1] |
| ✅ R-36 | ReDoS timeout on pattern engine regex | Done | S | [S-1] |
| ✅ R-36b | Pillow upgraded to ≥12.2.0 (3 CVEs) | Done | S | [S-51] |
| ✅ R-37 | SSRF allow-list | Done | M | [S-1] |
| ✅ R-38 | Passphrase rotation | Done | M | [S-1] |
| ✅ R-39 | Telemetry-free mode banner | Done | S | [S-1] |
| ✅ R-35 | API key storage via keyring | Done | M | [S-1] |

**Justification:** CVE-2026-39892 is a buffer overflow rated Moderate but could cause DoS in any BOP workflow that uses encryption. MCP zero-auth is the single biggest security gap — any process on localhost can manipulate the library. XXE and stored XSS are standard OWASP top-10 that damage credibility for a tool advertising "privacy-centric" and "local-first."

---

## Theme 2 — Platform Reach

*The single biggest limitation: BOP has no browser extension, no web client, no mobile access.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-01 | **Browser extension (MV3)** — Popup with category autocomplete (bundled JSON), read-later toggle, context menu ("Save to BOP" + "Save with selection"), Ctrl+Shift+B shortcut, 4 icon sizes, Test Connection in options, improved error messages. Chrome + Firefox MV3. | Done | L | [S-3][S-5][S-7][S-10][S-20][S-69][S-70][S-106] |
| ✅ R-04 | Bookmarklet fallback | Done | S | [S-6][S-10] |
| 🔲 R-02 | **Web client (FastAPI + HTMX)** — read/search/add from any device. PWA manifest for mobile install. Read-only by default, auth-gated mutations. Depends on SQLite migration (R-31). | Later | XL | [S-3][S-5][S-6][S-8][S-12] |
| 🔲 R-03 | **Mobile PWA share-intent** — Android "Share to BOP" target via the web client, auto-categorize on receipt. | Later | M | [S-8][S-12] |

**Justification:** "No extension" is the #1 complaint in r/selfhosted bookmark threads [S-20]. Every major competitor ships one: Karakeep (Chrome/FF/Safari with SingleFile integrated) [S-70], Linkwarden (Chrome/FF) [S-69], Linkding, Wallabag, Raindrop.io, Burn 451. The bookmarklet (R-04) is an interim bridge. Web client dropped to Later because SQLite prerequisite (R-31) makes it an XL chain.

---

## Theme 3 — MCP & AI Integration

*BOP's MCP server + RAG + semantic search combo is shared with only 3 other tools (Raindrop, Karakeep, Burn 451). Protect the lead and adapt to the evolving spec.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-57 | **MCP write tools** — 6 new tools: `delete_bookmark`, `update_bookmark`, `toggle_pin`, `mark_read_later`, `add_tags`, `remove_tags`. Total 26 tools. | Done | M | [S-1][S-78] |
| 🔲 R-58 | **MCP 2026-07-28 spec migration** — adapt to stateless protocol (no Mcp-Session-Id), add Mcp-Method/Mcp-Name headers, implement ttlMs + cacheScope on list results. Required for SDK Tier 1 compliance. | Next | L | [S-79][S-80] |
| 🔲 R-59 | **FastMCP 3.x upgrade** — bump from ≥2.0 to ≥3.4. Gains: OAuth auto-enable for HTTPS, OTEL spans on tool execution, fastmcp-remote for connecting stdio hosts to remote servers, meta-tools. | Next | M | [S-81] |
| 🔲 R-60 | **GUI chat panel** — sidebar or dialog for RAG chat. User types question, gets cited answers with bookmark links. `rag_chat.py` backend is complete but GUI-invisible. Most differentiating feature. Markwise and Raindrop Stella define the category. | Next | L | [S-1][S-65][S-82] |
| ✅ R-61 | **Nomic Embed v2 support** — Added NOMIC_MODEL constant + RECOMMENDED_MODELS dict + CLI `--model=nomic` flag for embed command. | Done | S | [S-83] |
| ✅ R-05 | FastMCP migration (2.x) | Done | M | [S-14][S-15] |
| ✅ R-06 | MCP tools: create_flow, append_to_flow, export_zip, list_snapshots | Done | M | [S-14] |
| ✅ R-07 | Cross-encoder re-rank | Done | M | [S-16][S-17] |
| ✅ R-08 | Chunk-level RAG provenance | Done | M | [S-1] |
| ✅ R-09 | Time-weighted recall | Done | S | [S-1] |
| ✅ R-10 | Collections as retrieval scopes | Done | M | [S-1][S-10] |
| ✅ R-11 | Answer caching | Done | S | [S-1] |
| ✅ R-12 | YouTube transcript capture | Done | M | [S-6][S-18] |
| ✅ R-13 | Smart Collections | Done | M | [S-10][S-19] |
| ✅ R-14 | MCP auth scopes | Done | M | [S-14] |
| 🔲 R-15 | **MCP streaming** for `chat_with_collection` — stream RAG responses token-by-token. Depends on FastMCP 3.x streaming support. | Later | M | [S-14][S-79] |

**Justification:** MCP write tools are needed for AI agent curation workflows (Burn 451 already ships delete/update). The 2026-07-28 spec is the biggest MCP revision since launch — going stateless, adding caching, aligning with OAuth 2.0 [S-79]. FastMCP 3.4 brings OTEL observability and remote server support [S-81]. GUI chat panel is the #1 feature gap vs Raindrop Stella and Markwise.

---

## Theme 4 — UI Quality & Performance

*Tkinter is the stack. Modernize within it. Fix the GUI-CLI parity gap (15+ CLI-only features).*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-62 | **Help menu with Search Syntax, Shortcuts, About** — Help menu added with Search Syntax (from SearchEngine), Keyboard Shortcuts list, and About dialog. All with Escape-to-close. | Done | S | [S-1] |
| ✅ R-63 | **Remove AI reference from About credits** — already removed in prior pass; verified clean. | Done | S | [S-1] |
| ✅ R-64 | **Fix About dialog false feature claims** — System Tray, drag-and-drop removed from features list. Undo/Redo scope clarified. | Done | S | [S-1] |
| ✅ R-65 | **Replace 35+ hardcoded Segoe UI fonts** — 24 hardcoded font tuples replaced across 9 UI files with FONTS.body/small/custom calls. | Done | M | [S-1] |
| ✅ R-66 | **Remove 4 dead UI view classes** — secondary_views.py deleted (~670 lines). Imports removed from ui/__init__.py. | Done | S | [S-1] |
| 🔲 R-16 | **List virtualization via tksheet** — replace Treeview with tksheet for virtual scrolling. Handles millions of rows. Pure Python. v7.6.0 is maintenance-only but stable. | Now | L | [S-22][S-23][S-71] |
| 🔲 R-67 | **GUI surfaces for Read Later, Flows, RSS** — 3 complete backend services with zero GUI exposure. Add collapsible sidebar sections. | Next | L | [S-1] |
| ✅ R-68 | **GUI import/export parity** — 9 service importers (Pocket, Readwise, Pinboard, Instapaper, Reddit, Matter, Wallabag, Arc, Zotero) added to Import menu with file choosers. | Done | M | [S-1] |
| ✅ R-69 | **Expand command palette to 35+ commands** — expanded from 19 to 35 commands: Toggle Pin, Copy URL, Delete, Zoom, Flatten, Clear Categories/Tags, AI Improve Titles, Organize, Help menus. | Done | M | [S-1] |
| ✅ R-70 | **Extend bookmark editor** — added read-later checkbox. Editor already had URL/title/category/tags/notes/pinned/archived. | Done | M | [S-1] |
| ✅ R-71 | **Theme-aware DependencyCheckDialog** — all ~40 hardcoded Catppuccin Mocha colors replaced with `get_theme()` tokens. | Done | M | [S-1] |
| ✅ R-72 | **Add Escape-to-close on 8 modal dialogs** — DependencyCheckDialog, ThemeSelectorDialog, BulkTagEditorDialog, EmojiPicker now have Escape binding. | Done | S | [S-1] |
| ✅ R-73 | **Batch save context manager** — `BookmarkManager.batch()` context manager suppresses per-mutation saves; single flush on exit. Nestable. | Done | M | [S-1] |
| ✅ R-74 | **File-change watching for MCP+GUI co-existence** — `BookmarkManager.start_file_watcher()` polls mtime every 5s, reloads on external change, calls optional GUI refresh callback. | Done | M | [S-1] |
| 🔲 R-17 | **Tree view alongside list view** — hierarchical category tree for deeply nested collections. | Next | M | [S-3][S-5] |
| 🔲 R-18 | **sv-ttk theme integration** — Windows 11 Sun Valley look. v2.6.1 actively maintained, Python 3.9-3.13. | Later | M | [S-24][S-72] |
| ✅ R-19 | Fix command palette FocusOut | Done | S | [S-1] |
| ✅ R-20 | Fix GridView scroll stealing | Done | S | [S-1] |
| 🔲 R-21 | **Reader view with highlight/annotation** — open extracted text in a reader pane. 4-color highlights, per-highlight notes. Export to Markdown. Linkwarden 2.14 ships this. | Later | L | [S-3][S-10][S-11][S-84] |
| 🔲 R-22 | **Graph view** — bookmarks as nodes, tags as edges, force-directed layout. | Later | L | [S-4] |

---

## Theme 5 — Preservation & Content

*Snapshots and content extraction differentiate BOP vs minimal tools like Linkding/Buku.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-23 | Headless Chromium snapshot fallback (playwright) | Done | M | [S-1][S-3] |
| ✅ R-24 | Scheduled auto-snapshot | Done | M | [S-1] |
| ✅ R-25 | EPUB export of collections | Done | M | [S-6][S-18] |
| 🔲 R-26 | **OPDS catalog** — serve collections to e-reader apps (Readeck-style). | Later | M | [S-6] |

---

## Theme 6 — Import / Export / Interop

*Pocket and Omnivore are dead. Arc Browser shut down May 2025. BOP is the landing pad.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-27 | Zotero RDF import/export | Done | M | [S-1] |
| ✅ R-28 | Matter CSV importer | Done | S | [S-1] |
| ✅ R-29 | Atom + JSON Feed export | Done | S | [S-1] |
| ✅ R-30 | Obsidian vault export | Done | M | [S-1][S-11] |
| ✅ R-75 | **Wallabag JSON importer** — WallabagJSONImporter added to importers_extra.py. Maps is_starred to pinned, tag objects to tag list. CLI + GUI menu entry. | Done | S | [S-8][S-85] |
| ✅ R-76 | **Arc Browser importer** — ArcBrowserImporter parses StorableSidebar.json with recursive folder walk. CLI + GUI menu entry. | Done | S | [S-86] |
| ✅ R-77 | **Shell completion scripts** — Static bash/zsh/fish completions in scripts/completions/. Covers all 41 subcommands + flow/feed/read-later/embed subargs. | Done | S | [S-31] |

---

## Theme 7 — Data Architecture

*JSON file storage works for thousands of bookmarks but won't scale to 100K+.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-31 | **SQLite migration (optional)** — WAL mode unlocks concurrent access for web client. JSON remains default. Migration tool on opt-in. | Next | XL | [S-7][S-9] |
| ✅ R-32 | Per-backup integrity hash (SHA-256) | Done | S | [S-1] |
| ✅ R-33 | Deduplicate cross-category patterns | Done | M | [S-1] |
| ✅ R-34 | Fix overly broad plain patterns | Done | M | [S-1] |

---

## Theme 8 — Distribution & Packaging

*PyInstaller works but has AV false-positive problems. No auto-update.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-40 | **Nuitka compilation** — Python-to-C, fewer AV false positives, 2-4x faster startup. Nuitka 4.0/4.1 shipped April 2026 with 1500% compilation speedup and confirmed Tkinter support. Now production-ready. | Next | L | [S-27][S-87] |
| 🔲 R-41 | **tufup auto-update** — TUF-based binary diff patches. Works with PyInstaller or Nuitka. v0.10.0 on PyPI, actively maintained. | Later | M | [S-28][S-88] |
| ✅ R-42 | Python version matrix in CI (3.10-3.13) | Done | S | [S-1] |

---

## Theme 9 — Testing & Quality

*255 test methods across 5 files. 27 of 35 service modules still untested.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-43 | Service layer test suite (26 tests) | Done | L | [S-1] |
| ✅ R-44 | MCP server integration tests (20 tests) | Done | M | [S-1] |
| ✅ R-45 | CLI smoke test suite (21 tests) | Done | M | [S-1] |
| ✅ R-46 | Remove ~1,409 lines dead code | Done | S | [S-1] |
| ✅ R-47 | Fix copy-pasted model docstrings | Done | S | [S-1] |
| ✅ R-78 | **Untested service coverage** — 16 new tests across 8 classes: HybridSearch, NLQuery, DeadLinkScanner, WallabagImporter, ArcImporter, BatchSave, SnapshotArchiver, EmbeddingModels. | Done | L | [S-1] |

---

## Theme 10 — Accessibility & i18n

*Desktop apps are not exempt from accessibility. i18n is a multiplier for OSS adoption.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-48 | **Keyboard accessibility** — tab order across treeview/sidebar/search/toolbar, column sort via keyboard, screen reader labels. WCAG 2.2 focus-appearance (2.4.11, 2.4.13). Min 24×24px click targets (2.5.8). | Next | L | [S-29][S-63] |
| ✅ R-49 | High-contrast WCAG AA theme | Done | S | [S-29][S-63] |
| 🔲 R-50 | **gettext i18n scaffolding** — extract user-facing strings, `.po` file structure, `CONTRIBUTING.md` section for translators. Infrastructure only, no translations yet. | Later | M | [S-30][S-68] |

---

## Completed Items Summary

All items below shipped in v6.0.0 through v6.4.1. Full details in [CHANGELOG.md](CHANGELOG.md).

<details>
<summary>40 completed roadmap items (click to expand)</summary>

| ID | Item | Version |
|----|------|---------|
| R-04 | Bookmarklet generator | v6.2.0 |
| R-05 | FastMCP 2.x migration | v6.2.0 |
| R-06 | 4 new MCP tools (create_flow, append_to_flow, export_zip, list_snapshots) | v6.2.0 |
| R-07 | Cross-encoder re-rank after RRF | v6.3.0 |
| R-08 | Chunk-level RAG provenance | v6.3.0 |
| R-09 | Time-weighted recall | v6.2.0 |
| R-10 | Collections as retrieval scopes | v6.3.0 |
| R-11 | Answer caching (LRU 128 entries) | v6.3.0 |
| R-12 | YouTube transcript capture | v6.3.0 |
| R-13 | Smart Collections | v6.2.0 |
| R-14 | MCP auth scopes (MCPTokenManager) | v6.3.0 |
| R-19 | Fix command palette FocusOut | v6.2.0 |
| R-20 | Fix GridView scroll stealing | v6.2.0 |
| R-23 | Headless Chromium snapshot (playwright) | v6.2.0 |
| R-24 | Scheduled auto-snapshot | v6.3.0 |
| R-25 | EPUB export | v6.2.0 |
| R-27 | Zotero RDF import/export | v6.3.0 |
| R-28 | Matter CSV importer | v6.3.0 |
| R-29 | Atom + JSON Feed export | v6.3.0 |
| R-30 | Obsidian vault export (CLI + MCP) | v6.2.0 |
| R-32 | Per-backup SHA-256 integrity hash | v6.2.0 |
| R-33 | Deduplicate cross-category patterns | v6.2.0 |
| R-34 | Fix overly broad plain patterns | v6.2.0 |
| R-35 | API key storage via keyring | v6.3.0 |
| R-36 | ReDoS timeout on pattern engine regex | v6.2.0 |
| R-36b | Pillow upgraded to ≥12.2.0 (3 CVEs) | v6.2.0 |
| R-37 | SSRF allow-list | v6.3.0 |
| R-38 | Passphrase rotation | v6.3.0 |
| R-39 | Telemetry-free mode banner | v6.2.0 |
| R-42 | Python version matrix in CI | v6.2.0 |
| R-43 | Service layer test suite (26 tests) | v6.2.0 |
| R-44 | MCP server integration tests (20 tests) | v6.2.0 |
| R-45 | CLI smoke test suite (21 tests) | v6.3.0 |
| R-46 | Remove ~1,409 lines dead code | v6.2.0 |
| R-47 | Fix copy-pasted model docstrings | v6.2.0 |
| R-49 | High-contrast WCAG AA theme | v6.2.0 |
| BUG-01 through BUG-14 | All 14 known bugs fixed | v6.2.0-v6.4.1 |
| + 30 v6.1.0 fixes | AI batch processor, chunk overlap, MCP schemas, CI flow, thread safety, etc. | v6.1.0 |

</details>

---

## Rejected (with reasoning)

| Idea | Source | Reason |
|------|--------|--------|
| Multi-user / team features | [S-3][S-7] | Contradicts local-first single-user design. Linkwarden and Linkding serve teams. |
| Docker as primary deployment | [S-5][S-3] | No-Docker is a differentiator. Docker *support* is fine but never required. |
| Meilisearch/Elasticsearch sidecar | [S-5] | Built-in FTS + LanceDB is a simplicity advantage. No external search infra. |
| Cloud-hosted SaaS | — | Premature. Stabilize desktop + MCP + extension first. |
| Native mobile apps (iOS/Android) | — | PWA via web client covers 90%. Native too expensive for single maintainer. |
| Full language rewrite (Rust/Go/TS) | — | Python ecosystem (fastembed, lancedb, mcp, trafilatura) is the stack. Nuitka for perf. |
| AI-only organization (no manual) | [S-19] | "AI assists, user decides" is core philosophy. |
| Browser-history import (full) | — | Privacy risk too high. One-off migration aid only if explicitly requested. |
| CustomTkinter migration | [S-24] | Stagnating (no releases in 12+ months). sv-ttk is the alternative. |
| Subscription pricing | — | BOP is free and local-first. Compete on sovereignty and features, not price. |
| 24-hour triage/auto-delete | [S-78] | Burn 451's model causes data anxiety. Contradicts archival philosophy. |

---

## Under Consideration

These ideas surfaced in research but need more validation before committing:

| Idea | Source | Open Question |
|------|--------|---------------|
| **Plugin API via `entry_points`** — community importers without forking | [S-1] | Is there demand? No community contributors yet. Ship when there's a second contributor. |
| **WARC dual-archive** alongside HTML snapshots | [S-4] | Storage cost doubles. Only if a user requests archival-grade preservation. |
| **Public-share static export** — single HTML per collection, no server | [S-1] | Nice but niche. Build only if the web client ships first. |
| **Auto-highlight extraction** — local LLM finds N highlights per article | [S-1][S-11] | Depends on reader view (R-21) landing first. |
| **Behavioral triage inbox** — amber 7d, red 30d aging indicators | [S-19] | Could cause data anxiety. Needs UX research. |
| **Externalize `default_categories.py` to JSON** — 5,768 lines of inline data | [S-1] | Enables user customization but adds load-time complexity. Ship when the editor exists. |
| **Lazy imports in `__init__.py`** — `__getattr__` for heavyweight subsystems | [S-1] | Measurable startup benefit? Needs profiling. |
| **Embedding model tier selection in GUI** — Fast/Balanced/Best with download progress | [S-1][S-83] | Good UX but depends on model ecosystem stabilizing. |
| **Search history persistence** — persist to settings.json, show dropdown on focus | [S-1] | Low effort, moderate value. Bundle with a UI polish release. |
| **Deduplicate Settings gear / Tools menu** — 3 items appear in both | [S-1] | UX improvement but low severity. |
| **Theme-aware title bar** — light title bar on light themes (Windows) | [S-1] | Nice polish. Bundle with sv-ttk integration. |
| **GoSuki-style browser file monitoring** — watch browser bookmark files via OS events, no extension needed | [S-113] | Alternative to R-01. Lower UX but zero install friction. Evaluate if extension dev stalls. |
| **Floccus/XBEL round-trip verification** — validate BOP's XBEL handler works with Floccus for free cross-browser sync | [S-103] | Unblocks sync without building sync infrastructure. Test-only, S effort. |

---

## Tier Summary

### Now — Ship Before Next Release (1 remaining)

All 12 of 13 Now-tier items shipped in v6.5.0. Remaining:

| # | Item | Effort | Category |
|---|------|--------|----------|
| R-16 | List virtualization via tksheet | L | Performance |

### Next — v7.0 (4 remaining, 8 shipped in v6.5.1)

| # | Item | Effort | Category |
|---|------|--------|----------|
| R-58 | MCP 2026-07-28 spec migration | L | MCP |
| R-59 | FastMCP 3.x upgrade | M | MCP |
| R-60 | GUI chat panel for RAG | L | AI |
| R-67 | GUI surfaces for Read Later, Flows, RSS | L | UI |
| R-31 | SQLite migration (optional) | XL | Architecture |
| R-40 | Nuitka compilation | L | Distribution |
| R-48 | Keyboard accessibility (WCAG 2.2) | L | Accessibility |

### Later — v7.x+ (9 remaining, 7 shipped in v6.5.1)

| # | Item | Effort | Category |
|---|------|--------|----------|
| R-15 | MCP streaming for RAG chat | M | MCP |
| R-17 | Tree view alongside list view | M | UI |
| R-18 | sv-ttk Sun Valley theme integration | M | UI |
| R-21 | Reader view with highlight/annotation | L | UI |
| R-22 | Graph view (force-directed) | L | UI |
| R-26 | OPDS catalog for e-readers | M | Export |
| R-41 | tufup auto-update | M | Distribution |
| R-50 | gettext i18n scaffolding | M | i18n |
| R-02 | Web client (FastAPI + HTMX + PWA) | XL | Platform |
| R-03 | Mobile PWA share-intent | M | Platform |

---

## Appendix: Sources

| ID | Source | URL / Reference |
|----|--------|-----------------|
| S-1 | BOP internal audit (multi-pass review, 2026-06-05) | `docs/research/research-feature-plan-2026-06-05.md` (local) |
| S-2 | BOP CHANGELOG | `CHANGELOG.md` (local) |
| S-3 | Linkwarden — self-hosted bookmark manager | https://github.com/linkwarden/linkwarden |
| S-4 | ArchiveBox — multi-format archiver | https://github.com/ArchiveBox/ArchiveBox |
| S-5 | Karakeep (ex-Hoarder) — AI bookmark everything | https://github.com/karakeep-app/karakeep |
| S-6 | Readeck — Go read-it-later with EPUB/OPDS | https://codeberg.org/readeck/readeck |
| S-7 | Linkding — minimalist self-hosted | https://github.com/sissbruecker/linkding |
| S-8 | Wallabag — PHP read-it-later | https://github.com/wallabag/wallabag |
| S-9 | Shiori — Go Pocket alternative | https://github.com/go-shiori/shiori |
| S-10 | Raindrop.io — cloud bookmark SaaS | https://raindrop.io |
| S-11 | Readwise Reader — highlight/annotation SaaS | https://readwise.io/read |
| S-12 | Omnivore (dead Nov 2024) — read-it-later | https://github.com/omnivore-app/omnivore |
| S-13 | Shaarli — minimalist link share | https://github.com/shaarli/Shaarli |
| S-14 | FastMCP — Python MCP framework | https://github.com/PrefectHQ/fastmcp |
| S-15 | MCP specification | https://modelcontextprotocol.io/specification |
| S-16 | LanceDB — embedded vector database | https://github.com/lancedb/lancedb |
| S-17 | FastEmbed — ONNX embedding inference | https://github.com/qdrant/fastembed |
| S-18 | yt-dlp — video metadata/transcript | https://github.com/yt-dlp/yt-dlp |
| S-19 | mymind / Burn 451 — AI-first bookmarking | https://mymind.com |
| S-20 | r/selfhosted bookmark threads | https://reddit.com/r/selfhosted |
| S-21 | Pocket shutdown (July 2025) | https://support.mozilla.org/en-US/kb/pocket |
| S-22 | tksheet — virtual scrolling for Tkinter | https://github.com/ragardner/tksheet |
| S-23 | tksheet 7.6.0 (maintenance-only) | https://pypi.org/project/tksheet/ |
| S-24 | sv-ttk — Sun Valley theme for ttk | https://github.com/rdbende/Sun-Valley-ttk-theme |
| S-25 | Pocket dead — user migration | https://blog.mozilla.org/en/mozilla/update-on-pocket/ |
| S-26 | Omnivore dead — acquihired by ElevenLabs | https://blog.omnivore.app/p/details-on-omnivore-shutting-down |
| S-27 | Nuitka — Python-to-C compiler | https://nuitka.net |
| S-28 | tufup — TUF-based auto-update | https://github.com/dennisvang/tufup |
| S-29 | WCAG 2.2 quick reference | https://www.w3.org/WAI/WCAG22/quickref/ |
| S-30 | Python gettext documentation | https://docs.python.org/3/library/gettext.html |
| S-31 | Buku — CLI bookmark manager | https://github.com/jarun/Buku |
| S-32 | Grimoire — SvelteKit bookmark manager | https://github.com/goniszewski/grimoire |
| S-33 | awesome-selfhosted bookmarks | https://github.com/awesome-selfhosted/awesome-selfhosted |
| S-34 | Pinboard — paid minimalist bookmarking | https://pinboard.in |
| S-35 | Diigo — social bookmarking + annotations | https://www.diigo.com |
| S-36 | Memex (WorldBrain) — browser annotations | https://github.com/WorldBrain/Memex |
| S-37 | GoodLinks — macOS/iOS bookmarking | https://goodlinks.app |
| S-38 | defusedxml — safe XML parsing | https://github.com/tiran/defusedxml |
| S-39 | monolith — single-file HTML snapshot | https://github.com/Y2Z/monolith |
| S-40 | trafilatura — web content extraction (v2.0.0) | https://github.com/adbar/trafilatura |
| S-41 | Servas — Laravel/Vue multi-user bookmarks | https://github.com/beromir/Servas |
| S-42 | LinkAce — auto-Wayback + link monitoring | https://github.com/Kovah/LinkAce |
| S-43 | Slash — short-link + bookmark hybrid | https://github.com/yourselfhosted/slash |
| S-44 | Espial — Haskell Pinboard clone | https://github.com/jonschoning/espial |
| S-47 | awesome-selfhosted bookmarks category | https://awesome-selfhosted.net/tags/bookmarks-and-link-sharing.html |
| S-48 | Self-hosted bookmark comparison (alexn.org) | https://alexn.org/blog/2025/02/14/self-hosted-bookmarks-manager/ |
| S-49 | Karakeep review (ReviewNexa) | https://reviewnexa.com/karakeep-review/ |
| S-50 | openalternative.co bookmark managers | https://openalternative.co/categories/bookmark-managers/self-hosted |
| S-51 | Pillow CVEs 2026 (25990, 40192, 42308) | https://www.cvedetails.com/product/27460/Python-Pillow.html |
| S-52 | FastMCP 3.4.0 changelog | https://gofastmcp.com/updates |
| S-53 | MCP 2026 roadmap | https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/ |
| S-54 | LanceDB 0.33.0 releases | https://github.com/lancedb/lancedb/releases |
| S-55 | Nomic Embed v2 benchmarks | https://mixpeek.com/curated-lists/best-embedding-models |
| S-56 | Nuitka vs PyInstaller 2026 | https://ahmedsyntax.com/2026-comparison-pyinstaller-vs-cx-freeze-vs-nui/ |
| S-57 | tksheet 7.6.0 on PyPI | https://pypi.org/project/tksheet/ |
| S-58 | sv-ttk 2.6.1 on PyPI | https://pypi.org/project/sv-ttk/ |
| S-59 | MCP 2026-07-28 release candidate | https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/ |
| S-60 | Raindrop.io MCP server (official) | https://developer.raindrop.io/mcp/mcp |
| S-61 | HN: How Do You Bookmark? (Jan 2025) | https://news.ycombinator.com/item?id=42648006 |
| S-62 | TechCrunch: Pocket shutdown alternatives | https://techcrunch.com/2025/05/27/read-it-later-app-pocket-is-shutting-down/ |
| S-63 | WCAG 2.2 ISO/IEC 40500:2025 | https://www.w3.org/TR/WCAG22/ |
| S-64 | TabMark: AI Bookmark Managers survey | https://tabmark.dev/blog/posts/ai-bookmark-managers/ |
| S-65 | Markwise — chat-with-bookmarks app | https://markwise.app/ |
| S-66 | Chinmay Panda: 2026 bookmark comparison | https://chinmaypanda.com/linkwarden-vs-slash-vs-karakeep-vs-linkding/ |
| S-67 | MDN: MV3 native messaging | https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging |
| S-68 | Lokalise: Python i18n guide | https://lokalise.com/blog/beginners-guide-to-python-i18n/ |
| S-69 | Linkwarden browser extension docs | https://docs.linkwarden.app/getting-started/browser-extension |
| S-70 | Karakeep apps and extensions | https://karakeep.app/apps |
| S-71 | tksheet: development ceased except bug fixes | https://deepwiki.com/ragardner/tksheet |
| S-72 | sv-ttk 2.6.1 releases | https://github.com/rdbende/Sun-Valley-ttk-theme/releases |
| S-73 | FastMCP updates page | https://gofastmcp.com/updates |
| S-74 | Karakeep MCP server docs | https://docs.karakeep.app/integrations/mcp/ |
| S-75 | CVE-2026-39892: cryptography buffer overflow (≥46.0.7) | https://www.sentinelone.com/vulnerability-database/cve-2026-39892/ |
| S-76 | CVE-2026-34073: cryptography cert validation bypass (≥46.0.6) | https://www.sentinelone.com/vulnerability-database/cve-2026-34073/ |
| S-77 | Bookmarkjar — AI bookmark manager (commercial) | https://bookmarkjar.com/ |
| S-78 | Burn 451 — AI bookmark with 22-tool MCP + triage | https://www.burn451.cloud/ |
| S-79 | MCP 2026-07-28 RC: stateless protocol, OAuth, caching | https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/ |
| S-80 | MCP spec breaking changes migration guide | https://dev.to/akaranjkar08/mcp-spec-ships-july-28-every-breaking-change-and-how-to-migrate-4co8 |
| S-81 | FastMCP 3.4.0: fastmcp-remote, OAuth, OTEL | https://pypi.org/project/fastmcp/ |
| S-82 | Raindrop.io Stella AI assistant | https://help.raindrop.io/stella |
| S-83 | Nomic Embed v2 — 137M, CPU-first, Matryoshka | https://pecollective.com/tools/best-embedding-models/ |
| S-84 | Linkwarden 2.14 — reader view, highlights, annotations | https://github.com/linkwarden/linkwarden/releases |
| S-85 | Wallabag 2.6.14 — latest stable, iOS app transition | https://github.com/wallabag/wallabag/releases |
| S-86 | Arc Browser shutdown (May 2025) — arc-export community tools | https://github.com/nicehash/ArcEscape |
| S-87 | Nuitka 4.0/4.1: 1500% compile speedup, Tkinter plugin | https://nuitka.net/posts/nuitka-release-40.html |
| S-88 | tufup 0.10.0 on PyPI | https://pypi.org/project/tufup/ |
| S-89 | Bookmark Lens — local-first MCP bookmark manager on LanceDB | https://github.com/cornelcroi/bookmark-lens |
| S-90 | bookmark-manager-mcp (infinitepi-io) | https://github.com/infinitepi-io/bookmark-manager-mcp |
| S-91 | HN: MCP-connected bookmark manager | https://news.ycombinator.com/item?id=47384765 |
| S-92 | Best AI Bookmark Manager 2026 (Burn 451 blog) | https://www.burn451.cloud/blog/best-ai-bookmark-manager-2026 |
| S-93 | Bookmarkjar review (Tooliverse) | https://tooliverse.ai/tools/bookmarkjar |
| S-94 | ArchiveBox 0.7.4 (May 2026) | https://github.com/ArchiveBox/ArchiveBox/releases |
| S-95 | LanceDB 0.33.0: streaming, IVF_HNSW_FLAT, session cache | https://docs.lancedb.com/changelog/changelog |
| S-96 | Trafilatura 2.0.0 documentation | https://trafilatura.readthedocs.io/ |
| S-97 | Universal Bookmark Manager (MV3 + native messaging) | https://github.com/lazyengineer-eth/universal-bookmark-manager |
| S-98 | Best Bookmark Managers 2026 (bookmarker.cc) | https://bookmarker.cc/blog/best-bookmark-managers-2026 |
| S-99 | MCP ecosystem: 97M+ monthly SDK downloads, 81K+ stars | https://en.wikipedia.org/wiki/Model_Context_Protocol |
| S-100 | Faved — local-first bookmark manager (1.1K stars) | https://github.com/denho/faved |
| S-101 | LazyCat Bookmark Cleaner — AI Chrome extension (1.8K stars) | https://github.com/Alanrk/LazyCat-Bookmark-Cleaner |
| S-102 | Eclaire — local-first AI PKM (864 stars) | https://github.com/eclaire-labs/eclaire |
| S-103 | Floccus — cross-browser bookmark sync via XBEL/WebDAV | https://github.com/floccusaddon/floccus |
| S-104 | Linkwarden 2.14 — reader view with highlights + annotations | https://linkwarden.app/blog/releases/2.11 |
| S-105 | Karakeep v0.32 — SingleFile in-extension + Safari + skills | https://github.com/karakeep-app/karakeep/releases |
| S-106 | Chrome Prompt API (Gemini Nano) — stable in Chrome 138+ extensions | https://developer.chrome.com/docs/ai/prompt-api |
| S-107 | CVE-2026-41066: lxml XXE injection in iterparse() | https://security.snyk.io/package/pip/lxml |
| S-108 | fastembed 0.8.0 — auto-CUDA, Python 3.14, ColModernVBERT | https://pypi.org/project/fastembed/ |
| S-109 | model2vec 0.8.2 — int8 quantization, potion-retrieval-32M | https://github.com/MinishLab/model2vec |
| S-110 | Zotero browser connector architecture (translator pattern) | https://github.com/zotero/zotero-connectors |
| S-111 | Perplexica/Vane — citation architecture (inline [1][2] badges) | https://github.com/ItzCrazyKns/Perplexica |
| S-112 | AnythingLLM — MCP host, workspaces as tools | https://github.com/Mintplex-Labs/anything-llm |
| S-113 | GoSuki — extension-free cross-browser bookmark monitoring | https://github.com/blob42/gosuki |
| S-114 | HN: "Tab Hoarding Journey to Sanity" — ADHD/visibility needs | https://hn.matthewblode.com/item/46529797 |
| S-115 | kottke.org: bookmark manager recommendations (Oct 2025) | https://kottke.org/25/10/can-you-recommend-a-good-bookmark-manager |
| S-116 | Mozilla Connect: AI tagging/categorizing request for Firefox | https://connect.mozilla.org/t5/ideas/automatic-tagging-categorizing-and-searching-of-bookmarks-using/idi-p/45605 |
| S-117 | Bookmark manager software market ~$450M (2024), $1.2B by 2033 | https://www.cognitivemarketresearch.com/bookmark-manager-software-market-report |
| S-118 | TabMark: AI saves 30-60 min/week on organization | https://tabmark.dev/blog/ai-bookmark-managers/ |
| S-119 | shom.dev: Omnivore→Karakeep→Wallabag→Readeck migration | https://shom.dev/posts/20250629_bookmarking-i-mean-omnivoring-no-hoarding-no-bagging-dot-dot-dot-wait-decking/ |
| S-120 | Betula — federated bookmark manager with ActivityPub | https://codeberg.org/bouncepaw/betula |
