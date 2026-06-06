# Changelog

All notable changes to Bookmark-Organizer-Pro will be documented in this file.

## [v6.5.1] - 2026-06-05

UI polish, importers, test coverage, and developer experience release. 11 roadmap items shipped.

### Added — Import/Export (R-75, R-76, R-68)

- **Wallabag JSON importer** — `WallabagJSONImporter` parses Wallabag exports,
  maps `is_starred` to pinned, extracts tag objects. CLI: `import-wallabag`.
- **Arc Browser importer** — `ArcBrowserImporter` parses `StorableSidebar.json`
  with recursive folder walk. CLI: `import-arc`.
- **GUI import parity** — 9 service importers (Pocket, Readwise, Pinboard,
  Instapaper, Reddit, Matter, Wallabag, Arc, Zotero) now accessible from the
  Import menu with file choosers.

### Added — AI & Embeddings (R-61)

- **Nomic Embed v2 model support** — `NOMIC_MODEL` constant + `RECOMMENDED_MODELS`
  dict with default/nomic/minilm profiles. CLI: `embed --model=nomic`.

### Added — CLI & DX (R-77)

- **Shell completion scripts** — bash, zsh, and fish completions covering all 41
  subcommands + flow/feed/read-later/embed sub-arguments. In `scripts/completions/`.

### Added — Architecture (R-74)

- **File-change watching** — `BookmarkManager.start_file_watcher()` polls mtime
  every 5s and reloads on external change. Enables MCP + GUI co-existence.

### Improved — UI (R-69, R-70, R-71, R-72)

- **Command palette expanded** from 19 to 35 commands — Toggle Pin, Copy URL,
  Delete, Zoom, Flatten, Clear Categories/Tags, AI Improve Titles, Organize,
  Search Syntax Help, Keyboard Shortcuts, About.
- **Bookmark editor** — added read-later checkbox alongside pinned/archived.
- **DependencyCheckDialog** — all ~40 hardcoded Catppuccin Mocha colors replaced
  with `get_theme()` tokens. Now follows active theme.
- **Escape-to-close** on 4 remaining dialogs: DependencyCheckDialog,
  ThemeSelectorDialog, BulkTagEditorDialog, EmojiPicker.

### Improved — Testing (R-78)

- 16 new test methods across 8 test classes: HybridSearchFallback, NLQueryHeuristic,
  DeadLinkScanner, WallabagImporter, ArcImporter, BatchSave, SnapshotArchiver,
  EmbeddingModels.

## [v6.5.0] - 2026-06-05

Security hardening, MCP expansion, browser extension production, and UI polish.

### Security (R-51, R-52, R-53, R-54, R-55, R-56)

- **Bump `cryptography` to ≥46.0.7** — fixes CVE-2026-39892 (buffer overflow)
  and CVE-2026-34073 (certificate validation bypass).
- **Wire MCP authentication** — MCPTokenManager now enforced in mcp_server.py.
  Open mode when no tokens configured; read-only/read-write scopes otherwise.
- **Fix XXE in OPML/XBEL importers** — defusedxml integrated in importers.py
  and xbel.py. Added to core dependencies.
- **Sanitize LocalArchiver HTML** — strip `<script>` tags and `on*` handlers.
  CSP `script-src 'none'` meta header on all archives.
- **Windows ACL on API token** — icacls restricts api_token.txt to current user
  on Windows (was world-readable).
- **REST API GET auth** — all GET endpoints except `/` now require Bearer token.

### Added — MCP (R-57)

- **6 new MCP write tools** (26 total): `delete_bookmark`, `update_bookmark`,
  `toggle_pin`, `mark_read_later`, `add_tags`, `remove_tags`. Registered in
  both raw MCP and FastMCP server builders.

### Added — Browser Extension (R-01)

- **Extension icons** — 16/32/48/128px PNGs generated from app icon.
- **Context menu** — "Save to BOP" on pages/links, "Save with selection" on
  selected text. Background service worker.
- **Keyboard shortcut** — Ctrl+Shift+B (configurable) opens popup.
- **Category autocomplete** — bundled categories.json (39 categories) populates
  `<datalist>` in popup.
- **Read-later toggle** — checkbox in popup; sends `read_later` in POST payload.
- **Test Connection** — button in Options page validates port + token against
  live API, shows version or specific error.
- **Improved error messages** — popup now shows actionable guidance for 401
  (invalid token), network errors (start API), etc.

### Added — UI (R-62, R-72)

- **Help menu** — Search Syntax (renders all 15+ filter docs), Keyboard
  Shortcuts reference, and About dialog. All dialogs support Escape-to-close.

### Fixed — UI (R-63, R-64, R-65, R-66)

- **About dialog false claims** — removed System Tray and drag-and-drop from
  features list. Clarified Undo/Redo scope.
- **24 hardcoded Segoe UI fonts replaced** across 9 UI files with FONTS system
  calls. macOS/Linux now render correctly.
- **4 dead UI view classes removed** — secondary_views.py deleted (~670 lines):
  KanbanView, TimelineView, ReadingListView, TagCloudView.

### Improved — Performance (R-73)

- **Batch save context manager** — `BookmarkManager.batch()` suppresses
  per-mutation saves; single flush on exit. Nestable.

## [v6.4.2] - 2026-06-06

Browser capture foundation release.

### Added

- **Browser extension MVP** — `browser-extension/` now contains a Manifest V3
  popup/options scaffold for saving the active tab to the local BOP API.
- **Extension options page** — stores localhost API port, API token, and default
  category in browser extension local storage.
- **`api-server` CLI command** — runs the existing localhost HTTP API for
  bookmarklet and extension workflows.

### Improved

- Added static extension validation tests for manifest permissions, popup API
  posting, options persistence, and asset presence.
- Added CLI coverage for `api-server` invalid-port handling and start/stop.
- Hardened an async batch-processor regression test to wait for actual worker
  completion instead of relying on a fixed short join timeout.

## [v6.4.1] - 2026-06-06

CLI reliability release.

### Fixed

- `scan --hours N` now honors the documented space-separated argument form.
  The existing `--hours=N` form remains supported.
- Invalid `scan --hours` values now print usage and do not start an
  unrestricted dead-link scan.
- `bookmark_organizer_pro.cli:main` now exists, so the `bop` console script and
  `python -m bookmark_organizer_pro.cli` entrypoint work.
- Package-level `BookmarkCLI` export is lazy-loaded so `python -m
  bookmark_organizer_pro.cli` runs without a `runpy` pre-import warning.

### Improved

- Added regression coverage for both accepted `scan --hours` forms, invalid
  input handling, the CLI entrypoint, and the package-level CLI export.

## [v6.4.0] - 2026-06-05

Usability & bulk operations release.

### Added

- **Settings gear button** — toolbar button opens quick-access settings menu
  (AI provider, categories, flatten, tags, backup)
- **Bulk operations** — Flatten All Folders, Clear All Categories, Clear All Tags
  available from Tools menu and Settings menu
- **Selection bar "Organize" button** — one-click auto-categorize selected
  bookmarks using the pattern engine
- **Selection bar "Clear Tags" button** — strip tags from selected bookmarks
- **Full GUI scaling** — zoom buttons (and Ctrl+Scroll) now scale fonts, button
  padding, sidebar width, and all layout elements (not just text)
- **Sidebar scroll fix** — mousewheel events propagate from all child widgets
  so the left panel scrolls reliably everywhere

### Changed

- Theme dropdown button now reads "Themes" (was showing the active theme name,
  which confused new users who didn't know what the button did)
- Selection bar buttons now have tooltips explaining each action
- All bulk cleanup operations work on selected bookmarks when a selection exists,
  otherwise on the full library

## [v6.3.0] - 2026-06-05

Feature release. 12 roadmap items shipped, 255 tests passing.

### Added — Features

- **Answer caching** (R-11) — LRU cache (128 entries) for RAG `ask()`.
  `clear_cache()` + `cache_stats`. Skips multi-turn conversations.
- **YouTube transcript capture** (R-12) — `services/youtube_transcript.py`.
  Detects YouTube URLs, fetches via yt-dlp CLI or library, parses VTT.
- **Atom + JSON Feed export** (R-29) — `services/feed_export.py`. CLI:
  `atom-export`, `json-feed`. Atom 1.0 (RFC 4287) + JSON Feed 1.1.
- **Matter CSV importer** (R-28) — `MatterImporter` in `importers_extra.py`.
  CLI: `import-matter`. Reads Title/URL/Tags/Status/Date Saved.
- **Zotero RDF import/export** (R-27) — `services/zotero_interop.py`. CLI:
  `import-zotero`, `zotero-export`. dc:title, dc:subject, dcterms:abstract.
- **Scheduled auto-snapshot** (R-24) — `services/auto_snapshot.py`.
  Background daemon thread with add/remove/run_once/start/stop.
- **Cross-encoder re-rank** (R-07) — optional `_try_rerank()` using
  ms-marco-MiniLM after RRF. `rerank=True` param in HybridSearch.
- **Chunk-level RAG provenance** (R-08) — `ChatTurn.chunk_provenance` with
  citation_id, bookmark_id, char_start, char_end, text_preview.
- **Collections as retrieval scopes** (R-10) — `restrict_tag` and
  `restrict_category` params on MCP `chat_with_collection`.
- **MCP auth scopes** (R-14) — `services/mcp_auth.py` with
  `MCPTokenManager`. Create/revoke tokens, read-only vs read-write scope.
- **Passphrase rotation** (R-38) — `EncryptedStore.rotate_passphrase()`
  with audit log.

### Improved — Security

- **API key storage via keyring** (R-35) — `get_api_key` checks OS keyring
  first, falls back to JSON. `set_api_key` stores in keyring when available.
- **SSRF allow-list** (R-37) — `URLUtilities.set_ssrf_allow_list(patterns)`
  adds regex whitelist for trusted internal domains.

### Improved — Testing

- **21 CLI smoke tests** (R-45) — dispatch routing, --version, help, list,
  add, search, categories, tags, stats, exports, imports. 255 total tests.

## [v6.2.1] - 2026-06-05

Bugfix + hardening release. Fixes 2 crash bugs, 6 data-corruption risks,
4 security gaps, 4 CLI parity gaps, and adds 34 new tests (222 total).

### Fixed — Critical

- **High-contrast theme crash** — `card_shadow` field added to `ThemeColors`
  dataclass. Missing ~11 fields in high-contrast palette filled with dark
  values. (A-01, B-06)
- **MCP `export_to_obsidian` NameError** — `Path` now imported at module
  level in `mcp_server.py`. (A-02)

### Fixed — Data Integrity

- **YAML frontmatter injection** in Obsidian export — all scalar values now
  properly escaped via `_yaml_escape()`. (B-01)
- **Smart Collections domain filter** — lowercased for case-insensitive
  matching. (B-02)
- **Smart Collections category filter** — changed from substring `in` to
  exact `==` match. "AI" no longer matches "Email". (B-03)
- **SingleFile backend MAX_BYTES** — now enforces 25MB limit like all other
  backends. (B-04)
- **EPUB mimetype extra field** — cleared after write for epubcheck
  compliance. (B-05)

### Fixed — Security

- **SSRF via redirect in snapshot fallback** — now follows redirects manually
  with `_is_safe_url()` check on each hop. (C-01)
- **Filesystem write sandboxing** — MCP `export_to_obsidian` vault_path must
  be under user's home directory. (C-02)
- **Bookmarklet token warning** — prints sync-risk warning after generating
  the bookmarklet URL. (C-03)
- **Path traversal in exported text** — EPUB and Obsidian export now validate
  `extracted_text_path` is under the data directory. (C-04)

### Added

- **4 CLI subcommands** — `smart-collections`, `nl-query`, `obsidian-export`,
  `epub-export`. All v6.2 features now accessible via CLI. (D-01..D-04)
- **CLI `--version` flag** — `bop --version` / `bop -V`. (E-10)
- **CLI `list --all`** — shows full list with count message when capped. (E-05)
- **CLI `check` multi-threading** — 5 concurrent workers instead of
  single-threaded. (E-06)
- **CLI help filename corrected** — references `main.py` instead of old
  `bookmark_organizer.py`. (E-01)
- **34 new tests** for SmartCollections (18), EPUB export (4), and Obsidian
  export (12). Total: 222 tests passing.

### Fixed — Cosmetic

- `main.py` docstring version updated to v6.2.0. (E-02)
- `CategoryColorManager` copy-pasted docstring replaced. (F-08)
- ROADMAP MCP tool count corrected to 20. (F-02)

## [v6.2.0] - 2026-06-05

Feature release with 22 roadmap items shipped. Consolidated ROADMAP v3 with
68 sourced references, then implemented all 19 Now-tier items plus 5 Next-tier
items. Total test suite: 188 methods across 3 files.

### Added — Features

- **Smart Collections** (`services/smart_collections.py`) — saved filter
  rules (tags, domains, dates, content types, keywords) that auto-populate
  dynamically. CRUD + evaluate API. (R-13)
- **EPUB export** (`services/epub_export.py`) — export bookmark collections
  as EPUB 3.0 e-books. Each bookmark = chapter with extracted text. No
  external deps — manual ZIP construction. (R-25)
- **Obsidian vault export** (`services/obsidian_export.py`) — Markdown files
  with YAML frontmatter (URL, tags, category, dates). Supports tag/category/
  date filtering. Also available as MCP tool `export_to_obsidian`. (R-30)
- **4 new MCP tools** — `create_flow`, `append_to_flow`, `export_zip`,
  `list_snapshots`, `export_to_obsidian` (20 total). (R-06, R-30)
- **FastMCP migration** — auto-schema from type hints when FastMCP is
  installed, raw `mcp` SDK fallback otherwise. (R-05)
- **Playwright snapshot backend** — headless Chromium for JS-heavy SPAs.
  4-backend chain: monolith → singlefile → playwright → Python BS4. (R-23)
- **Bookmarklet generator** — `scripts/generate_bookmarklet.py` creates a JS
  bookmark with auth token. Sends URL+title+selection to localhost API with
  toast feedback. (R-04)
- **Time-weighted recall** — exponential decay factor with configurable
  half-life in hybrid search. (R-09)
- **High-contrast theme** — WCAG AA accessible: yellow accents on black,
  maximum contrast. (R-49)
- **First-run privacy banner** — one-time notice confirming local-first
  operation. (R-39)

### Fixed — Quality

- **Pillow upgraded to ≥12.2.0** — fixes CVE-2026-25990, CVE-2026-40192,
  CVE-2026-42308. (R-36b)
- **ReDoS timeout on pattern engine regex** — `signal.alarm` guard on Unix,
  RecursionError/MemoryError catch on Windows. (R-36)
- **37 duplicate patterns removed** — 8 within-category + 29 cross-category.
  25+ overly broad plain patterns converted to typed. (R-33, R-34)
- **1,409 lines dead code removed** — GridView, BookmarkListView,
  MiniAnalyticsDashboard, SystemTray, BookmarkCard,
  CategoryDragDropManager. 9 UI files cleaned. (R-46)
- **Copy-pasted model docstrings** fixed in 5 files. (R-47)
- **Command palette FocusOut** — 150ms delay + child-focus check prevents
  premature close on click. (R-19)
- **GridView scroll stealing** — `bind_all` replaced with widget-scoped
  binding. (R-20)
- **Per-backup SHA-256 integrity hash** — verified on restore. (R-32)

### Improved — Infrastructure

- **Python version matrix in CI** — tests on 3.10, 3.11, 3.12, 3.13. (R-42)
- **26 new service layer tests** — embeddings, encryption, tag_linter,
  flows, digest, rss_feeds, zip_export, read_later. (R-43)
- **20 MCP server integration tests** — all 20 tools, schema validation,
  flows CRUD, dedup detection. (R-44)
- **4 broken test expectations fixed** — search-empty, cost tracker month,
  API auth, AI batch FakeConfig. 188 total tests green.

## [v6.1.0] - 2026-06-05

Hardening and reliability release. 35 fixes across 30+ files, informed by an
multi-pass deep-audit research plan (`docs/research/research-feature-plan-2026-06-05.md`).

### Fixed — Critical (P0)

- **AIBatchProcessor was dead code at runtime** — `.settings` attr and
  `categorize_bookmark()` method did not exist. Replaced with
  `get_batch_size()`/`get_rate_limit()` and `client.complete()`.
  (`services/ai_tools.py`)
- **Embedding chunk overlap infinite-loop** — `max(end-overlap, end)` always
  returned `end`, producing zero overlap. Fixed to `end - overlap` with an
  end-backward guard. (`services/embeddings.py`)
- **MCP server had no typed tool schemas** — all 15 tools used
  `additionalProperties: true`. Added proper JSON Schema for every tool with
  parameter types, descriptions, and required markers. (`mcp_server.py`)
- **PyInstaller spec missing all v6.0 hidden imports** — shipped binary
  couldn't use any v6 feature. Added 25+ service modules and optional deps.
  (`packaging/bookmark_organizer.spec`)
- **CI release upload failed** — `gh release upload` ran before the release
  existed. Added a `create-release` job before the matrix build.
  (`.github/workflows/build.yml`)

### Fixed — Reliability (P1)

- **AI/link-check blocked the main thread** — moved all AI enrichment, title
  improvement, and link checking to background threads with
  `root.after(0, callback)` UI updates. (`app_mixins/ai_enrichment.py`,
  `ai_titles.py`, `tools.py`)
- **AI enrichment/titles duplicated provider switch blocks** — replaced with
  `client.complete()` abstraction. (`app_mixins/ai_enrichment.py`, `ai_titles.py`)
- **LinkChecker had no rate limiting** — added per-domain 1s delay with proper
  `BookmarkOrganizerPro/6.0 LinkChecker` User-Agent. (`link_checker.py`)
- **`batch_refresh_metadata` mutated bookmarks from worker threads** — now
  collects results as data, applies under lock. (`managers/bookmarks.py`)
- **Dead-link scanner mutated bookmarks without lock** — wrapped mutations
  in `self._lock`. (`services/dead_link_scanner.py`)
- **VectorStore and DeadLinkScanner non-atomic writes** — replaced with
  tempfile + `os.replace`. (`services/vector_store.py`, `dead_link_scanner.py`)
- **Log file grew unbounded** — replaced `FileHandler` with
  `RotatingFileHandler(5MB, 3 backups)` + stderr fallback.
  (`logging_config.py`)
- **AICostTracker reported $0 for all models** — updated pricing table to
  mid-2026 models. (`services/ai_tools.py`)
- **API server had no auth** — added auto-generated bearer token for
  POST/DELETE + CORS deny headers. (`services/api.py`)
- **Analytics panel rebuilt all widgets every 30s** — now skips rebuild when
  stats are unchanged. (`app_mixins/dashboard.py`)
- **RSS parser vulnerable to XML bomb** — uses `defusedxml` when available.
  (`services/rss_feeds.py`)
- **Added `pyproject.toml`** with `[project]` table, optional dependency
  groups (`[ai]`, `[encryption]`, `[mcp]`, `[all]`), and entry points.

### Fixed — Data Safety (P2)

- **`save_bookmarks` lock race** — lock now held through `storage.save()`.
  (`managers/bookmarks.py`)
- **`remove_tag` was case-sensitive** while `add_tag` was not. Now both are
  case-insensitive. (`models/bookmark.py`)
- **`get_stale_bookmarks` ignored its `days` parameter**. (`managers/bookmarks.py`)
- **Search returned all bookmarks for empty query**. Now returns `[]`.
  (`search.py`)
- **Date filter included bookmarks with unparseable timestamps**. Now
  excludes them. (`search.py`)
- **`restore_backup` destroyed current data without safety net** — now
  creates a pre-restore backup. (`core/storage_manager.py`)
- **`decrypt_file` could overwrite source** — added src≠dst validation.
  (`services/encryption.py`)
- **TagManager had no thread safety** — added `RLock`. (`managers/tags.py`)
- **Importers allowed intra-file duplicates** — added `_dedup_bookmarks`.
  (`importers.py`)

### Fixed — Security

- **Snapshot banner HTML injection** — URL now escaped with `html.escape()`.
  (`services/snapshot.py`)
- **Prompt injection via unsanitized bookmark data** — added
  `sanitize_for_prompt()` utility. (`utils/safe.py`, `services/ai_tools.py`)
- **Ollama URL SSRF** — non-localhost URLs now rejected. (`ai.py`)
- **Runtime pip install supply chain risk** — `ensure_package` no longer
  auto-installs; shows clear install instruction. (`ai.py`)
- **thum.io screenshot API privacy** — now opt-in via
  `screenshot_api_enabled` setting. (`services/web_tools.py`)

### Improved

- **Duplicate-at-save-time detection** — `add_bookmark_clean` and MCP
  `add_bookmark` now return the existing bookmark with `already_exists: true`
  instead of silently returning None. (`managers/bookmarks.py`, `mcp_server.py`)
- **RAG citation validation** — hallucinated `[#cN]` tokens referencing
  non-existent chunks are stripped. (`services/rag_chat.py`)
- **Constants side-effect cleanup** — directory creation deferred to
  `ensure_directories()` called from entry points only. (`constants.py`,
  `launcher.py`, `cli.py`, `mcp_server.py`)
- **Tag linter no-op line removed**. (`services/tag_linter.py`)
- **Dead `_extract_text` conditional fixed**. (`services/web_tools.py`)
- **ROADMAP consolidated** as single source of truth with 60 prioritized
  items. Old `ROADMAP.md` + research plan merged.

## [v6.0.0] - 2026-04-19

Major release. Adds 18 new backend service modules and 20 new CLI
subcommands, informed by a competitive landscape analysis of the OSS
bookmark ecosystem (see `docs/COMPETITIVE_RESEARCH.md`). Every new
capability is gated behind optional dependencies that degrade gracefully
when missing, so the existing v5.x feature set keeps working with no
extra installs.

### Added — AI / search

- **Local semantic search** (`services/embeddings.py`,
  `services/vector_store.py`). Three-backend embedder chain: fastembed →
  model2vec → sentence-transformers. Vector store prefers LanceDB; falls
  back to in-memory JSON cosine. Stores chunked text with char-offset
  anchors for citation-aware summaries.
- **Hybrid keyword + semantic search via Reciprocal Rank Fusion**
  (`services/hybrid_search.py`). Fuses BOP's existing FTS-style
  SearchEngine with the vector store using k=60 RRF. Falls back to
  keyword-only when no embeddings.
- **Citation-aware AI summarizer** (`services/citation_summarizer.py`).
  LLM emits inline `[#cN]` citation tokens that resolve to specific text
  spans within the source. Each citation carries `chunk_id` plus
  `char_start`/`char_end` offsets so the UI can deep-link to the
  supporting span. Trust-building, deeply differentiated.
- **Conversational RAG over collections** (`services/rag_chat.py`).
  Single-turn first; multi-turn history capped to keep prompts bounded.
  Supports restricting retrieval to a subset of bookmark IDs.
- **NL → structured query translator** (`services/nl_query.py`). Schema-
  bounded LLM call fills a typed `StructuredQuery` (tags, dates, content
  type, domains, semantic seed); validated and executed locally against
  the bookmark manager. Never runs LLM-generated SQL. Falls back to a
  small heuristic when no AI is configured.
- **All 5 AI clients gained a `complete(prompt, system, max_tokens,
  temperature)` method** (OpenAI, Anthropic, Google Gemini, Groq,
  Ollama) so the new RAG / summarization / NL-query features can use the
  user's existing provider config.
- **Hybrid duplicate detector** (`services/dup_hybrid.py`). Three-pass
  layered detection: URL canonical → 64-bit SimHash (k=3 Hamming) →
  embedding cosine ≥ 0.92. Surfaces a review queue with method and
  confidence per group; never auto-merges.

### Added — Content & preservation

- **Trafilatura-based ingest pipeline** (`services/ingest.py`). At save
  time extracts main article text, computes reading time, language
  (lingua), and content type (article / video / code / paper / audio /
  social / discussion). Falls back to BS4 + heuristics when trafilatura
  is unavailable. Stores extracted text per-bookmark for reuse by
  embedding, summarization, and chat.
- **Single-file HTML snapshot archiver** (`services/snapshot.py`).
  Three-backend chain: `monolith` Rust binary → `single-file` Node CLI →
  pure-Python BS4 inliner that embeds CSS, images (as data URIs), and
  fonts. 25 MB hard ceiling per snapshot. Records `snapshot_path`,
  `snapshot_size`, `snapshot_at` on the Bookmark.
- **Per-bookmark ZIP exporter** (`services/zip_export.py`,
  Readeck-style). Each bookmark exports as a portable ZIP containing
  `metadata.json` + `notes.md` + `snapshot.html` (if captured) +
  `extracted.txt` (if ingested). Whole-collection mode bundles every
  per-bookmark ZIP into one file for easy backup.
- **Encrypted-DB toggle** (`services/encryption.py`). Optional AES-256-GCM
  with PBKDF2-HMAC-SHA256 (480 000 iterations, NIST SP 800-132 floor)
  over arbitrary JSON files. Adds `encrypt`/`decrypt` CLI subcommands.

### Added — Organization

- **Tag normalization linter** (`services/tag_linter.py`). Detects near-
  duplicate tags, casing drift, and singular/plural variants. Knows 14
  canonical aliases (`py`/`py3`/`python3` → `python`, `js` → `javascript`,
  `k8s` → `kubernetes`, etc.). Surfaces a review queue with suggested
  merges; `--apply` merges with one command. Goes beyond Karakeep's
  enforcement-only approach by working retrospectively on already-
  imported tag chaos. Tested on 4 840 real bookmarks.
- **Read-later queue** as a first-class boolean field on the Bookmark
  model (not a tag). New `read_later`, `read_later_position` fields.
  `services/read_later.py` exposes enqueue / dequeue / reorder / peek /
  complete operations.
- **Flows / research-trail manager** (`services/flows.py`). Ordered,
  annotated bookmark sequences (Grimoire-inspired). Each Flow has steps
  with per-step notes; bookmarks are stamped with `flow_id` and
  `flow_position`. Persisted to `~/.bookmark_organizer/flows.json`.
- **Daily digest service** (`services/digest.py`). Five-section view:
  on-this-day, this-week-last-year, rediscover (random older saves),
  read-later top, stale-but-loved (frequently visited but unopened
  recently). Shaarli-inspired.
- **RSS / Atom feed ingestor** (`services/rss_feeds.py`) with per-feed
  AI tagging modes (PREDEFINED / EXISTING / AUTO_GENERATE / DISABLED) +
  default static tags. Solves the missing layer that both Karakeep #833
  and Linkwarden #956 have open. Stdlib-only XML parser; tracks seen
  GUIDs to avoid re-import.

### Added — Reliability

- **Scheduled dead-link scanner** (`services/dead_link_scanner.py`).
  Background daemon that periodically scans the library and persists
  broken/redirected URLs to a queue. Configurable interval and
  "only-unchecked-for-N-hours" filter. Brings BOP up to LinkAce parity.
- **5 new importers** (`importers_extra.py`): Pocket export
  (HTML + JSON), Readwise Reader CSV, Pinboard JSON, Instapaper CSV,
  Reddit Saved JSON. Positions BOP as the universal landing pad after
  Pocket's July 2025 shutdown.

### Added — Integration

- **MCP server** (`mcp_server.py`). Stdio transport. Exposes 15 tools:
  list_bookmarks, get_bookmark, search_bookmarks, semantic_search,
  hybrid_search, add_bookmark, list_tags, list_categories,
  get_extracted_text, chat_with_collection, summarize_bookmark,
  daily_digest, list_dead_links, list_flows, get_flow. Run with
  `python -m bookmark_organizer_pro.mcp_server`. **No OSS bookmark
  manager exposes itself as MCP today** — first-mover. Makes BOP a
  first-class citizen for MCP-compatible clients.

### Added — CLI

- 20 new subcommands: `ingest`, `snapshot`, `embed`, `semantic`,
  `hybrid`, `summarize`, `chat`, `ask`, `lint-tags`, `dups`, `scan`,
  `digest`, `flow`, `feed`, `import-pocket`, `import-readwise`,
  `import-pinboard`, `import-instapaper`, `import-reddit`, `zip-export`,
  `encrypt`, `decrypt`, `read-later`, `mcp-server`.

### Changed — Bookmark model

Extended with v6 fields (all default-empty, fully backward-compatible
with v5.x JSON): `read_later`, `read_later_position`, `snapshot_path`,
`snapshot_size`, `snapshot_at`, `extracted_text_path`, `content_type`,
`sentiment`, `flow_id`, `flow_position`, `embedding_model`,
`embedding_dim`. `from_dict` round-trips all new fields with defensive
coercion.

### Changed — Storage

New per-feature directories under `~/.bookmark_organizer/`:
`snapshots/`, `extracted/`, `embeddings/`, `exports/`. New JSON files:
`flows.json`, `feeds.json`, `dead_links.json`. Existing bookmark files
unchanged.

### Documentation

- `docs/COMPETITIVE_RESEARCH.md` — 2 200-word competitive landscape
  analysis covering Karakeep, Linkwarden, Linkding, Shiori, Wallabag,
  Readeck, Buku, Floccus, Tab Stash, Stash, Reor, KaraKeep HomeDash, plus
  AI/RAG state-of-the-art (EmbeddingGemma, model2vec, lancedb, MCP,
  citation-aware RAG). Top-20 prioritized improvement list informed v6.
- `requirements.txt` extended with optional v6 deps (trafilatura,
  fastembed, lancedb, cryptography, mcp) using Python version markers.
- Local working notes rewritten for v6.

## Unreleased

### Changed
- **Repository organization**: moved source assets to `assets/`, build helpers to
  `scripts/`, PyInstaller metadata to `packaging/`, and added
  `docs/REPOSITORY_STRUCTURE.md` as the canonical layout guide.
- **Build hygiene**: PyInstaller, local build scripts, CI, and README build
  instructions now use `packaging/bookmark_organizer.spec`; generated
  `build/`, `dist/`, pytest cache, and bytecode outputs are ignored and safe to
  delete.
- **Developer workflow**: added `.gitattributes`, pytest configuration, a safe
  `scripts/clean_workspace.py` cleanup helper, and architecture notes that make
  the next `main.py` extractions explicit.
- **Architecture cleanup**: moved dependency discovery/install logic and shared
  runtime helpers out of `main.py` into package utilities, keeping the desktop
  entry point focused on UI orchestration.
- **Dead-code cleanup**: removed unused legacy dialog and dictionary helpers
  from `main.py`.

## [v5.2.2] - 2026-04-19

### Changed — Reliability & UX Hardening Pass
Large audit across backend and UI. 14 files touched, 2,116 insertions, 633
deletions.

- **Data/config validation** — stricter input validation across AI configs,
  bookmark and category models, and search queries. Defensive `from_dict`
  paths reject malformed payloads without crashing the app.
- **Atomic persistence** — storage writes hardened against partial writes and
  concurrent access; safer path handling.
- **Network safety** — additional SSRF and open-redirect guards in
  `url_utils`, `utils/metadata`, and `link_checker`. Timeouts and bounds
  tightened.
- **Import/export escaping** — importers re-audited for entity handling and
  field sanitization across all supported formats.
- **Category repair** — `CategoryManager` now recovers from corrupted or
  inconsistent category trees instead of failing to load.
- **Search edge cases** — query parser hardened against malformed tokens and
  pathological inputs.
- **Premium UI feedback paths** — UI reliably surfaces success/error state
  through the embedded log/toast paths instead of silent failures.
- **Regression coverage** — `tests/test_core.py` expanded (+166 lines)
  covering the new hardening paths.

### Build
- Version bumped to 5.2.2 across `main.py`, `bookmark_organizer_pro/constants.py`,
  `bookmark_organizer.spec`, and `version_info.txt`.

## [v5.2.1] - 2026-04-19

### Changed
- **Repo cleanup**: Renamed `bookmark_organizer_pro_v4.py` → `main.py`. The `_v4`
  suffix was legacy from the v4.x line and implied the existence of v1/v2/v3
  variants that never existed in the current tree. The modular
  `bookmark_organizer_pro/` package is the canonical backend; `main.py` is a
  thin(-ish) UI entry point that imports from it.
- `bookmark_organizer.spec` now points at `main.py` and carries the current
  `APP_VERSION = "5.2.0"` (was stuck at `4.1.0`).
- `version_info.txt` bumped from `4.6.0.0` → `5.2.0.0` so PyInstaller-built
  binaries report the correct Windows version metadata.
- README, local working notes, and all docs updated to reference `main.py`.

## [v5.2.0] - 2026-04-19

### Fixed
- **HTML entity decode in imports** — Titles like `Love, Death &amp; Robots` now
  display correctly as `Love, Death & Robots`. Applied `html.unescape()` to
  titles, URLs, folder names, and tags in all HTML-parsing importers
  (Netscape, Pocket, Raindrop, OPML).
- Right Analytics sidebar widened 300 → 360px to prevent header clipping at
  115% default zoom.
- Left sidebar widened 280 → 320px for consistent breathing room.

## [v5.1.0] - 2026-04-19

### Added
- Ollama local LLM support — server URL field + auto-detect models in AI
  settings dialog. Model catalog expanded to include llama3.3, qwen3, phi4,
  gemma3, deepseek-r1, mixtral, codellama, command-r.

### Changed
- Default zoom bumped 100% → 115% for better readability on high-DPI displays.
- Zoom scaling now applies to ALL text (Tk named fonts + custom FONTS system)
  so default launch is no longer cramped.

## [v4.10.0] - 2026-04-18

### Removed
- **2,558 lines of dead code**: `BookmarkOrganizerApp` (1,566 lines) and
  `EnhancedBookmarkOrganizerApp` (992 lines) — neither was instantiated.
  `FinalBookmarkOrganizerApp` is the sole production class.
- Main file: 21,127 → 18,569 lines.

### Added
- **`requirements.txt`**: Standard dependency file for pip/venv workflows.
- **GitHub Actions CI/CD** (`.github/workflows/build.yml`): PyInstaller builds
  for Windows/macOS/Linux triggered on tag push and manual dispatch. Auto-uploads
  release artifacts.
- **Import from Browser**: Import button now shows a menu with "Import from
  File..." plus auto-detected browsers (Chrome, Firefox, Edge, Brave). Imports
  bookmarks directly from the browser's profile data.
- **Search placeholder text**: "Search bookmarks... (Ctrl+F)" shown in muted
  text, clears on focus, restores on blur if empty.

### Changed
- **Theme dropdown**: Shows display names (e.g., "GitHub Dark") with dark/light
  indicators and active checkmark instead of raw internal keys.
- **Drag-drop import area**: Collapses to a compact "Import more..." link after
  first successful import, saving sidebar space.

## [v4.9.0] - 2026-04-18

### Changed -- Premium UX Polish Pass

**Empty State**
- Beautiful centered empty state when 0 bookmarks exist: large icon, heading,
  subtitle, two CTA buttons (Import Bookmarks / Add Bookmark), and a tip about
  drag-and-drop. Replaces the previous blank treeview.
- Empty state auto-hides when bookmarks are loaded, auto-shows when all removed.

**Toast Notification System**
- New `ToastNotification` class: non-blocking, auto-dismissing, stacking toasts
  that appear top-right with colored icon strips (success=green, error=red,
  warning=amber, info=blue).
- Import completion, link check results, and duplicate check feedback now use
  toasts instead of modal `messagebox.showinfo()` dialogs.

**Category Sidebar**
- Category items now use frame-based rows with separate name label and count
  badge (pill-style, `bg_tertiary` background).
- Hover effect applies to the entire row including the count badge.
- Count badges only shown when count > 0 (cleaner zero state).

**Font Consistency**
- Replaced all hardcoded `("Segoe UI", ...)` font references with the
  centralized `FONTS` system (FONTS.header, FONTS.small, FONTS.body).
- Search icon, clear button, sidebar headers, treeview headings all unified.

**Build Metadata**
- Author: "Bookmark Organizer Team" -> "SysAdminDoc"
- Website: placeholder URL -> actual GitHub repo URL
- Build date: "January 2026" -> "April 2026"

### Fixed
- `Image.Image` type hints quoted to prevent `AttributeError` when Pillow is
  not yet imported at class definition time (startup crash on fresh installs).

## [v4.8.0] - 2026-04-18

### Changed — Categorization Coverage Expansion Phase 3
Expanded DEFAULT_CATEGORIES from 1,583 → **1,963 patterns** (+380, +24%).

**Categories expanded:**
| Category | Before | After | Added |
|----------|--------|-------|-------|
| Sports | 10 | 60 | Pro leagues, fantasy, betting, stats, soccer |
| Automotive | 9 | 60 | 15 brands, parts stores, reviews, EV sites |
| Food & Dining | 11 | 62 | Recipes, grocery chains, meal kits, delivery |
| Education | 17 | 64 | MOOCs, .edu catch-all, textbooks, K-12, certs |
| Social Media | 17 | 36 | Messaging, photo social, link-in-bio |
| Gaming | 39 | 58 | Mod sites, retro, reviews, keywords |
| Entertainment | 107 | 130 | Podcasts, anime/manga, streaming keywords |
| Travel | 37 | 54 | Car rental, cruises, keywords |
| Reference | 53 | 68 | Calculators, converters, keywords |
| + 10 more cats | — | — | Keyword fallbacks added |

**Keyword fallback additions (~100):**
Added `keyword:` patterns to 20+ categories that previously relied only on
domain matching. Covers: shopping intent (coupon, promo code, deal), health
(symptoms, treatment, fitness), education (how to, learn, study guide),
entertainment (podcast, stream, anime), government (legislation, public
record), development (open source, npm package, source code), and more.

## [v4.7.0] - 2026-04-18

### Changed — Modular Extraction Phase 2
Extracted ~2,010 lines from the 22,924-line main file into 5 new package modules:

**New modules:**
```
bookmark_organizer_pro/
├── ai.py           # AI providers: OpenAI, Anthropic, Google, Groq, Ollama
│                   #   AIConfigManager, AIClient hierarchy, ensure_package
├── search.py       # SearchQuery, SearchEngine, FuzzySearchEngine
│                   #   levenshtein_distance, fuzzy_match
├── importers.py    # BrowserProfileImporter (Chrome/Firefox/Edge/Brave)
│                   #   PocketImporter, RaindropImporter, OPMLExporter
│                   #   TextURLImporter, OPMLImporter, OneTabImporter
│                   #   NetscapeBookmarkImporter
├── link_checker.py # LinkChecker with redirect detection
└── url_utils.py    # URLUtilities (redirect resolver, HTTPS upgrade,
                    #   affiliate detection, canonical URL)
```

**Migration impact:**
- Main file: 22,924 → 20,914 lines (~2,010 lines extracted)
- Package exports: 57 → 83 public names
- Zero behavioral changes — all imports resolved via package

### Fixed
- README clone URL (was `yourusername`, now `SysAdminDoc`)
- `.gitignore` removed `*.spec` that was blocking PyInstaller spec tracking
- AI client `print()` calls replaced with `log.error()`
- Importer `print()` calls replaced with `log.error()`

## [v4.6.0] - 2026-04-18

### Changed — Massive Categorization Coverage Expansion
Expanded DEFAULT_CATEGORIES from 892 → **1,583 patterns** (+77%). Measured
against a real-world export of 5,293 bookmarks:

- **Before**: 31.4% uncategorized (1,660 bookmarks)
- **After**: 15.7% uncategorized (832 bookmarks)
- **Improvement**: coverage jumped from 68.6% → **84.3%**

Added ~700 new patterns covering:
- **AI**: grok, notebooklm, openrouter, klingai, tattooai, prompts.chat,
  bitlife, otter, lenso, copyseeker, apollo, jobo.world, venice, phind, you.com
- **SysAdmin & IT**: cisco, juniper, fortinet, sonicwall, sophos, meraki,
  nirsoft, ntlite, autoit, autohotkey, christitus, nexttechconsultants,
  teamlogicit, zoom, webex, logmein, netgate, pfsense, avast forums
- **News**: local stations (whio, thinktv), alternative (infogalactic,
  bellingcat, dailywire, mises), science (nuclearsecrecy, phys.org)
- **Weather**: cira.colostate, weatherwise, velocityweather, pivotalweather
- **Health**: mavenimaging, 2020imaging, compassphs, covid19criticalcare,
  anthem, mymoffitt, weasis, osirix, radiant
- **Shopping**: rei, kuhl, patagonia, thefurniturewarehouse, secretlab,
  laserpointerpro, extraspace storage, northerner
- **Finance**: wpcuonline, achievacu, creditonebank, tiaa, geico, anthem,
  kraken, binance, bitbo, finviz, marketwatch, coingecko
- **Career**: careerplug, jobs.net, kellycareernetwork, workday, greenhouse,
  lever, angel.co, wellfound, weworkremotely, flexjobs
- **Downloads**: fmhy, lookmovie, couchtuner, filenext, rapidgator,
  getintopc, igg-games, skidrow, downr, audfree
- **Entertainment**: uflix, thetvapp, m4uhd, publiciptv, kapwing, storyblocks,
  pandora, bensound, groovedrumming
- **Forums**: patriots.win, kiwifarms, 16chan, ar15.com, forum.avast
- **Real Estate**: hotpads, appfolio, forrent, homes.com, loopnet, costar
- **Google/Microsoft catch-alls**: `domain:google.com` as Productivity
  fallback (specific subdomains still match their proper categories first),
  chrome.google.com for extensions
- **Keyword fallbacks**: remote desktop, web hosting, VPS, backup solution,
  file sharing, cloud storage, virtual machine, pfsense, print driver,
  bitcoin price, crypto, stock price, mortgage, zestimate, careers at,
  ai generator, prompt engineering, and more

### Fixed
- `whio.com`, `kuhl.com`, `covid19criticalcare.com`, `grok.com`, `arcgis.com`,
  `sysadmindoc.github.io` and many others now categorize correctly (were
  falling through to uncategorized)

## [v4.5.0] - 2026-04-18

### Changed — Modular Architecture Refactor
Broke the 25,310-line monolithic file into a proper Python package plus a
thinner UI + wiring file. Backend infrastructure now lives in `bookmark_organizer_pro/`.

**New package structure:**
```
bookmark_organizer_pro/
├── __init__.py            # Package-level re-exports (57 public names)
├── constants.py           # APP_NAME, paths, platform detection
├── logging_config.py      # AppLogger singleton + global `log`
├── utils/
│   ├── safe.py            # safe_int, safe_float, safe_json_loads, clamp, etc.
│   ├── validators.py      # validate_url, validate_path
│   ├── url.py             # normalize_url + TRACKING_PARAMS (60+ entries)
│   ├── metadata.py        # fetch_page_metadata, wayback_check, wayback_save
│   └── health.py          # calculate_health_score, merge_duplicate_bookmarks
├── models/
│   ├── bookmark.py        # Bookmark dataclass
│   ├── category.py        # Category dataclass
│   └── tag.py             # Tag dataclass
├── core/
│   ├── pattern_engine.py  # PatternEngine
│   ├── storage_manager.py # StorageManager (atomic writes, backups)
│   ├── category_manager.py # CategoryManager + CATEGORY_ICONS + get_category_icon
│   └── default_categories.py # DEFAULT_CATEGORIES (892 patterns, 32 categories)
└── io_formats/
    └── xbel.py            # XBELHandler
```

**Migration impact:**
- Main file: 25,310 → 22,923 lines (~2,400 lines extracted)
- Main file now imports from the package; all existing UI code unchanged
- External consumers can `from bookmark_organizer_pro import Bookmark, normalize_url, ...`
- 892 categorization patterns preserved
- Zero behavioral changes — all tests pass, all pattern matches identical

**Kept in main file (intentionally, due to tight UI coupling):**
- UI classes (BookmarkOrganizerApp, dialogs, views, ~100 classes)
- BookmarkManager, TagManager (reference UI callbacks)
- FaviconManager, LinkChecker (tied to UI progress callbacks)
- AI provider clients (tied to UI cost tracker)

## [v4.4.0] - 2026-04-18

### Added
- **Soft Delete / Trash** — `soft_delete_bookmark()`, `restore_from_trash()`, `get_trash()`, `empty_trash()`. Bookmarks go to a recoverable trash instead of permanent deletion. Inspired by LinkAce (1K+ stars)
- **LinkChecker Redirect Detection** — Detects HTTP redirects during link checking, stores final URL + redirect chain in custom_data. `get_redirected_bookmarks()` lists affected bookmarks, `fix_redirect()` updates URL to final destination. Inspired by bookmarks-organizer (209 stars) and TidyMark (196 stars)
- **Random Bookmark Rediscovery** — `get_random_bookmark()` returns a random bookmark for rediscovering forgotten saves. Inspired by Buku (7.1K stars)
- **Batch Metadata Refresh** — `batch_refresh_metadata()` re-fetches titles/descriptions/favicons for all bookmarks using ThreadPoolExecutor (configurable 1-10 workers). Progress callback support. Inspired by Buku's multi-threaded DB refresh
- **Auto-Clean URL on Add** — `add_bookmark_clean()` strips tracking params, normalizes URL, auto-categorizes, and checks for duplicates in one call. Inspired by Shaarli's transparent UTM stripping
- **XBEL Import/Export** — `XBELHandler.export()` and `XBELHandler.import_from_xbel()` support XML Bookmark Exchange Language, a standard interchange format. Round-trip preserves titles, URLs, categories, tags, descriptions, and dates. Atomic file writes. Inspired by Buku (supports 7 formats)

### Changed
- LinkChecker now tracks redirect chains (stores redirect_url, redirect_count, redirect_chain per bookmark)
- Netscape importer error logging uses `log.error()` instead of `print()`

## [v4.3.0] - 2026-04-18

### Added
- **URL Normalization Engine** — Academic-grade URL canonicalization (RFC 3986 + web heuristics). Strips 60+ tracking parameters, normalizes scheme/host/port/path, removes fragments, sorts query params, strips www prefix, removes default index files. Based on ACM CIKM 2009 research on URL normalization for de-duplication
- **Page Metadata Fetcher** — `fetch_page_metadata(url)` auto-fetches title, meta description, and favicon URL from live pages. Handles both `name` and `property` meta attributes, resolves relative favicon paths
- **Wayback Machine Integration** — `wayback_check(url)` queries archive.org API for existing snapshots; `wayback_save(url)` submits pages for archival. Inspired by Linkwarden/Shiori
- **Bookmark Health Scoring** — `calculate_health_score(bookmark)` returns 0-100 score based on 7 factors: link validity (40pts), title quality (10pts), description/notes (10pts), tags (10pts), recency (10pts), staleness (10pts), categorization (10pts). Inspired by Hoarder's health monitoring
- **Smart Duplicate Merger** — `merge_duplicate_bookmarks()` combines duplicate entries keeping best title, earliest created date, latest visit, combined tags (union), longest description, summed visit counts, and best favicon. Inspired by BrowserBookmarkChecker and Buku
- **BookmarkManager.merge_duplicates()** — One-call method to find and merge all duplicates with dry-run support
- **BookmarkManager.get_health_scores()** — Returns all bookmarks with health scores, sorted worst-first
- **BookmarkManager.fetch_metadata_for_bookmark()** — Updates a bookmark's title/description/favicon from the live URL
- **BookmarkManager.check_wayback()** / **save_to_wayback()** — Wayback Machine check and save per bookmark

### Changed
- `find_duplicates()` now uses the new `normalize_url()` canonicalization instead of simple path-only stripping. Catches far more duplicates (http vs https, www vs non-www, tracking params, sorted query params)
- `import_html_file()` now normalizes URLs before duplicate checking
- `import_json_file()` now normalizes URLs before duplicate checking

## [v4.2.0] - 2026-04-18

### Added
- 5 new categories: SysAdmin & IT, Weather & Meteorology, Downloads & Torrents, Media Production & Design, Software & Customization, Productivity & Tools
- 894 categorization patterns (up from ~150) across 32 categories
- Expanded icon mapping with 65+ keyword-to-emoji associations
- Domain patterns for 500+ popular websites derived from real-world bookmark analysis

### Changed
- PatternEngine domain matching now uses proper suffix matching instead of substring (fixes false positives like `t.co` matching inside `reddit.com`)
- Government & Legal `.gov` pattern uses regex to prevent false matches
- Redirects & Shorteners patterns converted to `domain:` type for precision
- Categories expanded from 27 to 32 with comprehensive pattern coverage

### Fixed
- Domain matching bug: `domain:t.co` no longer falsely matches `reddit.com`
- Plain pattern `redirect.` no longer catches unrelated URLs
- StorageManager: atomic write via os.replace() prevents data loss on Windows
- Bookmark ID: os.urandom() for true uniqueness instead of collision-prone time+hash
- Bookmark.from_dict(): validates URL is non-empty
- StorageManager.load(): skips individual corrupt entries instead of failing entire load
- SearchQuery: domain filter uses suffix matching, tag filter uses exact match
- HTML import: decodes HTML entities in titles, normalizes URLs for dedup
- JSON import: per-item error handling with logging
- HTML export: escapes tag values in TAGS attribute
- JSON export: atomic write via temp file + os.replace()
- Backup rotation: handles unlink failures gracefully
- Replaced print() error calls with structured log.error()

## [v4.1.0] - 2026-01

- Initial public release
- Multi-format import (HTML, JSON, CSV, OPML, TXT)
- AI-powered categorization (OpenAI, Anthropic, Google, Groq, Ollama)
- 10+ built-in themes
- Advanced search with boolean operators
- Undo/redo command stack
- System tray integration
- Favicon caching
- Automatic backups
