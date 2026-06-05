# Bookmark Organizer Pro — Roadmap

Single source of truth for all planned work. Consolidated from `ROADMAP.md` + `RESEARCH_FEATURE_PLAN_2026-06-05.md` on 2026-06-05.
Completed items move to `COMPLETED.md` on each release.

Python/Tkinter bookmark manager with 4,224 categorization patterns, 5 AI providers, MCP server, local semantic search (lancedb + fastembed), hybrid RRF, single-file HTML snapshots, citation-aware AI summaries, RAG chat, encrypted DB, dead-link scanner.

---

## P0 — Must-fix (blocks core functionality)

- [x] **BOP-001** Fix AIBatchProcessor `.settings` / `categorize_bookmark` crashes — use `get_batch_size()`/`get_rate_limit()` + `client.complete()` | `services/ai_tools.py`
- [x] **BOP-002** Fix chunk overlap infinite-loop — `start = end - overlap` + end-backward guard | `services/embeddings.py`
- [x] **BOP-003** Type all 15 MCP tool schemas (proper JSON Schema per tool) | `mcp_server.py`
- [x] **BOP-004** PyInstaller spec: add v6.0 hidden imports (all services/* + optional libs) | `packaging/bookmark_organizer.spec`
- [x] **BOP-005** CI: add `gh release create` step before matrix upload | `.github/workflows/build.yml`

## P1 — High impact (safety, UX, reliability)

- [x] **BOP-011** Atomic writes for VectorStore and DeadLinkScanner | `services/vector_store.py`, `services/dead_link_scanner.py`
- [x] **BOP-012** Log rotation (RotatingFileHandler 5MB/3 backups) + stderr fallback | `logging_config.py`
- [x] **BOP-013** Update AICostTracker pricing to mid-2026 models | `services/ai_tools.py`
- [x] **BOP-017** Use defusedxml for RSS feed parsing (XML bomb protection) | `services/rss_feeds.py`
- [x] **BOP-018** Escape URL in snapshot banner (HTML injection) | `services/snapshot.py`
- [x] **BOP-006** Move AI network calls to background threads | `app_mixins/ai_enrichment.py`, `app_mixins/ai_titles.py`
- [x] **BOP-007** Move link checking to background thread | `app_mixins/tools.py`
- [x] **BOP-014** Use `client.complete()` in AI enrichment/titles instead of provider switch | `app_mixins/ai_enrichment.py`, `app_mixins/ai_titles.py`
- [x] **BOP-020** Add pyproject.toml `[project]` table with metadata, deps, entry points | `pyproject.toml`
- [x] **BOP-008** Per-domain rate limiting for LinkChecker (1s/domain, proper UA) | `link_checker.py`
- [x] **BOP-009** Fix `batch_refresh_metadata` thread safety (collect-then-apply) | `managers/bookmarks.py`
- [x] **BOP-015** API server auth token + CORS deny | `services/api.py`
- [x] **BOP-016** Skip analytics rebuild when stats unchanged | `app_mixins/dashboard.py`
- [x] **BOP-010** Fix dead-link scanner thread safety | `services/dead_link_scanner.py`
- [ ] **BOP-019** List virtualization (tksheet or canvas-based) | `app_mixins/bookmarks.py`

## P2 — Medium impact (competitive parity, quality of life)

- [ ] **BOP-021** Browser extension (MV3) with one-click save + offline tag suggestions
- [ ] **BOP-022** Web client (FastAPI + HTMX) with PWA
- [ ] **BOP-023** Smart Collections with auto-matching rules (net-new)
- [x] **BOP-024** Duplicate-at-save-time detection — returns existing bookmark | `managers/bookmarks.py`, `mcp_server.py`
- [ ] **BOP-025** Headless Chromium snapshot fallback via playwright
- [ ] **BOP-026** Cross-encoder re-rank after RRF
- [ ] **BOP-027** Reader view with highlight and annotation (net-new)
- [ ] **BOP-028** EPUB export of collections
- [ ] **BOP-029** YouTube transcript capture and indexing via yt-dlp
- [x] **BOP-030** Sanitize user data in LLM prompts | `utils/safe.py`, `services/ai_tools.py`
- [x] **BOP-031** URL normalization HTTP->HTTPS is correct for dedup — clarified | `utils/url.py`
- [x] **BOP-032** Pre-restore backup in StorageManager | `core/storage_manager.py`
- [x] **BOP-033** Thread safety for TagManager | `managers/tags.py`
- [x] **BOP-034** Fix `save_bookmarks` lock race — hold lock through write | `managers/bookmarks.py`
- [ ] **BOP-035** Deduplicate cross-category patterns | `core/default_categories.py`
- [ ] **BOP-036** Fix overly broad plain patterns | `core/default_categories.py`, `core/pattern_engine.py`
- [x] **BOP-037** Intra-file dedup in importers | `importers.py`
- [ ] **BOP-038** Fix GridView scroll stealing | `ui/widget_grid.py`, `ui/components.py`
- [ ] **BOP-039** Fix command palette FocusOut | `ui/shell_widgets.py`
- [ ] **BOP-040** Undo for bulk category moves and duplicate removal

## P3 — Nice-to-have (polish, future positioning)

- [ ] **BOP-041** Obsidian vault sync via MCP export tool
- [ ] **BOP-042** Nuitka compilation for distribution
- [ ] **BOP-043** tufup auto-update framework
- [ ] **BOP-044** sv-ttk theme migration
- [ ] **BOP-045** Behavioral triage: inbox with aging indicators
- [ ] **BOP-046** Graph view of bookmarks
- [ ] **BOP-047** ATOM/JSON Feed output per collection
- [ ] **BOP-048** Matter/Omnivore/Zotero importers
- [ ] **BOP-049** MCP auth token with per-tool scopes
- [ ] **BOP-050** MCP streaming for `chat_with_collection`
- [ ] **BOP-051** Remove ~1,300 lines dead code (GridView, unused widgets, broken tray)
- [ ] **BOP-052** Fix copy-pasted model docstrings on widget classes
- [x] **BOP-053** Move constants.py directory creation to `ensure_directories()` | `constants.py`, `launcher.py`, `cli.py`, `mcp_server.py`
- [x] **BOP-054** Validate RAG citation IDs, strip hallucinated tokens | `services/rag_chat.py`
- [ ] **BOP-055** Extract health score to single shared utility
- [ ] **BOP-056** Use keyring/DPAPI for API key storage on Windows
- [x] **BOP-057** Add Ollama URL SSRF check (restrict to localhost) | `ai.py`
- [x] **BOP-058** Remove `ensure_package` runtime pip install — clear install instruction | `ai.py`
- [x] **BOP-059** Make thum.io screenshot API opt-in (settings flag) | `services/web_tools.py`
- [ ] **BOP-060** Keyboard accessibility for treeview

## Quick Wins (done this pass)

- [x] Chunk overlap bug (`embeddings.py:182`)
- [x] Tag linter no-op line (`tag_linter.py:92`)
- [x] Dead `_extract_text` conditional (`web_tools.py:444`)
- [x] Snapshot URL escaping (`snapshot.py:182`)
- [x] Log rotation + stderr fallback (`logging_config.py`)
- [x] `remove_tag` case sensitivity (`models/bookmark.py`)
- [x] `get_stale_bookmarks` ignores `days` param (`managers/bookmarks.py`)
- [x] Search empty query returns `[]` (`search.py`)
- [x] Date filter bad timestamps → `return False` (`search.py`)
- [x] Pre-restore backup (`storage_manager.py`)
- [x] `decrypt_file` dst validation (`encryption.py`)
- [x] AICostTracker pricing update (`ai_tools.py`)
- [x] defusedxml for RSS (`rss_feeds.py`)

## Competitive Research

See `RESEARCH_FEATURE_PLAN_2026-06-05.md` for the full competitive analysis (Linkwarden, Karakeep, Raindrop, Readeck, ArchiveBox, etc.), feature inventory, architecture audit, and detailed implementation notes.
