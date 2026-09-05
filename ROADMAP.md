# Roadmap: Bookmark Organizer Pro

Actionable incomplete work only. Historical and completed material belongs in `CHANGELOG.md`; blocked work remains in `Roadmap_Blocked.md`.

## Research-Driven Additions

### P1

- [ ] P1: R-159: Remove confirmation from the restorable extension queue clear
  Why: Popup and side panel block an undoable clear behind `globalThis.confirm` even though the cleared journal can be restored.
  Evidence: `browser-extension/popup.js:110`; `browser-extension/sidepanel.js:150`; `browser-extension/shared.js:749`; `tests/test_packaging.py:500`
  Touches: extension popup, side panel, shared journal API, locale strings, extension and packaging tests
  Acceptance: Clear acts immediately, reports the count, and exposes Restore in the same panel; restore preserves entry order and retry metadata after worker restart; no confirmation API or `confirmed` flag remains; popup and side-panel parity tests pass.
  Complexity: S

- [ ] P1: R-161: Add revision-bound paragraph paging for MCP extracted content
  Why: `get_extracted_text` can return an entire article or transcript in one tool response, with no way to resume safely after recapture.
  Evidence: `bookmark_organizer_pro/mcp_server.py:762`; Karakeep 0.33.1 https://github.com/karakeep-app/karakeep/releases/tag/v0.33.1
  Touches: reader text service, MCP registry and annotations, MCP auth scopes, tool tests, generated product contracts
  Acceptance: A `get_extracted_text_page` tool returns `content`, `next_cursor`, `total_chars`, and `source_sha256`; chunks honor a bounded `max_chars` and snap to paragraph boundaries; cursors are validated against bookmark ID and source digest; changed content rejects an old cursor; the legacy tool handles small files and returns a clear paging instruction above its documented ceiling.
  Complexity: M

- [ ] P1: R-162: Activate SQLite migration safely from the desktop
  Why: The GUI creates a database but leaves users to set an environment variable or rename files manually before it is used.
  Evidence: `bookmark_organizer_pro/app_mixins/tools.py:1525`; JSON performance guidance in `README.md:692`; recovery primitives in `bookmark_organizer_pro/services/recovery_bundle.py`
  Touches: desktop migration flow, settings store, storage backend resolution, SQLite migration, startup recovery, tests and README
  Acceptance: Migration writes to a temporary database, verifies count, revision, integrity, and a canonical-record digest, atomically installs it, persists the next-launch backend choice, and confirms the restarted manager reads the same library; any failure keeps JSON active and preserves both sources; an existing destination is backed up or replaced through the same flow without manual renaming.
  Complexity: M

- [ ] P1: R-163: Capture browser selections as first-class resilient highlights
  Why: Popup and context-menu selections are truncated into bookmark notes while the reader already supports exact, context, position, digest, and re-anchoring fields.
  Evidence: `browser-extension/popup.js:37`; `browser-extension/background.js:140`; `browser-extension/shared.js:388`; `bookmark_organizer_pro/services/reader_annotations.py:30`; https://github.com/obsidianmd/obsidian-clipper
  Touches: extension capture scripts and journal schema, loopback API, ingest service, reader annotation store, highlight workspace, extension and API tests
  Acceptance: Selection capture records exact text plus available prefix, suffix, position, and page URL; the API creates or reuses the bookmark and adds one idempotent highlight without overwriting notes or tags; queue replay cannot duplicate it; captures without offsets remain re-anchorable `unverified` highlights; popup and context-menu paths behave consistently.
  Complexity: M

- [ ] P1: R-164: Add W3C Web Annotation JSON-LD interchange and public Text Fragment links
  Why: The internal selector model already maps to the standard, but current import and export accept only the private annotation schema.
  Evidence: `bookmark_organizer_pro/services/reader_annotations.py:961` and `:1205`; https://www.w3.org/TR/annotation-model/; https://wicg.github.io/scroll-to-text-fragment/; https://web.hypothes.is/blog/hypothesis-for-web-developers/
  Touches: annotation import and export adapters, CLI and workspace format selectors, source-link builder, schema fixtures, round-trip tests
  Acceptance: Native v2 remains the lossless default; JSON-LD export emits valid Annotation, TextualBody, TextQuoteSelector, and TextPositionSelector records; conservative import preserves unknown fields in provenance or reports them; notes and tags round-trip; HTTP and HTTPS highlights can copy a correctly encoded text-fragment link; conformance fixtures round-trip without duplicate annotations.
  Complexity: M

- [ ] P1: R-165: Turn dead-link results into a persistent remediation workspace after trash lands
  Why: The desktop only prints a bounded report, so users cannot dismiss false positives, replace URLs, retry selected items, or review an archived copy before removal. R-152 must land first.
  Evidence: `bookmark_organizer_pro/app_mixins/tools.py:1267`; `bookmark_organizer_pro/services/dead_link_scanner.py:449`; https://support.start.me/en/articles/9182823-broken-link-checker-pro; https://github.com/sissbruecker/linkding/issues/68
  Touches: dead-link record schema and migration, scanner, desktop workspace, bookmark edit and trash commands, CLI and MCP list output, tests
  Acceptance: Each record keeps check history, last verdict, manual-good state, dismissal deadline, and optional replacement URL; the workspace supports Retry, Mark good, Edit URL, Open domain root, Open archived copy, and Move to trash without adding a new egress provider; transient failures do not reappear before their retry policy; batch changes are previewed and recoverable through R-152; 200% scaling, theme, focus-order, and localization checks pass.
  Complexity: M

### P2

- [ ] P2: R-166: Add archive storage observability and recovery-backed cleanup
  Why: Snapshot size is recorded, but aggregate archive size has no production caller and users cannot identify costly captures before disk pressure becomes a failure.
  Evidence: `bookmark_organizer_pro/models/bookmark.py:87`; `bookmark_organizer_pro/services/web_tools.py:483`; Karakeep large-archive fix https://github.com/karakeep-app/karakeep/releases/tag/v0.33.2; exact largest-item demand needs live validation from https://www.reddit.com/r/selfhosted/comments/1nq9drl/linkwarden_v213_opensource_collaborative_bookmark/
  Touches: snapshot manifests and history, processing timeline, analytics or tools workspace, cleanup preview, recovery bundle, settings, tests
  Acceptance: The desktop reports total bytes, item count, median, p95, largest captures, MIME family, and backend from verified manifests; users can preview recapture-without-media or local-snapshot removal and see affected bytes before applying; destructive removal first creates and verifies a recovery package containing the exact snapshot, history, extraction, and transcript artifacts, aborting if recovery fails; no action runs automatically or relies on a bookmark-only safepoint.
  Complexity: M
  Note 2026-09-04: The live-validation caveat on this item is settled. Disk growth is an open question users ask and do not get answered ("What's the disk space usage like, average per-day/week additional storage in your usage?", https://news.ycombinator.com/item?id=49351802), and archive size is what breaks self-hosted setups (https://news.ycombinator.com/item?id=44597668). Build it.

- [ ] P2: R-167: Add multilingual FTS analyzer profiles with versioned rebuilds
  Why: Current FTS config exposes English-style stop words and ASCII folding but not the ICU, Chinese, Japanese, or n-gram tokenizers available in the pinned search engine.
  Evidence: `bookmark_organizer_pro/services/vector_store.py:665`; current tokenizer API https://lancedb.github.io/lancedb/python/python/
  Touches: vector-store settings and manifest, FTS creation and query path, index rebuild UI and CLI, diagnostics, language fixtures
  Acceptance: Auto, Latin, ICU, Chinese, Japanese, and n-gram profiles map to documented LanceDB analyzers; profile and analyzer version are stored in the index contract; a change builds a new generation and switches only after validation; index and query analyzers match; model-backed profiles report unavailable until their local model exists and never download during indexing or query; accented Latin, CJK, mixed-script URL, and code-identifier fixtures prove recall without regressing English.
  Complexity: L

- [ ] P2: R-168: Expose tag hygiene and organization suggestions through separate read-only MCP tools
  Why: Deterministic tag linting and category-rule suggestions exist in desktop and CLI services, but MCP agents cannot inspect either result safely.
  Evidence: `bookmark_organizer_pro/cli.py:783` and `:1501`; missing tools in `bookmark_organizer_pro/mcp_server.py:1499`; https://help.raindrop.io/integrations/mcp
  Touches: tag-linter and rule-suggestion adapters, MCP registry, read scopes and annotations, pagination, product contracts, tests
  Acceptance: `audit_tags` returns bounded groups with variant tags, canonical merge target, affected bookmark count, and deterministic reason; `suggest_organization` returns bookmark ID, current category, proposed category, matching rule evidence, and confidence; neither tool mutates data or calls a model; each matches its CLI service on the same fixture; auth metadata marks both read-only.
  Complexity: M

- [ ] P2: R-169: Give smart collections desktop CRUD, preview, and apply workflows
  Why: The service and CLI support versioned collections, but the desktop only displays a report and tells users to use the CLI.
  Evidence: `bookmark_organizer_pro/app_mixins/tools.py:1206`; `bookmark_organizer_pro/cli.py`; `bookmark_organizer_pro/services/smart_collections.py`
  Touches: smart-collection service, desktop workspace, search filter application, atomic persistence, accessibility and visual tests
  Acceptance: Desktop users can create, edit, delete, preview result counts, and apply a saved collection to the main table; invalid filters fail before atomic persistence; empty, error, dark, light, 200% scaling, focus-order, and localized-copy states are tested.
  Complexity: M

- [ ] P2: R-170: Persist saved searches and recent-query history
  Why: `SearchEngine` implements CRUD and migration methods, but production callers never load, save, or manage them, so history disappears on restart.
  Evidence: `bookmark_organizer_pro/search.py:656`; no production call sites found outside tests on 2026-08-23
  Touches: search engine, atomic settings or dedicated store, search bar and command palette, saved-search management UI, recovery bundle, tests
  Acceptance: Named searches and a bounded recent-history list survive restart through an atomic versioned store; users can run, rename, reorder, and delete saved searches; malformed or legacy data fails closed with recovery reporting; recovery bundles include the store; persistence never records private transient query text when history is disabled.
  Complexity: M

- [ ] P2: R-171: Detect Reader View suitability before presenting extraction as successful
  Why: The current workflow can offer Reader View for content that yields empty or structurally unusable extraction, while Karakeep now records a suitability result.
  Evidence: extraction and reader paths in `bookmark_organizer_pro/services/ingest.py`, `bookmark_organizer_pro/services/reader_annotations.py`, and `bookmark_organizer_pro/ui/reader_view.py`; https://github.com/karakeep-app/karakeep/releases/tag/v0.33.1
  Touches: extraction result schema, processing timeline, reader launch state, repair workflow, diagnostics, tests
  Acceptance: Extraction records a bounded reasoned state of suitable, marginal, unsuitable, or failed using local signals; Reader View distinguishes those states and offers original page, snapshot, or extraction repair without claiming success; recapture can change the verdict; representative article, index, login, media, and empty fixtures are deterministic.
  Complexity: M

- [ ] P2: R-172: Correct architecture and product documentation against live composition
  Why: Architecture docs still call thin `main.py` the large legacy UI entry point, and several product counts and surface claims have drifted.
  Evidence: `docs/ARCHITECTURE.md:4`; `main.py:10`; live composition in `bookmark_organizer_pro/app.py`; current counts in `README.md` and `CLAUDE.md`
  Touches: `docs/ARCHITECTURE.md`, `README.md`, `CLAUDE.md`, `main.py`, documentation contract tests
  Acceptance: Documentation names the 14-mixin coordinator, current storage and service boundaries, actual large-file seams, supported list view, six AI providers, and the real quick-add behavior; product counts come from existing contract sources; a stale-claim test covers view modes, provider names, mixin count, and command and tool counts.
  Complexity: S
  Note 2026-09-04: Sequence this after R-191, since removing the dead subsystems changes the service counts and the module inventory this item is meant to make accurate. The README troubleshooting entry for high CPU on large imports is a symptom of R-179 and should be revisited once that lands rather than restated.

- [ ] P2: R-173: Extract named domain modules from CLI, MCP, and desktop tools
  Why: Three large dispatch files mix unrelated domains, making cross-surface outcome contracts hard to compare and test.
  Evidence: `bookmark_organizer_pro/cli.py`; `bookmark_organizer_pro/mcp_server.py`; `bookmark_organizer_pro/app_mixins/tools.py`; recurring cross-surface fixes in commit history
  Touches: new `bookmark_organizer_pro/cli_commands/` and `bookmark_organizer_pro/mcp_tools/` packages, `bookmark_organizer_pro/app_mixins/tools_data.py`, `bookmark_organizer_pro/app_mixins/tools_maintenance.py`, `bookmark_organizer_pro/app_mixins/tools_research.py`, compatibility facades, packaging contracts
  Acceptance: Migration and import handlers, maintenance handlers, and reader and export handlers move from `cli.py` into named domain modules; library, reader, and maintenance tool specs and handlers move from `mcp_server.py` while transport stays there; data, maintenance, and research desktop actions move from `tools.py` into the named mixins; each original file shrinks by at least 35%, no extracted module exceeds 800 lines, imports remain acyclic, public entry points and generated schemas stay identical, import time does not regress by more than 10%, and the full local gates pass.
  Complexity: L

## Research-Driven Additions (2026-09-04)

### P1

- [ ] P1: R-180: Bound and cheapen the table population path
  Why: One refresh takes four full snapshots of the library, filters it with list comprehensions, sorts it recomputing the key per comparison, then builds a row object with a nested six-key dict, four truncations, and a favicon lookup for every record with no cap. In accessibility mode it issues one Tcl insert per row, which presents as a hung application.
  Evidence: `bookmark_organizer_pro/app_mixins/bookmarks.py:105`, `:151`, `:159` and `bookmark_organizer_pro/app_mixins/filters.py:233` each call `get_all_bookmarks()`, which returns a fresh list from `_iter_snapshot()` (`managers/bookmarks.py:813-815`); sort at `app_mixins/bookmarks.py:149`; `_populate_list_view` at `:234-334` with the row spec at `:288-297`, favicon lookup at `:313`, and the per-row insert fallback at `:319-330`; no paging or row limit exists in `bookmarks.py`, `filters.py`, or `ui/treeview.py`
  Touches: `bookmark_organizer_pro/app_mixins/bookmarks.py`, `bookmark_organizer_pro/app_mixins/filters.py`, `bookmark_organizer_pro/ui/treeview.py`, `benchmarks/bench_core.py`, `tests/test_core.py`
  Acceptance: A refresh takes exactly one library snapshot and derives filter counts, totals, and the visible set from it, asserted by a test that counts `get_all_bookmarks()` calls; the sort key is computed once per record per refresh; row specs are built only for rows the view can present, with the remainder loaded on demand and the full count still reported accurately in the summary; the accessibility fallback batches its inserts; the new benchmark case from R-178 covers the refresh and its budget is proved by reintroducing a second full scan.
  Note 2026-09-05: R-178 shipped the growth-class thresholds and a `duplicate_scan` case but NOT the table-population case, which needs an offscreen Tk root in a benchmark worker and was split out rather than half-built. Adding it belongs to this item. `benchmarks/bench_core.py` now takes a growth class per case in `CASE_GROWTH`, so a new case must declare one.
  Note 2026-09-05: The snapshot and sort halves are done. `_refresh_bookmark_list` now takes exactly one snapshot and derives the category filter, filter counts, totals and the visible set from it, and the title sort key is computed once per record instead of per comparison. `tests/test_maintenance_flows.py::TestBookmarkTableRefresh` counts the snapshots and is proved by reintroducing a second scan. STILL OPEN: `_populate_list_view` still builds a row spec, four truncations and a favicon lookup for every record with no cap, and the accessibility fallback still issues one Tcl insert per row. Those need a load-more contract that keeps the summary count accurate, which is the remaining work here.
  Complexity: L

- [ ] P1: R-181: Harden the local credential surface
  Why: Failed authentication currently erases its own evidence, is never throttled, and cannot be locked out. The 500-event audit cap means 500 bad requests both delete the record of the attack and trigger 500 disk rewrites, while the credential that grants read, write, and extension scope has no expiry and no rotation path anywhere in the product.
  Evidence: `bookmark_organizer_pro/services/mcp_auth.py:490-491` `del audit[:-MAX_AUDIT_EVENTS]` on every authorize call including failures, rewriting the token file at `:758-760`; `:701` increments `invalid_attempts` with nothing enforcing on it; `import_legacy_rest_token` at `:560-578` creates the credential with no `expires_at` while `create_token:537`, `revoke_token:832`, and `list_tokens:945` have no caller; `bookmark_organizer_pro/services/api.py` has no 429 path, window, or counter, `_check_auth` at `:557` answers immediately at `:591`, `_check_browser_origin` at `:596-605` allows a missing `Origin`, and there is no Host-header check unlike `mcp_server.py:610-614`
  Touches: `bookmark_organizer_pro/services/mcp_auth.py`, `bookmark_organizer_pro/services/api.py`, `bookmark_organizer_pro/cli.py`, `bookmark_organizer_pro/ui/management_dialogs.py`, locale strings, `tests/test_services.py`
  Acceptance: Failed-authentication events are recorded in a separate bounded ring that success events cannot evict, and a burst of failures is written once rather than per attempt; repeated failures from one peer are throttled with increasing delay and answered 429 past a documented ceiling, with success resetting the counter and throttling scoped per peer so one bad client cannot lock out the extension; a failure burst raises a visible desktop notice naming the count and last attempt; the REST credential can be rotated and revoked from both the desktop and the CLI, and rotation invalidates the old value immediately; `api.py` validates the Host header and rejects a browser request with no `Origin` on mutating routes; tests cover the ladder, the reset, the ring isolation, rotation, and the rebinding-shaped request.
  Complexity: M

- [ ] P1: R-185: Route plurals, dates, and sorting through the locale
  Why: A parallel English-only pluralizer is called from more than fifteen desktop sites and its output is never wrapped for translation, so the POT gate cannot see it and those strings can never be translated. Dates are always formatted in English and the table sorts by codepoint order, so accented, German, and CJK titles land out of position.
  Evidence: `bookmark_organizer_pro/text_format.py:14-32` `pluralize()` called from `bookmark_organizer_pro/app_mixins/tools.py:1028`, `:1122`, `:1200`, `:1241` and others with no `_()` wrapper, while `bookmark_organizer_pro/i18n.py` implements real `ngettext` and `npgettext`; `locale.setlocale()` is never called so `strftime("%b %d, %Y")` at `bookmark_organizer_pro/app_mixins/bookmarks.py:33` is always English; sorting uses NFKC plus casefold codepoint order in `bookmark_organizer_pro/ui/treeview.py` with no `locale.strxfrm`; the same class of defect is recorded in the 2026-08-22 working note about nesting a Python pluralizer inside a translator call; https://github.com/linkwarden/linkwarden/releases/tag/v2.16.2 shows sorting draws real complaints
  Touches: `bookmark_organizer_pro/text_format.py`, `bookmark_organizer_pro/i18n.py`, `bookmark_organizer_pro/app_mixins/tools.py`, `bookmark_organizer_pro/app_mixins/bookmarks.py`, `bookmark_organizer_pro/ui/treeview.py`, `locale/bop.pot`, `tests/test_i18n.py`
  Acceptance: Every user-facing plural reaches the catalogue through `format_plural` or `ngettext`, replaced from an explicit verified table rather than a regex sweep because a mechanical rewrite of this copy has broken the build before; a gate fails if `text_format.pluralize()` is called from a user-facing sink; dates format through a locale-aware helper with an explicit fallback when the locale is unavailable; one shared collation key drives the initial refresh and every column sort, computed once per record in line with R-180; a test asserts a fixture of `Étude`, `Etude`, `Zebra`, `étude`, a German sharp-s title, and a CJK title orders as specified; the POT regenerates and its freshness check passes.
  Complexity: M

- [ ] P1: R-187: Close the native export and round-trip gaps
  Why: Neither native export can reproduce the library it came from. Netscape HTML flattens the category tree and drops notes, dates, and every state flag; native JSON writes category and tag maps the importer never reads; and highlights are exported by no native format at all, which is the part users say they most fear losing when they move tools.
  Evidence: `bookmark_organizer_pro/managers/bookmarks.py:1501-1540` writes one flat `<H3>` per category with no `<DD>` and no `LAST_MODIFIED`, while nesting is real at `bookmark_organizer_pro/models/category.py:32`; native JSON writes `categories` and `tags` maps at `:1548-1551` that the importer at `:747` never reads; annotations live in `bookmark_organizer_pro/services/reader_annotations.py` and no native export includes them; `tests/test_core.py:80` covers `to_dict`/`from_dict` only and `:1905` exports HTML without reimporting; the `TAGS` plus `<DD>` pair is the format's only lossless path for tags and notes (https://learn.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/platform-apis/aa753582(v=vs.85)); "I just hope that I can export and migrate all my snapshot data as well" at https://news.ycombinator.com/item?id=45047572
  Touches: `bookmark_organizer_pro/managers/bookmarks.py`, `bookmark_organizer_pro/importers.py`, `bookmark_organizer_pro/services/reader_annotations.py`, `bookmark_organizer_pro/ui/workflow_selective_export.py`, `tests/test_core.py`
  Acceptance: Netscape export emits nested `<DL>` blocks matching the category tree, a `<DD>` element for notes, and `LAST_MODIFIED` where known, and the importer reads all three back; native JSON export round-trips category colors, empty categories, tag metadata, and every state flag, with the importer reading the maps the exporter writes; highlights and reading progress are included in the native JSON export and reimported without duplicating existing annotations; a round-trip test exports a fixture covering nested categories, notes, tags, unicode titles, a pre-1970 `ADD_DATE`, highlights, and read state, reimports into an empty library, and asserts field-level equality; the test is proved by flattening one nesting level in the writer and watching it fail; third-party importers are unchanged. Depends on R-176 so both surfaces already share one parser.
  Complexity: M

- [ ] P1: R-189: Validate the build against Tk 9.0.4 and Python 3.14 and retire 3.10
  Why: The supported matrix lists a runtime that goes end of life on 2026-10-31 and omits the current stable line, and Tk changed underneath Windows CPython in a way that renames the DLLs the frozen build collects.
  Evidence: `packaging/release_manifest.json` lists `3.10`, `3.12`, `3.13` as unlocked supported environments with the verified lock on 3.11; Python 3.10 end of life 2026-10-31 (https://devguide.python.org/versions/); CPython `PCbuild/tcltk.props` on the 3.14 branch sets `TclVersion` to 9.0.4.0, first shipped in 3.14.7 on 2026-08-05, with DLLs renamed to `tcl90.dll` and `tcl9tk90.dll` plus a new `libtommath.dll` and the Tk script library embedded in the DLL (https://github.com/python/cpython/issues/124111); Nuitka 4.2 on 2026-08-27 adds official 3.14 support
  Touches: `pyproject.toml` `requires-python`, `packaging/release_manifest.json`, `packaging/bookmark_organizer.spec`, `packaging/nuitka_build.py`, `scripts/build_release.py`, `scripts/release_artifact_smoke.py`, README support matrix, `tests/test_packaging.py`
  Acceptance: The full suite, the ruff gate, and the offscreen desktop smoke pass on a 3.14.7 or later interpreter; a frozen artifact built against that interpreter launches and reports its version through the release artifact smoke, proving the Tk 9 DLL set is collected; `requires-python` and the supported-environment list drop 3.10 and add 3.14; a test asserts no supported environment is past its upstream end-of-life date; if the Tk 9 frozen build fails, 3.14 stays out of the matrix and the exact failure is recorded in `Roadmap_Blocked.md` rather than silently omitted.
  Complexity: M

### P2

- [ ] P2: R-191: Delete the dead subsystems and the hooks that do nothing
  Why: Roughly 1,600 lines of service code and five declared extension points have no caller, which misleads every future reader about what the product does. One of them is worse than dead weight: the dashboard renders a per-bookmark version history that nothing ever writes to, and an AI cost report that would always show zeros.
  Evidence: `bookmark_organizer_pro/services/web_tools.py` is entirely unreferenced at 1,045 lines (`WaybackMachine:52`, `LocalArchiver:174`, `AISummarizer:511`, `ScreenshotCapture:784`, `PDFExporter:905`), superseded by `services/snapshot.py`; `services/organization.py` `CollectionManager:231`, `FrequentlyUsedManager:398`, `SettingsProfileManager:470` unreferenced and `SmartTagManager:87` touched only for a constant at `services/organization_rules.py:478-480`; `services/ai_tools.py:695` `AICostTracker` never instantiated so `record_usage:798` never fires; `services/local_state.py` `VersionHistory:727` never written, `CategoryColorManager:814` and `FontManager:886` unreferenced; smaller dead entry points at `flows.remove_step:178`, `flows.project_onto:230`, `smart_collections.evaluate_all:424`, `organization_rules.enable_rule:625` and `disable_rule:628`, `nl_query.heuristic_parse:119`, `ollama_manager.delete_model:227` and `list_local_models:242`, `extraction_repairs.preview_repair:249`, `reader_annotations.parse_annotation_export:1214`, `updates.is_newer_version:53`, `local_state.redact_text:103`; empty hooks at `commands.py:19`, `app_mixins/app_shell.py:41`, `app_mixins/selection.py:62`, `app_mixins/lifecycle.py:129`
  Touches: `bookmark_organizer_pro/services/web_tools.py`, `bookmark_organizer_pro/services/organization.py`, `bookmark_organizer_pro/services/ai_tools.py`, `bookmark_organizer_pro/services/local_state.py`, `bookmark_organizer_pro/services/__init__.py`, `bookmark_organizer_pro/commands.py`, `bookmark_organizer_pro/app_mixins/`, `packaging/product_claims.json`, README and `docs/ARCHITECTURE.md`, affected tests
  Acceptance: Each item is either removed with its tests, barrel exports, and documentation claims in one commit, or wired to a real user path with a test that reaches it through that path; anything surfacing data that is never written (version history, AI cost report) is removed from the dashboard in the same change so no view promises an always-empty record; a reachability check runs in the suite and fails on a new public service entry point with no non-test caller, proved by adding an unreferenced function and watching it fail; product-claim counts and README service counts move together.
  Complexity: M

- [ ] P2: R-192: Finish or withdraw the desktop spaced-repetition surface
  Why: The dashboard shows a due-review count that the desktop offers no way to act on. Recording a review is reachable only from the CLI and MCP, and the pace and weight controls have no caller anywhere, so a feature the dashboard advertises cannot be used in the application.
  Evidence: `bookmark_organizer_pro/app_mixins/dashboard.py:748` renders the due count; `bookmark_organizer_pro/services/reader_annotations.py:894` `record_review` is called only from `bookmark_organizer_pro/cli.py:2289` and `bookmark_organizer_pro/mcp_server.py:1110`; `set_review_pace:863` and `set_source_weight:879` have no caller; the same pattern applies to RSS feeds (`cli.py:1636`, `:1822`), Zotero interop (`:2829`, `:2844`), EPUB export (`:2757`), and extraction repairs (`:675`), all CLI-only
  Touches: `bookmark_organizer_pro/app_mixins/dashboard.py`, `bookmark_organizer_pro/ui/reader_view.py`, a review workspace under `bookmark_organizer_pro/ui/`, `bookmark_organizer_pro/services/reader_annotations.py`, locale strings, `tests/test_accessibility_contracts.py`
  Acceptance: The due count opens a review surface that presents due highlights, records a grade through `record_review`, and advances the schedule, or the count is removed from the dashboard; review pace and source weight are settable from that surface or deleted; the surface passes the modal dialog contract from R-184 and the theme, focus-order, 200% scaling, and localized-copy checks the existing workspaces pass; the CLI-only features named above are each given a desktop entry point or documented in the README as command-line only, so no capability is silently invisible.
  Complexity: M

- [ ] P2: R-193: Give XBEL a real surface or delete it
  Why: XBEL import and export are implemented, exported from the package facade, and covered by a round-trip test, but no GUI, CLI, MCP, or REST path calls either, so a documented interchange format is unreachable. This repeats the dead-feature pattern the working notes already record.
  Evidence: `bookmark_organizer_pro/io_formats/xbel.py` implements both directions; exported at `bookmark_organizer_pro/__init__.py:107` and `:216`; round-trip test at `tests/test_core.py:924`; no other call site across `bookmark_organizer_pro/` or `scripts/` on 2026-09-04; XBEL is the native format for KDE and GNOME `recently-used.xbel` (https://xbel.sourceforge.net/)
  Touches: `bookmark_organizer_pro/cli.py`, `bookmark_organizer_pro/app_mixins/import_export.py`, `bookmark_organizer_pro/ui/import_center.py`, drag-and-drop routing, `packaging/product_claims.json`, README format list, `tests/test_cli.py`
  Acceptance: XBEL import and export are reachable from the CLI and from the Import Center and export menu with the same duplicate, summary, and next-action handling as other file formats, and `.xbel` drops route correctly; nesting, dates, and descriptions survive a round trip through a real user path rather than a direct handler call; product-contract counts and README format lists move together. If the decision is to delete, the module, facade export, tests, and every documentation mention go in one commit.
  Complexity: S

- [ ] P2: R-194: Add profile-path importers for Vivaldi, Opera, and Zen
  Why: Three widely used Chromium and Firefox forks store bookmarks in the exact formats the browser profile importer already reads, so supporting them is a table of profile paths rather than new parsing work, and browser migration is where users report the most loss.
  Evidence: `bookmark_organizer_pro/importers.py:366-388` `BrowserProfileImporter` already enumerates profile locations per browser and parses the Chromium JSON and Firefox formats; large-collection browser migration failures at https://news.ycombinator.com/item?id=41814394; destructive Firefox import behavior at https://news.ycombinator.com/item?id=45047572
  Touches: `bookmark_organizer_pro/importers.py`, `bookmark_organizer_pro/ui/import_center.py`, `bookmark_organizer_pro/cli.py`, `packaging/product_claims.json`, README importer list, `tests/test_services.py`
  Acceptance: Vivaldi, Opera, and Zen appear as sources in the Import Center and the CLI with correct default profile paths for Windows, and each detects multiple profiles rather than only the default; a missing browser reports a clear not-installed state rather than an error; folder structure, tags where present, and dates import on the same terms as the existing Chromium and Firefox paths; importer counts in product claims and the README move together; tests cover the path resolution and a fixture profile per browser.
  Complexity: S

- [ ] P2: R-195: Reject Windows reserved device names in generated export paths
  Why: Export filename sanitization caps length and strips illegal characters but does not handle reserved device names, so a bookmark titled `CON`, `NUL`, or `LPT1` raises `OSError` partway through an export and leaves the output incomplete.
  Evidence: `bookmark_organizer_pro/services/obsidian_export.py:38` and `bookmark_organizer_pro/services/reader_annotations.py:188` strip `<>:"/\|?*` and cap length with no device-name check; the same helper shape is used wherever a title becomes a filename
  Touches: `bookmark_organizer_pro/services/obsidian_export.py`, `bookmark_organizer_pro/services/reader_annotations.py`, a shared filename helper in `bookmark_organizer_pro/utils/`, `tests/test_services.py`
  Acceptance: One shared helper produces every generated filename and rewrites reserved device names, names ending in a dot or space, and empty results into a safe form that stays stable across runs; a collision after rewriting is disambiguated rather than overwriting; a test covers each reserved name with and without an extension, a trailing-dot title, a title that sanitizes to empty, and two titles that collide after rewriting; an export of a library containing all of them completes with every file written.
  Complexity: S

- [ ] P2: R-196: Run a pseudo-locale and RTL pass in the visual smoke
  Why: The expansion helper exists and has a unit test, but no gate renders the desktop under it, so nothing proves the Tk layout survives longer translated strings at the supported viewport. This is the same shape as the theme gate already flagged in open item R-156.
  Evidence: `bookmark_organizer_pro/i18n.py:147-166` `is_rtl()` and `pseudo_localize()`; the only caller outside the module is `tests/test_i18n.py:24`; `scripts/visual_regression_smoke.py` contains no pseudo-locale or RTL reference
  Touches: `scripts/visual_regression_smoke.py`, `bookmark_organizer_pro/i18n.py`, `tests/test_visual_regression_smoke.py`
  Acceptance: The smoke gains a pseudo-locale phase rendering the core desktop surfaces and every modal dialog with expanded strings at the supported laptop geometry, failing on clipping, horizontal overflow, or a control pushed outside its container; the RTL variant runs on at least the main window and one dense dialog; the gate is proved by shrinking one container until an expanded string overflows and watching it fail; normal-locale captures are unaffected. Depends on R-185 so the strings being expanded are the ones translators actually see.
  Complexity: M

- [ ] P2: R-197: Cover the modules that carry lint exemptions or no tests at all
  Why: `services/organization.py` has a repo-wide `F821` exemption and no test references it, so a genuine `NameError` there is invisible to both the lint gate and the suite. The pattern extends to a long tail concentrated in the Tkinter layer.
  Evidence: `pyproject.toml` per-file-ignores exempt `bookmark_organizer_pro/services/organization.py` and `bookmark_organizer_pro/mcp_server.py` from `F821`; no test references `services/organization.py`, `services/icons.py`, or `services/zotero_interop.py`; all eight AI app_mixins plus `bookmark_crud.py`, `command_palette.py`, `zoom.py`, eleven UI modules including the six `workflow_*` files, and `desktop_bootstrap.py`, `logging_config.py`, `text_format.py` have no test reference
  Touches: `tests/test_services.py`, new test modules, `pyproject.toml` per-file-ignores, `bookmark_organizer_pro/services/organization.py`, `bookmark_organizer_pro/mcp_server.py`
  Acceptance: Whatever survives R-191 in `services/organization.py` gains behavioral tests and its `F821` exemption is removed, with forward references rewritten so ruff is satisfied without a blanket exemption; the `mcp_server.py` exemption is narrowed to the specific dynamically injected global instead of the whole file; `services/icons.py` and `services/zotero_interop.py` gain tests for their public entry points; a smoke test imports every module under `bookmark_organizer_pro/` in a subprocess so an undefined name anywhere fails the suite, proved by planting one and watching it fail. Runs after R-191 so no effort goes into covering code that is about to be deleted.
  Complexity: M

- [ ] P2: R-198: Take the build toolchain forward through a frozen-artifact regression
  Why: The recorded PyInstaller version predates a fix for a Windows-only failure in the exact artifact shape this project ships, and the Nuitka release supporting the interpreter R-189 targets is already out.
  Evidence: `packaging/release_manifest.json` `build_tools` records `pyinstaller 6.21.0`; PyInstaller 6.22.2 on 2026-08-17 fixes a spurious security validation error when a onefile executable launches from a symlinked directory or junction (https://raw.githubusercontent.com/pyinstaller/pyinstaller/develop/doc/CHANGES.rst); Nuitka 4.2 on 2026-08-27 adds official Python 3.14 support (https://nuitka.net/changelog/Changelog.html); the 2026-08-23 pass deferred this bump for lack of a concrete reason
  Touches: `pyproject.toml` dev extra, `packaging/release_manifest.json`, `packaging/bookmark_organizer.spec`, `packaging/nuitka_build.py`, `scripts/build_release.py`, `scripts/release_artifact_smoke.py`
  Acceptance: The release rebuilds on PyInstaller 6.22.2 and Nuitka 4.2, the manifest records both, and the artifact smoke passes from a normal directory and from a directory junction; startup time and artifact size are compared against the previous build and any regression beyond ten percent is recorded rather than accepted; runs after R-189 so the interpreter and Tk version are settled first.
  Complexity: M

- [ ] P2: R-199: Add a provider model catalog to Assistant Settings
  Why: Provider setup asks the user to type a model identifier, so a decommissioned or misspelled model fails at first use rather than at selection. The closest architectural peer shipped exactly this control in its latest release, and the knowledge already exists in the codebase but is only used reactively.
  Evidence: https://github.com/goniszewski/grimoire/releases/tag/v1.1.0 adds an AI provider model catalog picker; `bookmark_organizer_pro/ai.py:40` already contains a model-decommission detector; `bookmark_organizer_pro/app_mixins/ai_settings.py` is under active modification in the working tree on 2026-09-04; "does the pipeline run on the device" is the first question users ask of any new tool (https://news.ycombinator.com/item?id=47889110)
  Touches: `bookmark_organizer_pro/ai.py`, `bookmark_organizer_pro/app_mixins/ai_settings.py`, a versioned local model catalog data file, `bookmark_organizer_pro/services/local_state.py`, locale strings, `tests/test_ai_clients.py`
  Acceptance: Each provider offers a picker listing known models with context window and a decommissioned marker, sourced from a versioned local data file with no network call at settings time; a free-text field remains for models absent from the catalog and is clearly labeled unverified; selecting a decommissioned model warns before saving; each entry states whether it runs locally or sends data to a provider; the catalog file has a schema test and a staleness field so an out-of-date catalog is visible; no provider default changes.
  Complexity: M

- [ ] P2: R-200: Decide the FastMCP 4 and MCP SDK v2 migration on measured compatibility
  Why: FastMCP 4 is stable and the MCP Python SDK v1 line is on security fixes only, so the current caps pin the server to a maintenance branch. The blocked note recording FastMCP 4 as beta is stale, and the decision needs evidence rather than another deferral.
  Evidence: FastMCP 4.0.0 stable 2026-08-31 with 4.0.2 on 2026-09-02 (https://github.com/jlowin/fastmcp/releases); MCP Python SDK v2.1.1 on 2026-08-25 (https://github.com/modelcontextprotocol/python-sdk/releases); breaking changes at https://gofastmcp.com/getting-started/upgrading/from-fastmcp-3 remove server-initiated sampling and roots, restrict `ctx.elicit()` to the old protocol, move model fields to snake_case, and split background tasks into `fastmcp-tasks`; `pyproject.toml` caps `mcp>=1.28,<2.0` and `fastmcp>=3.4.1,<4.0`; the stale note is the 2026-08-21 update under R-106 in `Roadmap_Blocked.md`
  Touches: `pyproject.toml`, `bookmark_organizer_pro/mcp_server.py`, `bookmark_organizer_pro/services/mcp_auth.py`, `packaging/server.json`, `packaging/product_claims.json`, `tests/test_mcp_tools.py`, `Roadmap_Blocked.md`
  Acceptance: An isolated environment runs the existing MCP contract suite against fastmcp 4.0.2 with SDK v2 and records, per tool, whether schema, annotations, and auth metadata are identical; stdio and Streamable HTTP are exercised against both a current and a pre-2026-07-28 client; the report names every behavioral difference and every tool needing work; the outcome is either a migration landing with all 37 tools passing and the caps raised, or a written keep decision with the measured reasons; either way the stale beta note in `Roadmap_Blocked.md` is corrected. Depends on R-183 so a construction failure during the trial is visible rather than silent.
  Complexity: L

### P3

- [ ] P3: R-201: Give widgets accessible names and roles ahead of Tk 9.1
  Why: Tk widgets are largely invisible to Windows screen readers today, and the accepted Tcl proposal that changes this needs per-widget role and name metadata. Designing that metadata now turns the eventual upgrade into wiring rather than an audit of every surface.
  Evidence: Tcl TIP 733 "Add accessibility/screen reader support to Tk" is state Final, vote 7/0/0, targeted at Tcl-Version 9.1, adding a `tk accessible` command with an MSAA backend on Windows (https://core.tcl-lang.org/tips/doc/trunk/tip/733.md); Tk 9.0.4 only reached CPython Windows builds in 3.14.7 on 2026-08-05 so 9.1 is further out; `bookmark_organizer_pro/ui/tk_interactions.py:75` `_bop_accessible_name` is read only by the smoke test and is invisible to Narrator; the worst surface is `bookmark_organizer_pro/ui/graph_view.py:181`, a `tk.Canvas` with hand-rolled directional navigation and no accessible name
  Touches: `bookmark_organizer_pro/ui/components.py`, `bookmark_organizer_pro/ui/widget_controls.py`, `bookmark_organizer_pro/ui/treeview.py`, `bookmark_organizer_pro/ui/graph_view.py`, the modal helper from R-184, `tests/test_accessibility_contracts.py`
  Acceptance: Every interactive control built through the shared widget factories carries a declared role and an accessible name drawn from its visible label or an explicit override, stored on the widget rather than computed at render time; the graph canvas exposes a name and a role for the canvas and for the selected node; a contract test enumerates interactive widgets across the main window and every dialog and fails naming any without both; the metadata is inert on Tk 8.6 and 9.0 and costs no measurable render time; no behavior changes until a Tk 9.1 interpreter is available, at which point wiring `tk accessible` is a separate item.
  Complexity: M

- [ ] P2: R-203: Make the offline queue replay the worker's job, not the popup's
  Why: `retryPendingSaves` guards against concurrent replays with `pendingReplayInFlight`, a module-level variable. The popup and the side panel are separate realms with separate module instances, so each holds its own `null` guard. Open both, click Retry in both, and every entry is POSTed twice; the queue survives only because the server answers 409 on a duplicate URL. `background.js` has no replay of its own, so a queue built while every page is closed sits there until a human opens a surface and clicks.
  Evidence: `browser-extension/shared.js` declares `let pendingReplayInFlight = null` at module scope and `retryPendingSaves` is called only from `browser-extension/popup.js` and `browser-extension/sidepanel.js`; `browser-extension/background.js` registers no `chrome.alarms` listener and no `onStartup` replay; the duplicate-suppression that makes the race survivable is the API's 409, not extension code
  Touches: `browser-extension/background.js`, `browser-extension/shared.js`, `browser-extension/manifest.json`, `tests/test_browser_extension.py`
  Acceptance: WHEN the offline queue is non-empty and the API becomes reachable, the service worker SHALL replay it without any page being open, driven by a `chrome.alarms` schedule that survives worker teardown; WHEN two realms attempt a replay at once, exactly one SHALL proceed, enforced by a claim written to `chrome.storage.local` with an owner and an expiry rather than by a module-level variable, and the claim SHALL expire so a torn-down worker cannot deadlock the queue; a test drives two concurrent replays through separate module instances and asserts each entry is POSTed once; a test asserts a replay runs from the worker with no page context.
  Complexity: M
