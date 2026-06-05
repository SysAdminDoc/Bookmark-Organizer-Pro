# Bookmark Organizer Pro — Roadmap

> **Version:** 3.0 · **Date:** 2026-06-05 · **Covers:** v6.1.0 → v7.x  
> **Single source of truth** for all planned work.  
> Supersedes prior `ROADMAP.md` (v2) and `RESEARCH_FEATURE_PLAN_2026-06-05.md`.

---

## How to Read This

| Symbol | Meaning |
|--------|---------|
| ✅ | Done (shipped in v6.1.0 or earlier) |
| 🔲 | Open — implementation not started |
| 🚧 | In progress or partially shipped |
| S/M/L/XL | Effort estimate (days: 0.5 / 1-2 / 3-5 / 1-2 weeks) |

**Tiers:** Now (v6.2) → Next (v7.0) → Later (v7.x+) → Under Consideration → Rejected

**Every item is traceable** to a source in the [Appendix](#appendix-sources). Items without sources are rejected.

---

## State of the Project (v6.1.0)

Bookmark Organizer Pro is a **local-first, privacy-centric** Python/Tkinter bookmark manager. At v6.1.0 it ships:

- **AI:** 5 providers (OpenAI, Anthropic, Gemini, Groq, Ollama), auto-categorization with 4,224 patterns, tag suggestions, title improvement, citation-aware summaries, conversational RAG, NL-to-structured-query
- **Search:** Full-text boolean + semantic vector (LanceDB + FastEmbed) + hybrid RRF
- **MCP server:** 15 typed tools — one of only two OSS bookmark managers with MCP (Raindrop.io added one in 2026 — [S-60])
- **Preservation:** Single-file HTML snapshots (monolith/single-file/BS4), dead-link scanner, Wayback Machine
- **Security:** AES-256-GCM encrypted DB, SSRF guards, prompt sanitization, API auth tokens
- **Import/Export:** 13 importers, 7 exporters (HTML/JSON/CSV/OPML/XBEL/Markdown/ZIP)
- **UI:** 10+ themes, command palette, toast notifications, zoom, high-DPI

**What v6.1.0 fixed (35 items):** AI batch processor crashes, chunk overlap infinite-loop, untyped MCP schemas, PyInstaller missing hidden imports, CI release flow, thread-safety across 5 services, main-thread blocking, per-domain rate limiting, atomic writes, log rotation, defusedxml, API auth, prompt sanitization, and 13 quick wins. See [CHANGELOG.md](CHANGELOG.md).

**Hard constraints:**
- MIT license
- Python ≥ 3.10, Tkinter GUI (no Electron/Tauri rewrite)
- Local-first: no mandatory server, no cloud dependency, no Docker requirement
- Optional deps must degrade gracefully — core works with zero extras installed
- Windows-primary, cross-platform (macOS, Linux)
- User data sovereignty: AI assists, user decides; never auto-delete or auto-merge

---

## Theme 1 — Platform Reach

*The single biggest limitation: BOP has no browser extension, no web client, no mobile access.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-01 | **Browser extension (MV3)** — one-click save popup with offline category/tag suggestions from the 4,224-pattern engine, native messaging to localhost API. Chrome + Firefox. | Now | L | [S-1][S-3][S-5][S-7][S-10] |
| 🔲 R-02 | **Web client (FastAPI + HTMX)** — read/search/add from any device. PWA manifest for mobile install. Read-only by default, auth-gated mutations. Shares JSON storage via WAL-mode SQLite migration (see R-30). | Next | XL | [S-3][S-5][S-6][S-8][S-12] |
| 🔲 R-03 | **Mobile PWA share-intent** — Android "Share to BOP" target via the web client, auto-categorize on receipt. | Next | M | [S-8][S-12] |
| ✅ R-04 | **Bookmarklet fallback** — `scripts/generate_bookmarklet.py` generates a JS bookmark with auth token. Sends URL+title+selection to localhost API with toast feedback. | Now | S | [S-6][S-10] |

**Justification:** Every major competitor ships a browser extension ([S-3] Linkwarden, [S-5] Karakeep, [S-7] Linkding, [S-8] Wallabag, [S-10] Raindrop). "No extension" is the #1 complaint in r/selfhosted bookmark threads ([S-20]). The bookmarklet is a low-effort interim solution while the extension matures.

---

## Theme 2 — AI & Search Quality

*BOP's MCP server + RAG + semantic search combo is unique. Protect and extend the lead.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-05 | **FastMCP migration** — auto-schema from type hints with FastMCP when available, raw mcp SDK fallback. 19 tools registered in both paths. | Now | M | [S-14][S-15] |
| ✅ R-06 | **MCP tools: `create_flow`, `append_to_flow`, `export_zip`, `list_snapshots`** — 4 new typed tools added (19 total). | Now | M | [S-14] |
| 🔲 R-07 | **Cross-encoder re-rank** after RRF — optional `bge-reranker-base` step for ambiguous queries. Gated on installed package. | Next | M | [S-16][S-17] |
| 🔲 R-08 | **Chunk-level provenance in RAG** — cite specific chunk offsets, not just bookmark ID. UI deep-links to the supporting span. | Next | M | [S-1] |
| ✅ R-09 | **Time-weighted recall** — exponential decay factor with configurable half-life in hybrid search. `time_weight` param (0-1). | Next | S | [S-1] |
| 🔲 R-10 | **Collections as retrieval scopes** — pin RAG chat to a collection or tag from the sidebar. | Next | M | [S-1][S-10] |
| 🔲 R-11 | **Answer caching** — `(query_hash, scope_hash)` cache for repeat questions. | Later | S | [S-1] |
| 🔲 R-12 | **YouTube transcript capture** — detect YouTube URLs at save time, fetch transcript via `yt-dlp --write-auto-sub --skip-download`, index as extracted text for semantic search + RAG. | Next | M | [S-6][S-18] |
| ✅ R-13 | **Smart Collections** — `SmartCollectionManager` with tag/domain/date/keyword/content-type filters. CRUD + evaluate API. | Next | M | [S-10][S-19] |
| 🔲 R-14 | **MCP auth token with per-tool scopes** — read-only vs. read-write tokens for multi-client environments. | Later | M | [S-14] |
| 🔲 R-15 | **MCP streaming** for `chat_with_collection` — stream RAG responses token-by-token. | Later | M | [S-14] |

---

## Theme 3 — UI & Performance

*Tkinter is the stack. Modernize within it, don't fight it.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-16 | **List virtualization via tksheet** — replace Treeview with tksheet for virtual scrolling. Handles millions of rows. Pure Python. | Now | L | [S-22][S-23] |
| 🔲 R-17 | **Tree view alongside list view** — hierarchical category tree for deeply nested collections. | Next | M | [S-3][S-5] |
| 🔲 R-18 | **sv-ttk theme integration** — Windows 11 Sun Valley look without CustomTkinter dependency. Lightweight, actively maintained. | Next | M | [S-24] |
| ✅ R-19 | **Fix command palette FocusOut** — clicking a palette item closes it before the click registers. `after(150)` delay + child-focus check. | Now | S | [S-1] |
| ✅ R-20 | **Fix GridView scroll stealing** — `bind_all('<MouseWheel>')` replaced with widget-scoped binding. | Now | S | [S-1] |
| 🔲 R-21 | **Reader view with highlight/annotation** — open extracted text in a reader pane. 4-color highlights, per-highlight notes. Export to Markdown. | Later | L | [S-3][S-10][S-11] |
| 🔲 R-22 | **Graph view** — bookmarks as nodes, tags as edges, force-directed layout. | Later | L | [S-4] |

---

## Theme 4 — Preservation & Content

*Snapshots and content extraction are a differentiator vs. minimal tools like Linkding/Buku.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-23 | **Headless Chromium snapshot fallback** — playwright backend added as 3rd in chain (monolith → singlefile → playwright → python). | Now | M | [S-1][S-3] |
| 🔲 R-24 | **Scheduled auto-snapshot** — user picks bookmarks for periodic re-capture to catch silent edits. | Next | M | [S-1] |
| ✅ R-25 | **EPUB export of collections** — EPUB 3.0 via manual ZIP. Each bookmark = chapter. No external deps. | Next | M | [S-6][S-18] |
| 🔲 R-26 | **OPDS catalog** — serve collections to e-reader apps (Readeck-style). | Later | M | [S-6] |

---

## Theme 5 — Import / Export / Interop

*Pocket and Omnivore are dead ([S-25][S-26]). BOP should be the landing pad.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-27 | **Zotero RDF import/export** — bridge to academic reference managers. | Next | M | [S-1] |
| 🔲 R-28 | **Matter export format** — import from Readwise-adjacent service. | Later | S | [S-1] |
| 🔲 R-29 | **ATOM / JSON Feed output per collection** — share collections as RSS. | Later | S | [S-1] |
| ✅ R-30 | **Obsidian vault export via CLI + MCP** — `services/obsidian_export.py` + MCP `export_to_obsidian` tool (20 total). Tag/category/date filters. | Next | M | [S-1][S-11] |

---

## Theme 6 — Data Architecture

*JSON file storage works for thousands of bookmarks but won't scale to 100K+.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-31 | **SQLite migration (optional)** — WAL mode unlocks concurrent access for web client. JSON remains default for backwards compat. Migration tool converts JSON → SQLite on opt-in. | Next | XL | [S-7][S-9] |
| ✅ R-32 | **Per-backup integrity hash** — SHA-256 checksum file alongside each backup. Verify on restore. | Now | S | [S-1] |
| ✅ R-33 | **Deduplicate cross-category patterns** — removed 8 within-category + 29 cross-category duplicates. | Now | M | [S-1] |
| ✅ R-34 | **Fix overly broad plain patterns** — converted 25+ plain patterns to typed `domain:`/`keyword:`/`regex:`. | Now | M | [S-1] |

---

## Theme 7 — Security & Privacy

*Local-first is a privacy claim. Back it up.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-35 | **API key storage via keyring/DPAPI** — use OS credential store instead of plaintext JSON on Windows. | Next | M | [S-1] |
| ✅ R-36 | **ReDoS timeout on pattern engine regex** — `signal.alarm` guard on Unix, catch-all on Windows. | Now | S | [S-1] |
| ✅ R-36b | **Upgrade Pillow to ≥12.2.0** — CVE-2026-25990, CVE-2026-40192, CVE-2026-42308 fixed. | Now | S | [S-51] |
| 🔲 R-37 | **SSRF allow-list for snapshot/ingest** — beyond current private-IP block. Configurable regex whitelist. | Next | M | [S-1] |
| 🔲 R-38 | **Auto-rotate encrypted-DB passphrase** — with audit log entry. | Later | M | [S-1] |
| ✅ R-39 | **Telemetry-free mode banner** — first-run privacy notice in launcher. | Now | S | [S-1] |

---

## Theme 8 — Distribution & Packaging

*PyInstaller works but has AV false-positive problems. No auto-update.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-40 | **Nuitka compilation** — Python-to-C, fewer AV false positives, 2-4x faster startup. Tkinter plugin available. | Next | L | [S-27] |
| 🔲 R-41 | **tufup auto-update** — TUF-based binary diff patches. Works with PyInstaller or Nuitka. | Later | M | [S-28] |
| ✅ R-42 | **Python version matrix in CI** — test job on 3.10, 3.11, 3.12, 3.13 before build. | Now | S | [S-1] |

---

## Theme 9 — Testing & Quality

*142 test methods in 1 file. Zero coverage of v6 service modules.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| ✅ R-43 | **Service layer test suite** — 26 tests across 8 services (embeddings, encryption, tag_linter, flows, digest, rss_feeds, zip_export, read_later). 188 total tests pass. | Now | L | [S-1] |
| ✅ R-44 | **MCP server integration tests** — 20 tests covering all 19 tools, schema validation, dedup detection, flows CRUD. | Now | M | [S-1] |
| 🔲 R-45 | **CLI smoke test suite** — automated `bop <command>` tests for all 30+ subcommands in CI. | Next | M | [S-1] |
| ✅ R-46 | **Remove ~1,409 lines dead code** — GridView, BookmarkListView, MiniAnalyticsDashboard, SystemTray, BookmarkCard, CategoryDragDropManager, ViewMode.GRID, dead assignment. 9 files cleaned. | Now | S | [S-1] |
| ✅ R-47 | **Fix copy-pasted model docstrings** — replaced in cli.py, api.py, widget_bookmark_editor.py, widget_lists.py, workflow_detail_panel.py. | Now | S | [S-1] |

---

## Theme 10 — Accessibility & i18n

*Desktop apps are not exempt from accessibility. i18n is a multiplier for OSS adoption.*

| # | Item | Tier | Effort | Source |
|---|------|------|--------|--------|
| 🔲 R-48 | **Keyboard accessibility** — tab order across treeview/sidebar/search/toolbar, column sort via keyboard, screen reader labels on major sections. WCAG 2.2 focus-appearance criteria (2.4.11, 2.4.13). Min 24×24px click targets (2.5.8). | Next | L | [S-29][S-63] |
| ✅ R-49 | **High-contrast theme** — WCAG AA dark theme with yellow accents, white text on black. | Next | S | [S-29][S-63] |
| 🔲 R-50 | **gettext i18n scaffolding** — extract all user-facing strings, `.po` file structure, `CONTRIBUTING.md` section for translators. No translations required yet — just the infrastructure. | Later | M | [S-30][S-68] |

---

## Completed (v6.1.0)

All v6.1.0 fixes are recorded in [CHANGELOG.md](CHANGELOG.md). Key items that were previously on this roadmap:

| ID | Item | Status |
|----|------|--------|
| BOP-001 | AI batch processor crashes | ✅ v6.1.0 |
| BOP-002 | Chunk overlap infinite-loop | ✅ v6.1.0 |
| BOP-003 | Typed MCP tool schemas | ✅ v6.1.0 |
| BOP-004 | PyInstaller v6 hidden imports | ✅ v6.1.0 |
| BOP-005 | CI release creation step | ✅ v6.1.0 |
| BOP-006 | AI calls off main thread | ✅ v6.1.0 |
| BOP-007 | Link check off main thread | ✅ v6.1.0 |
| BOP-008 | Per-domain rate limiting | ✅ v6.1.0 |
| BOP-009 | batch_refresh_metadata thread safety | ✅ v6.1.0 |
| BOP-010 | Dead-link scanner thread safety | ✅ v6.1.0 |
| BOP-011 | Atomic writes (VectorStore, DeadLinkScanner) | ✅ v6.1.0 |
| BOP-012 | Log rotation | ✅ v6.1.0 |
| BOP-013 | AI cost tracker pricing update | ✅ v6.1.0 |
| BOP-014 | client.complete() abstraction | ✅ v6.1.0 |
| BOP-015 | API auth + CORS | ✅ v6.1.0 |
| BOP-016 | Analytics skip-unchanged | ✅ v6.1.0 |
| BOP-017 | defusedxml for RSS | ✅ v6.1.0 |
| BOP-018 | Snapshot URL escaping | ✅ v6.1.0 |
| BOP-020 | pyproject.toml | ✅ v6.1.0 |
| BOP-024 | Duplicate-at-save-time detection | ✅ v6.1.0 |
| BOP-030 | Prompt sanitization | ✅ v6.1.0 |
| BOP-032 | Pre-restore backup | ✅ v6.1.0 |
| BOP-033 | TagManager thread safety | ✅ v6.1.0 |
| BOP-034 | save_bookmarks lock race | ✅ v6.1.0 |
| BOP-037 | Importer intra-file dedup | ✅ v6.1.0 |
| BOP-053 | ensure_directories() refactor | ✅ v6.1.0 |
| BOP-054 | RAG citation validation | ✅ v6.1.0 |
| BOP-057 | Ollama SSRF guard | ✅ v6.1.0 |
| BOP-058 | Remove runtime pip install | ✅ v6.1.0 |
| BOP-059 | thum.io opt-in | ✅ v6.1.0 |
| + 5 more | Quick wins (tag case, stale days, search empty, date filter, decrypt validation) | ✅ v6.1.0 |

---

## Rejected (with reasoning)

| Idea | Source | Reason |
|------|--------|--------|
| Multi-user / team features | [S-3][S-7] | Contradicts local-first single-user design. Linkwarden and Linkding cover teams. |
| Docker as primary deployment | [S-5][S-3] | No-Docker is a differentiator. Docker *support* is fine but never required. |
| Meilisearch/Elasticsearch sidecar | [S-5] | Built-in FTS + LanceDB is a simplicity advantage. No external search infra. |
| Cloud-hosted SaaS | — | Premature. Stabilize first, revisit post-v7. |
| Native mobile apps (iOS/Android) | — | PWA via web client covers 90%. Native is too expensive for a single maintainer. |
| Full language rewrite (Rust/Go/TS) | — | Python ecosystem (fastembed, lancedb, mcp, trafilatura) is the stack. Nuitka for perf. |
| AI-only organization (no manual) | [S-19] | "AI assists, user decides" is core philosophy. Never remove manual control. |
| Browser-history import (full) | — | Privacy risk too high. One-off migration aid only if explicitly requested. |
| CustomTkinter migration | [S-24] | Stagnating (no releases in 12+ months, maintainer absent). sv-ttk is the alternative. |

---

## Under Consideration

These ideas surfaced in research but need more validation before committing:

| Idea | Source | Open Question |
|------|--------|---------------|
| **Plugin API via `entry_points`** — community importers without forking | [S-1] | Is there demand? No community contributors yet. Ship when there's a second contributor. |
| **WARC dual-archive** alongside HTML snapshots | [S-4] | Storage cost doubles. Only if a user requests archival-grade preservation. |
| **Public-share static export** — single HTML per collection, no server | [S-1] | Nice but niche. Build only if the web client ships first. |
| **Auto-highlight extraction** — local LLM finds N highlights per article | [S-1][S-11] | Cool but depends on reader view (R-21) landing first. |
| **Behavioral triage inbox** — amber 7d, red 30d aging indicators | [S-19] | Could cause data anxiety (Burn 451's biggest complaint). Needs UX research. |

---

## Appendix: Sources

| ID | Source | URL / Reference |
|----|--------|-----------------|
| S-1 | BOP internal audit (8-agent pass, 2026-06-05) | `RESEARCH_FEATURE_PLAN_2026-06-05.md` (local) |
| S-2 | BOP v6.1.0 CHANGELOG | `CHANGELOG.md` (local) |
| S-3 | Linkwarden — self-hosted bookmark manager | https://github.com/linkwarden/linkwarden |
| S-4 | ArchiveBox — aggressive multi-format archiver | https://github.com/ArchiveBox/ArchiveBox |
| S-5 | Karakeep (ex-Hoarder) — AI bookmark everything | https://github.com/karakeep-app/karakeep |
| S-6 | Readeck — Go read-it-later with EPUB/OPDS | https://github.com/readeck/readeck |
| S-7 | Linkding — minimalist self-hosted | https://github.com/sissbruecker/linkding |
| S-8 | Wallabag — PHP read-it-later | https://github.com/wallabag/wallabag |
| S-9 | Shiori — Go Pocket alternative | https://github.com/go-shiori/shiori |
| S-10 | Raindrop.io — cloud bookmark SaaS | https://raindrop.io |
| S-11 | Readwise Reader — highlight/annotation SaaS | https://readwise.io/read |
| S-12 | Omnivore (dead Nov 2024) — read-it-later | https://github.com/omnivore-app/omnivore |
| S-13 | Shaarli — minimalist link share | https://github.com/shaarli/Shaarli |
| S-14 | FastMCP — Python MCP framework | https://github.com/jlowin/fastmcp |
| S-15 | MCP specification | https://modelcontextprotocol.io/specification |
| S-16 | LanceDB — embedded vector database | https://github.com/lancedb/lancedb |
| S-17 | FastEmbed — ONNX embedding inference | https://github.com/qdrant/fastembed |
| S-18 | yt-dlp — video metadata/transcript | https://github.com/yt-dlp/yt-dlp |
| S-19 | mymind / Burn 451 — AI-first bookmarking | https://mymind.com / https://burn451.com |
| S-20 | r/selfhosted bookmark threads | https://reddit.com/r/selfhosted (search: bookmark) |
| S-21 | Pocket shutdown (July 2025) | https://support.mozilla.org/en-US/kb/pocket |
| S-22 | tksheet — virtual scrolling for Tkinter | https://github.com/ragardner/tksheet |
| S-23 | Tkinter Treeview performance limits | [S-1] internal audit, `app_mixins/bookmarks.py` |
| S-24 | sv-ttk — Sun Valley theme for ttk | https://github.com/rdbende/Sun-Valley-ttk-theme |
| S-25 | Pocket dead — user migration | https://blog.mozilla.org/en/mozilla/update-on-pocket/ |
| S-26 | Omnivore dead — acquihired by ElevenLabs | https://blog.omnivore.app/p/details-on-omnivore-shutting-down |
| S-27 | Nuitka — Python-to-C compiler | https://nuitka.net |
| S-28 | tufup — TUF-based auto-update | https://github.com/dennisvang/tufup |
| S-29 | WCAG 2.2 quick reference | https://www.w3.org/WAI/WCAG22/quickref/ |
| S-30 | Python gettext documentation | https://docs.python.org/3/library/gettext.html |
| S-31 | Buku — CLI bookmark manager | https://github.com/jarun/Buku |
| S-32 | Grimoire — bookmark manager | https://github.com/goniszewski/grimoire |
| S-33 | awesome-selfhosted bookmarks | https://github.com/awesome-selfhosted/awesome-selfhosted#bookmarks-and-link-sharing |
| S-34 | Pinboard — paid minimalist bookmarking | https://pinboard.in |
| S-35 | Diigo — social bookmarking + annotations | https://www.diigo.com |
| S-36 | Memex (WorldBrain) — browser annotations | https://github.com/WorldBrain/Memex |
| S-37 | GoodLinks — macOS/iOS bookmarking | https://goodlinks.app |
| S-38 | defusedxml — safe XML parsing | https://github.com/tiran/defusedxml |
| S-39 | monolith — single-file HTML snapshot | https://github.com/Y2Z/monolith |
| S-40 | trafilatura — web content extraction | https://github.com/adbar/trafilatura |
| S-41 | Servas — Laravel/Vue multi-user bookmarks | https://github.com/beromir/Servas |
| S-42 | LinkAce — auto-Wayback + link monitoring | https://github.com/Kovah/LinkAce |
| S-43 | Slash — short-link + bookmark hybrid | https://github.com/yourselfhosted/slash |
| S-44 | Espial — Haskell Pinboard clone | https://github.com/jonschoning/espial |
| S-45 | Grimoire — SvelteKit bookmark manager | https://github.com/goniszewski/grimoire |
| S-46 | Buku — CLI-first SQLite bookmarks | https://github.com/jarun/Buku |
| S-47 | awesome-selfhosted bookmarks category | https://awesome-selfhosted.net/tags/bookmarks-and-link-sharing.html |
| S-48 | Self-hosted bookmark comparison (alexn.org) | https://alexn.org/blog/2025/02/14/self-hosted-bookmarks-manager/ |
| S-49 | Karakeep review (ReviewNexa) | https://reviewnexa.com/karakeep-review/ |
| S-50 | openalternative.co bookmark managers | https://openalternative.co/categories/bookmark-managers/self-hosted |
| S-51 | Pillow CVEs 2026 (25990, 40192, 42308) | https://www.cvedetails.com/vulnerability-list/vendor_id-10210/product_id-27460/Python-Pillow.html |
| S-52 | FastMCP 3.4.0 changelog | https://gofastmcp.com/changelog |
| S-53 | MCP 2026 roadmap (2026-07-28 spec) | https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/ |
| S-54 | LanceDB 0.33.0 releases | https://github.com/lancedb/lancedb/releases |
| S-55 | nomic-embed-text benchmarks | https://mixpeek.com/curated-lists/best-embedding-models |
| S-56 | Nuitka vs PyInstaller 2026 | https://ahmedsyntax.com/2026-comparison-pyinstaller-vs-cx-freeze-vs-nui/ |
| S-57 | tksheet 7.6.0 on PyPI | https://pypi.org/project/tksheet/ |
| S-58 | sv-ttk 2.6.1 on PyPI | https://pypi.org/project/sv-ttk/ |
| S-59 | MCP 2026-07-28 release candidate | https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/ |
| S-60 | Raindrop.io MCP server (official) | https://help.raindrop.io/mcp |
| S-61 | HN: How Do You Bookmark? (Jan 2025) | https://news.ycombinator.com/item?id=42648006 |
| S-62 | TechCrunch: Pocket shutdown alternatives | https://techcrunch.com/2025/05/27/read-it-later-app-pocket-is-shutting-down-here-are-the-best-alternatives/ |
| S-63 | WCAG 2.2 ISO/IEC 40500:2025 | https://www.w3.org/TR/WCAG22/ |
| S-64 | TabMark: AI Bookmark Managers survey | https://tabmark.dev/blog/posts/ai-bookmark-managers/ |
| S-65 | Markwise — chat-with-bookmarks app | https://markwise.app/ |
| S-66 | Chinmay Panda: 2026 bookmark manager comparison | https://chinmaypanda.com/linkwarden-vs-slash-vs-karakeep-vs-linkding-for-bookmark-managers-in-2026/ |
| S-67 | MDN: MV3 native messaging | https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging |
| S-68 | Lokalise: Python i18n guide | https://lokalise.com/blog/beginners-guide-to-python-i18n/ |

---

## Now (v6.2) — 19 items

Immediate priority. Ship within the next development cycle.

- 🔲 **R-01** Browser extension (MV3) [L]
- ✅ **R-04** Bookmarklet fallback [S]
- ✅ **R-05** FastMCP migration [M]
- ✅ **R-06** MCP tools: create_flow, append_to_flow, export_zip, list_snapshots [M]
- 🔲 **R-16** List virtualization via tksheet [L]
- ✅ **R-19** Fix command palette FocusOut [S]
- ✅ **R-20** Fix GridView scroll stealing [S]
- ✅ **R-23** Headless Chromium snapshot fallback [M]
- ✅ **R-32** Per-backup integrity hash [S]
- ✅ **R-33** Deduplicate cross-category patterns [M]
- ✅ **R-34** Fix overly broad plain patterns [M]
- ✅ **R-36** ReDoS timeout on pattern engine [S]
- ✅ **R-39** Telemetry-free mode banner [S]
- ✅ **R-42** Python version matrix in CI [S]
- ✅ **R-43** Service layer test suite [L]
- ✅ **R-44** MCP server integration tests [M]
- ✅ **R-36b** Upgrade Pillow to ≥12.2.0 (3 CVEs) [S]
- ✅ **R-46** Remove ~1,300 lines dead code [S]
- ✅ **R-47** Fix copy-pasted model docstrings [S]

## Next (v7.0) — 21 items

High-value features and architectural investments.

- 🔲 **R-02** Web client (FastAPI + HTMX + PWA) [XL]
- 🔲 **R-03** Mobile PWA share-intent [M]
- 🔲 **R-07** Cross-encoder re-rank after RRF [M]
- 🔲 **R-08** Chunk-level RAG provenance [M]
- ✅ **R-09** Time-weighted recall [S]
- 🔲 **R-10** Collections as retrieval scopes [M]
- 🔲 **R-12** YouTube transcript capture [M]
- ✅ **R-13** Smart Collections [M]
- 🔲 **R-17** Tree view alongside list [M]
- 🔲 **R-18** sv-ttk theme integration [M]
- 🔲 **R-24** Scheduled auto-snapshot [M]
- ✅ **R-25** EPUB export of collections [M]
- 🔲 **R-27** Zotero RDF import/export [M]
- ✅ **R-30** Obsidian vault export [M]
- 🔲 **R-31** SQLite migration (optional) [XL]
- 🔲 **R-35** API key storage via keyring [M]
- 🔲 **R-37** SSRF allow-list for snapshot/ingest [M]
- 🔲 **R-40** Nuitka compilation [L]
- 🔲 **R-45** CLI smoke test suite [M]
- 🔲 **R-48** Keyboard accessibility [L]
- ✅ **R-49** High-contrast theme [S]

## Later (v7.x+) — 11 items

Valuable but not urgent. Build when the foundation supports it.

- 🔲 **R-11** Answer caching [S]
- 🔲 **R-14** MCP per-tool scoped auth [M]
- 🔲 **R-15** MCP streaming for RAG chat [M]
- 🔲 **R-21** Reader view with highlights [L]
- 🔲 **R-22** Graph view [L]
- 🔲 **R-26** OPDS catalog [M]
- 🔲 **R-28** Matter export format [S]
- 🔲 **R-29** ATOM/JSON Feed output [S]
- 🔲 **R-38** Auto-rotate encrypted-DB passphrase [M]
- 🔲 **R-41** tufup auto-update [M]
- 🔲 **R-50** gettext i18n scaffolding [M]
