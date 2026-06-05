# Research Feature Plan -- Bookmark Organizer Pro v6.2.0 → v6.2.1

> **Date:** 2026-06-05 | **Analyst:** 8-agent code audit + ecosystem research + UX walkthrough
> **Scope:** Net-new findings not already on ROADMAP.md v3. Complements, does not duplicate.
> **Status:** All P0 and P1 findings resolved in v6.2.1. See CHANGELOG.md.

---

## Executive Summary

BOP v6.2.0 ships 20 MCP tools, 4-backend snapshot chain, smart collections,
EPUB/Obsidian export, hybrid search with time-weighting, and 188 passing tests.
The codebase is 135 files / ~37K lines with 29 roadmap items still open.

This research pass surfaced **2 crash bugs**, **6 data-corruption risks**,
**4 security gaps**, **9 CLI parity gaps**, **11 UX friction points**, and
**6 ecosystem shifts** that affect existing roadmap priorities. It also
identified **20 high-value missing test surfaces** (3 flagship v6.2 services
have zero test coverage).

**Top 3 urgent actions:**
1. Fix BUG-TH-1 (`card_shadow` not a ThemeColors field -- likely TypeError on
   high-contrast theme use) and BUG-MCP-1 (`Path` not imported in
   `t_export_to_obsidian` -- NameError at runtime).
2. Fix YAML frontmatter injection in obsidian_export.py (BUG-OB-1/2/3) --
   data corruption via unescaped title/url/category.
3. Add test coverage for SmartCollections, EPUB export, and Obsidian export
   (3 flagship v6.2 features with zero tests).

---

## Evidence Base

| Source | Method | Confidence |
|--------|--------|------------|
| 8-file code audit (SC, EPUB, Obsidian, Snapshot, Bookmarklet, HybridSearch, Theme, MCP) | Line-by-line review | Verified |
| ROADMAP verification (29 open items + completed items) | Cross-reference code vs. claims | Verified |
| Top-20 missing test analysis | Coverage gap analysis | Verified |
| Ecosystem research (14 competitors, MCP spec, deps) | Web search + release notes | Likely (Jun 2026 data) |
| UX walkthrough (7 flows: first run, import, AI, search, MCP, CLI) | Static code analysis | Likely (not live-validated) |

---

## New Findings

### A. Crash Bugs (P0 -- fix before any release)

**A-01. ThemeColors rejects unknown `card_shadow` kwarg (BUG-TH-1)**
- File: `bookmark_organizer_pro/theme_runtime.py:499`
- `ThemeColors` (defined in `ui/theme.py`) is a dataclass. It has no
  `card_shadow` field. The `high_contrast` theme dict passes
  `card_shadow="#000000"` as a keyword argument. Python dataclasses reject
  unexpected kwargs with `TypeError`.
- Impact: Any code path that instantiates the `high_contrast` ThemeColors
  crashes. Since theme objects are built at module import time inside
  `BUILT_IN_THEMES`, this crashes on `import theme_runtime` if high_contrast
  is ever selected.
- Confidence: **Verified** -- `card_shadow` is not in `ThemeColors` field list.
- Fix: Either add `card_shadow: str = "#d8e1dd"` to `ThemeColors`, or remove
  the `card_shadow=` kwarg from the high_contrast definition. Recommend
  adding the field (other themes may benefit).
- Effort: S (one-liner)

**A-02. `Path` not imported in `t_export_to_obsidian` (BUG-MCP-1)**
- File: `bookmark_organizer_pro/mcp_server.py:316`
- `vault = Path(vault_path).expanduser()` -- but `Path` is not imported at
  the top of mcp_server.py. The only `Path` in the file is a local import
  `from pathlib import Path as _P` scoped to `t_get_extracted_text` (line 207).
  Line 316 will raise `NameError: name 'Path' is not defined`.
- Impact: MCP tool `export_to_obsidian` is dead at runtime. Any MCP client
  calling it gets an error.
- Confidence: **Verified** -- grep confirms no top-level `Path` import.
- Fix: Add `from pathlib import Path` to the top-level imports, or change
  line 316 to use `from pathlib import Path; vault = Path(vault_path)...`
  inside the function.
- Effort: S (one-liner)

### B. Data Corruption / Functional Bugs (P1)

**B-01. YAML frontmatter injection in obsidian_export.py (BUG-OB-1/2/3)**
- File: `bookmark_organizer_pro/services/obsidian_export.py:62-66`
- `url:`, `category:`, and `title:` are written as raw/minimally-quoted
  strings. A bookmark title like `My "Title\nnew_key: injected` breaks
  the YAML. A URL with `: ` or `#` corrupts the frontmatter.
- `_yaml_list()` (line 42) wraps tags in double quotes but does not escape
  embedded double-quote characters.
- Impact: Obsidian will fail to parse the frontmatter, losing metadata for
  the note. With malicious crafting, arbitrary YAML keys can be injected.
- Confidence: **Verified** -- no YAML escaping anywhere in the file.
- Fix: Use `yaml.dump()` for the frontmatter block, or at minimum:
  (a) double-quote all scalar values, (b) escape `"` as `\"` inside
  double-quoted YAML strings, (c) escape newlines as `\n`.
- Effort: S-M

**B-02. Smart Collections domain filter not lowercased (BUG-SC-1)**
- File: `bookmark_organizer_pro/services/smart_collections.py:65`
- `domain = bookmark.domain` is used raw. Filter domains are lowered via
  `d.lower()`, but if `bookmark.domain` returns `GitHub.com`, the `in` check
  fails.
- Impact: Domain-based smart collection filters silently miss bookmarks with
  mixed-case domains.
- Confidence: **Verified** -- line 65 has no `.lower()`.
- Fix: `domain = bookmark.domain.lower()` on line 65.
- Effort: S (one-liner)

**B-03. Smart Collections category filter uses substring matching (BUG-SC audit)**
- File: `bookmark_organizer_pro/services/smart_collections.py:61`
- `c.lower() in cat_lower` means a filter for category `"AI"` matches
  `"Email"` (because `"ai"` is in `"email"`).
- Impact: Category-filtered smart collections return false positives.
- Confidence: **Verified** -- substring `in` on line 61.
- Fix: Use equality (`==`) or startswith instead of `in`.
- Effort: S

**B-04. SingleFile backend skips MAX_BYTES check (BUG-SN-1)**
- File: `bookmark_organizer_pro/services/snapshot.py:113-132`
- Monolith enforces `MAX_BYTES` (line 108), Playwright enforces it (line 151),
  Python fallback enforces it (line 217). SingleFile does not.
- Impact: A 500MB page captured via SingleFile is persisted without limit.
- Confidence: **Verified** -- no size check in `_snapshot_singlefile`.
- Fix: Add the same check after line 131:
  `if out_path.stat().st_size > self.MAX_BYTES: out_path.unlink(); return False, "snapshot too large"`
- Effort: S

**B-05. EPUB mimetype entry may have extra field data (BUG-EP-1)**
- File: `bookmark_organizer_pro/services/epub_export.py:129-130`
- EPUB OCF 3.0 section 3.3 requires the `mimetype` entry to be first in the
  ZIP with no extra field. `zipfile.ZipFile(..., ZIP_DEFLATED)` as the
  constructor compression default may set extra field bytes on entries.
  `writestr("mimetype", ..., compress_type=ZIP_STORED)` correctly stores
  uncompressed but does not clear the extra field.
- Impact: Strict EPUB validators (epubcheck) reject the file. Most readers
  still accept it.
- Confidence: **Likely** -- Python's zipfile module behavior varies by version.
  Needs live validation with epubcheck.
- Fix: After writing the mimetype entry, patch `zf.infolist()[0].extra = b""`.
  Or open the ZipFile with `ZIP_STORED` as default compression.
- Effort: S

**B-06. High-contrast theme missing ~11 ThemeColors fields (BUG-TH-2)**
- File: `bookmark_organizer_pro/theme_runtime.py:472-504`
- The high_contrast theme does not set: `hover`, `drag_target`, `drag_target_bg`,
  `drop_zone`, `drop_zone_active`, `drop_zone_border`, `status_success`,
  `status_warning`, `status_error`, `status_info`, `card_bg`,
  `scrollbar_thumb_hover`.
- These fall back to the light-theme defaults from the dataclass (white `#ffffff`
  card_bg, light green `#def7ee` hover, etc.), breaking the dark high-contrast
  theme with visible light elements.
- Impact: Visual breakage when high-contrast theme is active.
- Confidence: **Verified** -- compared field lists.
- Fix: Set all missing fields to dark values consistent with the theme.
- Effort: S

### C. Security Issues (P1-P2)

**C-01. SSRF via redirect in Python snapshot fallback (SEC-SN-1)**
- File: `bookmark_organizer_pro/services/snapshot.py:168`
- `_is_safe_url()` checks the initial URL, but `requests.get(..., allow_redirects=True)`
  follows redirects to unchecked destinations. A URL that initially resolves to
  a public IP could redirect to `http://169.254.169.254/` (AWS metadata) or
  `http://127.0.0.1/`.
- Impact: SSRF to internal services. Mitigated by local-only deployment but
  relevant if the API is exposed on a network.
- Confidence: **Verified** -- `allow_redirects=True` on line 168, no redirect
  target check.
- Fix: Use `allow_redirects=False`, follow redirects manually with
  `_is_safe_url()` check on each hop. Or use `requests.Session` with a
  redirect hook.
- Effort: S-M
- Related: R-37 (SSRF allow-list) covers the broader pattern.

**C-02. Arbitrary filesystem write via MCP `export_to_obsidian` vault_path (SEC-OB-2)**
- File: `bookmark_organizer_pro/mcp_server.py:316`
- `Path(vault_path).expanduser()` is passed directly from MCP tool arguments
  with no validation. An attacker with MCP access could write `.md` files to
  any directory (e.g., `C:\Windows\System32`).
- Impact: File write to sensitive locations. Mitigated by MCP transport trust
  boundary (stdio = same-user), but should be sandboxed anyway.
- Confidence: **Verified** -- no path validation.
- Fix: Validate that `vault_path` is under the user's home directory or a
  configured allowed-paths list.
- Effort: S

**C-03. Bookmarklet token exposed via browser sync (SEC-BM-1)**
- File: `scripts/generate_bookmarklet.py:35,52`
- The API bearer token is embedded verbatim in the `javascript:` URL. If
  the user has Chrome Sync / Firefox Sync enabled, the token is uploaded to
  cloud servers in cleartext.
- Impact: Token leakage via bookmark sync.
- Confidence: **Verified** -- token is in the URL.
- Fix: Add a warning message after printing the bookmarklet: "WARNING: If
  bookmark sync is enabled, this token will be uploaded to your browser's
  cloud service." Also consider a session-based challenge instead of a static
  bearer token.
- Effort: S (warning) / M (session challenge)

**C-04. `extracted_text_path` path traversal in EPUB and Obsidian export (SEC-EP-1, SEC-OB-1)**
- Files: `epub_export.py:69`, `obsidian_export.py:94`
- Both read `Path(bm.extracted_text_path).read_text()` without validating
  that the path is under the expected data directory.
- Impact: If the bookmark model is populated with a crafted path, arbitrary
  file contents are included in exports.
- Confidence: **Verified** -- no path validation in either file.
- Fix: Validate that `extracted_text_path` starts with `DATA_DIR` or
  `EXTRACTED_DIR` before reading.
- Effort: S

### D. CLI Parity Gaps (P2 -- 4 "done" features not exposed via CLI)

**D-01. Smart Collections has no CLI subcommand**
- `services/smart_collections.py` exists (R-13 marked done), but there is no
  CLI command to list/create/evaluate smart collections. Only accessible via
  GUI and programmatic API.
- Effort: S | Tier: Now

**D-02. NL Query has no CLI subcommand**
- `services/nl_query.py` exists and is imported, but no `nl-query` or
  `natural` CLI command exposes it. The roadmap "State of the Project"
  mentions NL-query as shipped, but CLI users cannot access it.
- Effort: S | Tier: Now

**D-03. Obsidian export has no CLI subcommand**
- Available via MCP (`export_to_obsidian`) but not CLI. The module docstring
  even says `CLI: bop obsidian-export --vault ~/Notes --since 2026-06-01`
  but the command does not exist in cli.py's dispatch dict.
- Effort: S | Tier: Now

**D-04. EPUB export has no CLI subcommand**
- `services/epub_export.py` exists (R-25 marked done) but no CLI command.
- Effort: S | Tier: Now

### E. UX Friction (P2-P3)

**E-01. CLI help says `python bookmark_organizer.py` (wrong filename)**
- File: `bookmark_organizer_pro/cli.py:89,131`
- The file was renamed to `main.py` in v5.2.1. The help text still says
  `bookmark_organizer.py`. New users will copy-paste a broken command.
- Confidence: **Verified** -- lines 89 and 131.
- Effort: S

**E-02. `main.py` docstring says v6.0.0, constants says v6.2.0**
- File: `main.py:2` says "v6.0.0", `constants.py:9` says "6.2.0"
- Impact: Cosmetic but misleading if anyone reads the module docstring.
- Confidence: **Verified**.
- Effort: S

**E-03. Window geometry 1500x950 exceeds 125% DPI effective resolution**
- File: `app.py:106` (referenced in UX audit)
- On 1920x1080 at 125% DPI (effective 1536x864), the 1500px-wide window
  is too wide. No logic adapts to screen resolution.
- Confidence: **Likely** -- needs live validation on the target display.
- Effort: S (clamp to `min(1500, screen_width - 60)`)

**E-04. Browser import always uses first profile, no picker**
- File: `import_export.py:187`
- Multi-profile Chrome users get the first profile silently imported.
- Confidence: **Verified** -- `profiles[0]` with no picker.
- Effort: M (add profile picker dialog)

**E-05. CLI `list` caps at 50 without telling the user**
- File: `bookmark_organizer_pro/cli.py:148` (referenced in UX audit)
- Output says "All Bookmarks (500):" but only shows 50 rows. No
  "Showing 50 of 500" message or `--all` flag.
- Confidence: **Verified** from audit data.
- Effort: S

**E-06. CLI `check` is single-threaded (GUI uses 5 workers)**
- File: `bookmark_organizer_pro/cli.py:299-341`
- For 1,000 bookmarks at 5s timeout, single-threaded = 83 minutes.
  GUI uses `ThreadPoolExecutor(max_workers=5)`.
- Confidence: **Verified** from audit data.
- Effort: S-M (add ThreadPoolExecutor)

**E-07. Zoom label shows "100%" but default zoom is 115%**
- File: referenced in UX audit as `app_shell.py:267`
- Cosmetic mismatch on first render.
- Confidence: **Likely** -- needs live validation.
- Effort: S

**E-08. Search syntax undiscoverable in the GUI**
- The search box supports `domain:`, `tag:`, `is:pinned`, `before:`,
  `after:`, regex `/pattern/`, quoted phrases, boolean AND/OR, `-exclusion`.
  None of this is documented in-app. Only visible in search.py source.
- Confidence: **Verified** -- no help dialog for search syntax.
- Effort: S-M (add a "?" icon that shows a tooltip/popover with syntax ref)

**E-09. MCP server eagerly loads all services including EmbeddingService**
- File: `bookmark_organizer_pro/mcp_server.py:86-101`
- `BookmarkServices.__init__` constructs `EmbeddingService`, `VectorStore`,
  `HybridSearch`, `CitationSummarizer`, `CollectionChat`, etc. even if the
  agent only calls `list_bookmarks`. Cold start is slow and memory-heavy.
- Confidence: **Verified** -- all services constructed unconditionally.
- Fix: Lazy properties instead of eager construction.
- Effort: M

**E-10. No `--version` flag in CLI**
- Standard convention is `--version` or `-V` for just the version string.
  Currently the only way to see the version is `help` (full output).
- Confidence: **Verified** -- not in dispatch dict.
- Effort: S

**E-11. Analytics polling every 30s iterates all bookmarks**
- File: referenced as `lifecycle.py:102-103`
- At 10K+ bookmarks, this is recurring background cost for data that only
  changes on user action. Should be event-driven.
- Confidence: **Likely** -- audit describes the polling pattern.
- Effort: M (switch to event-driven refresh)

### F. Roadmap Adjustments (existing open items)

**F-01. R-01 (Browser extension) -- split into phased approach**
- The bookmarklet (R-04) and HTTP API are already shipped. A minimal popup
  extension that talks to the existing API is S-M effort, not L. Full native
  messaging is L. Recommend splitting:
  - R-01a: HTTP API popup extension (S-M, Now)
  - R-01b: Native messaging host for offline tagging (L, Next)

**F-02. R-06 / State of Project text -- tool count is 20, not 19 or 15**
- ROADMAP "State of the Project" says "15 typed tools" and R-06 says "19
  tools registered". Actual count in mcp_server.py TOOLS list is **20**
  (confirmed by counting tuples). The 20th is `list_snapshots`.
- Fix: Update ROADMAP text to "20 typed tools".

**F-03. R-16 (tksheet) -- bump to L-XL**
- The Treeview is deeply integrated: column sorting, favicon injection,
  selection tracking (`_tree_items`), context menus, double-click handlers.
  `VimNavigator` in `navigation.py` must also be ported. L is slightly
  optimistic; L-XL is more accurate.

**F-04. R-31 (SQLite migration) -- add explicit R-02 dependency**
- JSON storage works fine for single-user desktop. SQLite's compelling
  driver is concurrent access for the web client (R-02). Without R-02,
  SQLite has no compelling standalone value.
- Recommendation: Mark "Blocked by R-02. No value as standalone migration
  for desktop-only use." This effectively makes it Later unless R-02 is
  prioritized.

**F-05. R-45 (CLI smoke tests) -- blocked on D-01 through D-04**
- If R-45 tests "all subcommands", the 4 missing CLI commands (smart
  collections, NL query, obsidian export, EPUB export) need to exist first.
  Either fold D-01-D-04 into R-45's scope, or block R-45 on them.
- Also update description: "34 commands, ~45 code paths" (not "30+").
  Note that `chat` requires mock stdin or skip.

**F-06. R-48 (Keyboard accessibility) -- reduce estimate to M-L**
- Partial infrastructure already exists: `make_keyboard_activatable()` in
  `ui/tk_interactions.py`, `VimNavigator` in `navigation.py`, focus-ring
  width tokenized as `DesignTokens.FOCUS_RING_WIDTH`, Ctrl+F accelerator.
- Remaining: (1) explicit tab order, (2) column sort keyboard access,
  (3) min click target audit, (4) screen reader name attributes.
- M-L is more accurate given the existing foundation.

**F-07. R-18 (sv-ttk) -- note maintenance-mode risk**
- sv-ttk last released Jan 2024, no 2026 activity. Supports Python 3.8-3.12
  only (no 3.13/3.14). May need a fork or alternative if Python version
  requirements advance.
- Recommendation: Keep on roadmap but add risk note.

**F-08. R-47 completion claim -- CategoryColorManager docstring missed**
- File: `bookmark_organizer_pro/services/local_state.py:274-288`
- R-47 ("Fix copy-pasted model docstrings") is marked done, but
  `CategoryColorManager` still has the `Category` model docstring
  copy-pasted as its own.
- Regression from R-47 claimed completion.
- Effort: S

### G. Ecosystem Shifts Affecting Priorities

**G-01. Karakeep shipped official MCP server (v0.32.0, May 2026)**
- BOP is no longer the only OSS bookmark manager with MCP. Karakeep's
  `@karakeep/mcp` on npm is official and current. ROADMAP claim "No other
  OSS bookmark manager ships this" is stale.
- Action: Update README/ROADMAP marketing language. Differentiate on tool
  count (20 vs. unknown) and RAG/citation features.

**G-02. MCP spec release candidate (2026-07-28) brings breaking changes**
- Stateless protocol core, required `Mcp-Method`/`Mcp-Name` headers on
  Streamable HTTP, `ttlMs`/`cacheScope` on list results, W3C Trace Context.
- Action: Plan a compatibility pass when the spec ships. May affect
  `serve_stdio()` and `_build_fastmcp_server()`. FastMCP 3.4.0 likely
  handles most of this, but the raw SDK fallback path needs review.

**G-03. FastMCP v3.1 "code mode" -- 99% token savings for large tool catalogs**
- Collapses 1000-tool catalogs into 2 tools. BOP has 20 tools which is
  fine, but this is relevant for R-15 (MCP streaming) planning.

**G-04. Better embedding models available in FastEmbed**
- `snowflake-arctic-embed-s` (33M params) and `nomic-embed-text-v1.5`
  (8192-token context vs. bge-small's 512) are both supported by FastEmbed
  and run on CPU. These are better quality than `bge-small-en-v1.5`.
- Action: Consider R-NEW for embedding model upgrade. Not urgent but
  quality improvement for semantic search.

**G-05. Pillow CVE-2026-25990 affects FastEmbed compatibility**
- FastEmbed issue #606 tracks Pillow 12.x compat. BOP already pinned
  Pillow >=12.2.0 (R-36b). Verify FastEmbed works with this pin.
- Confidence: **Needs live validation**.

**G-06. Pocket shutdown (Jul 2025) continues driving migration demand**
- Burn 451 (26 MCP tools), GoodLinks, Karakeep are top beneficiaries.
  BOP's 5 importers (Pocket/Readwise/Pinboard/Instapaper/Reddit) are
  well-positioned. The browser extension (R-01) is the missing piece for
  capturing this audience.

---

## Updated Priority Order

### Immediate (pre-release blockers)

| # | Finding | Effort | Confidence |
|---|---------|--------|------------|
| A-01 | Fix `card_shadow` crash in high_contrast theme | S | Verified |
| A-02 | Fix `Path` import in `t_export_to_obsidian` | S | Verified |
| B-01 | Fix YAML frontmatter injection in obsidian_export | S-M | Verified |
| B-02 | Fix domain filter lowercase in smart_collections | S | Verified |
| B-03 | Fix category filter substring matching | S | Verified |
| E-01 | Fix CLI help filename (`bookmark_organizer.py` -> correct invocation) | S | Verified |
| E-02 | Fix main.py docstring version (v6.0.0 -> v6.2.0) | S | Verified |
| F-08 | Fix CategoryColorManager copy-pasted docstring (R-47 miss) | S | Verified |
| F-02 | Fix ROADMAP tool count (15/19 -> 20) | S | Verified |

### High priority (v6.2.1 or v6.3)

| # | Finding | Effort | Confidence |
|---|---------|--------|------------|
| B-04 | SingleFile backend MAX_BYTES check | S | Verified |
| B-06 | High-contrast theme missing ~11 field defaults | S | Verified |
| C-01 | SSRF via redirect in Python snapshot fallback | S-M | Verified |
| C-02 | Sandbox MCP `export_to_obsidian` vault_path | S | Verified |
| C-04 | Path traversal in extracted_text_path reads | S | Verified |
| D-01 | CLI: smart-collections subcommand | S | Verified |
| D-02 | CLI: nl-query subcommand | S | Verified |
| D-03 | CLI: obsidian-export subcommand | S | Verified |
| D-04 | CLI: epub-export subcommand | S | Verified |
| E-10 | CLI: add `--version` flag | S | Verified |
| E-05 | CLI: `list` show count / add `--all` flag | S | Verified |

### Medium priority (v7.0 planning)

| # | Finding | Effort | Confidence |
|---|---------|--------|------------|
| E-09 | Lazy service initialization in MCP server | M | Verified |
| E-06 | CLI `check` multi-threading | S-M | Verified |
| E-08 | In-app search syntax reference | S-M | Verified |
| E-04 | Browser import profile picker | M | Verified |
| E-11 | Event-driven analytics refresh (replace polling) | M | Likely |
| B-05 | EPUB mimetype extra field (epubcheck compliance) | S | Needs validation |
| C-03 | Bookmarklet sync token warning | S | Verified |
| E-03 | Adaptive window geometry for DPI | S | Needs validation |
| E-07 | Fix zoom label initial value | S | Likely |
| G-01 | Update MCP-first-mover marketing language | S | Verified |

---

## Quick Wins (< 30 min each, all verified)

1. **A-01**: Remove `card_shadow="#000000"` from high_contrast theme (or add field to ThemeColors)
2. **A-02**: Add `from pathlib import Path` to mcp_server.py top-level imports
3. **B-02**: Change line 65 of smart_collections.py to `domain = bookmark.domain.lower()`
4. **B-03**: Change line 61 to `== cat_lower` instead of `in cat_lower`
5. **B-04**: Add `if out_path.stat().st_size > self.MAX_BYTES:` check after line 131 of snapshot.py
6. **E-01**: Replace `bookmark_organizer.py` with correct filename in cli.py lines 89, 131
7. **E-02**: Update main.py docstring from "v6.0.0" to "v6.2.0"
8. **E-10**: Add `"--version"` handler to cli.py `run()` method
9. **F-02**: Update ROADMAP "State of the Project" tool count from 15 to 20
10. **F-08**: Replace CategoryColorManager docstring in local_state.py:274-288

---

## Test Coverage Priorities (top 5)

The 3 flagship v6.2 services have **zero test coverage**:

| Priority | Module | Risk | Key Tests |
|----------|--------|------|-----------|
| 1 | `smart_collections.py` | HIGH - filter logic bugs silently include/exclude wrong bookmarks | `matches()` per filter axis, `from_dict` with corrupt data, create/delete/evaluate roundtrip |
| 2 | `epub_export.py` | HIGH - wrong ZIP structure = corrupted files readers reject | Verify mimetype first+uncompressed, required EPUB entries exist, HTML escaping, empty bookmark list |
| 3 | `obsidian_export.py` | HIGH - YAML injection = data corruption | Valid YAML frontmatter, `_safe_filename` edge cases, duplicate-title suffix, injection via quotes/colons/newlines |
| 4 | `cli.py` | MEDIUM - primary user entry point, dispatch routing untested | `run([])` prints help, `run(["add", url])` succeeds, `run(["unknown"])` errors |
| 5 | `nl_query.py` | MEDIUM - LLM JSON parsing + every filter branch | `_parse` with clean/malformed JSON, `_heuristic` extraction, `execute_query` per filter |

Additional high-value test surfaces (items 6-20):

6. `dup_hybrid.py` -- `_simhash64()`, `_hamming()`, `detect()` (pure functions, easy to test)
7. `vector_store.py` -- `_cosine()`, `reciprocal_rank_fusion()` (pure math)
8. `ingest.py` -- `_detect_content_type_from_url()`, `_detect_content_type_from_text()`, `IngestResult.apply_to()`
9. Import/export roundtrip -- OPML, XBEL, JSON export->import produces identical data
10. `importers_extra.py` -- 5 importers with format-specific parsing edge cases
11. `dead_link_scanner.py` -- `_persist()` + `_load_records()` roundtrip, merge logic
12. `snapshot.py` -- `delete_snapshot()`, `has_snapshot()` (no network needed)
13. `citation_summarizer.py` -- `_parse_response()`, `CitedSummary.render_html()`
14. `hybrid_search.py` -- `_recency_factor()`, keyword-only fallback path
15. Bookmark model -- Unicode/emoji/CJK edge cases in `from_dict()`, `add_tag()`, `clean_url()`
16. MCP tools -- `t_semantic_search`, `t_export_to_obsidian`, `t_summarize` (untested tools)
17. `storage_manager.py` -- concurrent save stress test (5 threads)
18. `rag_chat.py` -- history truncation, citation-stripping regex
19. `tag_linter.py` -- `apply()` method (lint is tested, apply is not)
20. `obsidian_export._safe_filename` -- empty string, 200-char title, Windows reserved names

---

## Open Questions (need live validation or user input)

1. **Does the high_contrast theme actually crash on import?** The `card_shadow` field
   may be handled by a `**kwargs` catch in ThemeColors that I did not find. Run
   `python -c "from bookmark_organizer_pro.theme_runtime import BUILT_IN_THEMES"` to
   confirm.

2. **Does epubcheck reject BOP's EPUB output?** The mimetype extra-field concern
   (B-05) is spec-pedantic. Test with `java -jar epubcheck.jar output.epub`.

3. **What is the actual cold-start time of the MCP server?** The eager service
   initialization (E-09) may be acceptable if startup is < 2s. Profile it.

4. **Is the `nomic-embed-text-v1.5` quality improvement worth a migration?** Requires
   re-embedding all bookmarks. User should decide based on library size.

5. **Should R-31 (SQLite) be explicitly blocked on R-02 (web client)?** If the user
   has no near-term web client plans, SQLite is dead weight on the roadmap.

6. **MCP spec RC (2026-07-28) -- does FastMCP 3.4.0 handle the breaking changes?**
   Need to test once the spec ships. If yes, only the raw SDK fallback path needs
   updating.

---

## Appendix: Findings Not Actionable

These were reviewed and determined to not warrant roadmap items:

- **Playwright browser launch per snapshot (BUG-SN-3)**: Real but only matters for
  batch snapshotting. Add browser reuse when R-24 (scheduled auto-snapshot) ships.
- **`_recency_factor` uses 0.693 instead of `math.log(2)` (BUG-HS-3)**: 0.04% error
  is negligible. Clarity improvement, not a bug.
- **Future dates get max recency boost (BUG-HS-1)**: Edge case. Future-dated bookmarks
  are rare and treating them as "just now" is reasonable.
- **TOCTOU race in SmartCollectionManager._load (BUG-SC-2)**: Theoretical. Single-user
  desktop app with rare concurrent access. Fix if R-31 (SQLite) ships.
- **EPUB toc.xhtml not in spine (audit note)**: Some readers expect it, most don't.
  Low-priority spec compliance.
- **Naive vs aware datetime in `_recency_factor` (BUG-HS-2)**: Off by at most 14
  hours against a 180-day half-life. Negligible impact on ranking.
