# Roadmap: Bookmark Organizer Pro

Actionable incomplete work only. Historical and completed material belongs in `CHANGELOG.md`; blocked work remains in `Roadmap_Blocked.md`.

## Research-Driven Additions

### P0

- [ ] P0: R-152: Route all bookmark deletion through a persistent trash contract
  Why: The README promises recoverable trash, but desktop, CLI, REST, MCP, and maintenance paths permanently remove records while isolated trash helpers are unused and conflate deletion with archive state.
  Evidence: `README.md:433`; `bookmark_organizer_pro/commands.py:160`; `bookmark_organizer_pro/cli.py:976`; `bookmark_organizer_pro/services/api.py:1206`; `bookmark_organizer_pro/mcp_server.py:1424`; `bookmark_organizer_pro/managers/bookmarks.py:943`
  Touches: bookmark model and manager, commands, desktop CRUD and trash workspace, CLI, REST, MCP, search filters, snapshots, reader annotations, progress, tests
  Acceptance: Delete from every public surface records an independent deletion timestamp, hides the bookmark from normal views, preserves its snapshots, extracted text, highlights, and progress across restart, and exposes list, restore, and explicit purge operations; archive state survives trash and restore unchanged; purge creates and verifies a complete recovery bundle for the records and owned artifacts before unlinking them, and never treats a bookmark-only safepoint as artifact recovery; cross-surface, restart, restore, and purge-failure tests pass.
  Complexity: L

- [ ] P0: R-153: Make background extension captures lossless and outcome-visible
  Why: The retry journal silently drops the oldest saves after 50 entries, and context-menu saves ignore success, queue, and failure outcomes.
  Evidence: `browser-extension/shared.js:696`; `browser-extension/background.js:122`; `browser-extension/popup.js:203`; `browser-extension/sidepanel.js:612`; community offline-failure signal at https://www.reddit.com/r/selfhosted/comments/1raq3b0/selfhosted_bookmark_manager_with_android_app_that/
  Touches: `browser-extension/shared.js`, `browser-extension/background.js`, popup and side-panel pending panels, IndexedDB journal storage, extension tests and packaging contracts
  Acceptance: More than 50 distinct offline captures remain queued in order until explicit clear or successful replay; quota failure refuses the new capture without evicting old entries and sets a visible action badge plus durable status; replay is idempotent after worker restart; popup, side panel, context menu, and selection capture share the same outcome contract; overflow and quota tests pass in Chromium and Firefox builds.
  Complexity: M

- [ ] P0: R-154: Stream migrations into a disk-backed preflight plan
  Why: Preflight hashes the source, materializes the parsed export, and retains all converted bookmarks in memory, so large imports can exhaust memory before apply.
  Evidence: `bookmark_organizer_pro/services/migration.py:40`, `:57`, `:216`; iterative parser https://pypi.org/project/ijson/; Karakeep import pressure https://github.com/karakeep-app/karakeep/issues/1748; large-archive fix https://github.com/karakeep-app/karakeep/releases/tag/v0.33.2
  Touches: `bookmark_organizer_pro/services/migration.py`, `pyproject.toml`, dependency lock and release manifest, temporary SQLite plan store, migration CLI and desktop flows, job ledger, cancellation, tests
  Acceptance: A hashing reader feeds `csv.DictReader` or pinned `ijson>=3.5.1,<4` so source bytes are consumed once; converted records, normalized dedupe keys, counters, and errors stream into a temporary SQLite plan rather than a bookmark tuple; apply streams that plan only after preflight approval; record, field, nesting, and source-byte ceilings fail with an exact report; cancellation or failure deletes the spool and leaves the library untouched; generated 250 MB CSV and JSON fixtures keep additional Python allocation below 96 MiB while preserving deterministic hashes and fidelity counts.
  Complexity: XL

### P1

- [ ] P1: R-155: Isolate production data paths in every test process
  Why: Per-class overrides and an after-the-fact extension-registry guard do not stop other default application paths from touching a user's library.
  Evidence: `tests/__init__.py:10`; per-class overrides in `tests/test_cli.py:19`, `tests/test_services.py:36`, and `tests/test_mcp_tools.py:30`; commit-history repairs for extension-origin leakage
  Touches: test bootstrap, `bookmark_organizer_pro/constants.py`, local-state and API defaults, subprocess test helpers, storage fixtures
  Acceptance: A temporary `BOOKMARK_DATA_DIR` is established before application imports in the main suite and spawned test processes; a default `BookmarkAPI` writes its registry there; canaries cover the known production paths derived from constants, local state, API credentials, and extension-origin defaults while allowing ordinary pytest temporary directories; every protected real path remains absent or byte-identical after the full suite.
  Complexity: M

- [ ] P1: R-156: Make desktop theme activation a tested gate condition
  Why: Several visual-smoke paths call `set_theme()` without checking its result, so captures can pass while rendering the previous theme.
  Evidence: `scripts/visual_regression_smoke.py:776`, `:822`, `:851`, and `:956`; historical gate repair commit `584799be1f3bf471a45480c107a99ceb427ec5b5`; current smoke unit tests in `tests/test_visual_regression_smoke.py`
  Touches: `scripts/visual_regression_smoke.py`, theme-matrix helpers, `tests/test_visual_regression_smoke.py`
  Acceptance: Every theme transition checks the returned theme name or success result before capture; a fake manager that refuses or no-ops a requested transition makes each affected matrix path fail with the requested and active theme names; an untouched manager passes the same paths.
  Complexity: S

- [ ] P1: R-157: Report duplicate adds consistently in desktop and CLI
  Why: Duplicate GUI and CLI adds claim success, and the desktop starts unnecessary favicon work, while REST and MCP already expose `already_exists`.
  Evidence: `bookmark_organizer_pro/managers/bookmarks.py:1116`; `bookmark_organizer_pro/app_mixins/bookmark_crud.py:35`; `bookmark_organizer_pro/cli.py:945`; comparison paths `bookmark_organizer_pro/services/api.py:1090` and `bookmark_organizer_pro/mcp_server.py:728`
  Touches: bookmark manager result contract, desktop add flow, CLI text and JSON output, favicon dispatch, cross-surface tests
  Acceptance: Normalized duplicates make no mutation and trigger no favicon fetch; desktop selects the existing row and reports its title; CLI text prints the existing ID and `--json` returns `already_exists: true`; REST and MCP behavior stays compatible; URL-normalization variants are covered.
  Complexity: S

- [ ] P1: R-158: Replace the absolute first-run privacy claim with an egress inventory
  Why: The launcher says no data leaves the machine without an AI key even though non-AI metadata, favicon, link-check, snapshot, feed, transcript, Wayback, and update features can use the network.
  Evidence: `bookmark_organizer_pro/launcher.py:65`; `README.md:627`; egress controls in `bookmark_organizer_pro/services/egress.py` and `bookmark_organizer_pro/services/snapshot.py`
  Touches: launcher banner, onboarding copy, network settings, README privacy section, string catalog, copy-contract tests
  Acceptance: First-run copy distinguishes default-local storage from automatic, user-triggered, opt-in, and provider-specific egress; each listed path names its control; tests fail if a registered egress feature lacks an inventory entry; no feature's actual default changes silently.
  Complexity: S

- [ ] P1: R-159: Remove confirmation from the restorable extension queue clear
  Why: Popup and side panel block an undoable clear behind `globalThis.confirm` even though the cleared journal can be restored.
  Evidence: `browser-extension/popup.js:110`; `browser-extension/sidepanel.js:150`; `browser-extension/shared.js:749`; `tests/test_packaging.py:500`
  Touches: extension popup, side panel, shared journal API, locale strings, extension and packaging tests
  Acceptance: Clear acts immediately, reports the count, and exposes Restore in the same panel; restore preserves entry order and retry metadata after worker restart; no confirmation API or `confirmed` flag remains; popup and side-panel parity tests pass.
  Complexity: S

- [ ] P1: R-160: Replace deprecated LanceDB table discovery
  Why: The clean functional suite still emits 58 deprecation warnings from one `table_names()` call.
  Evidence: `bookmark_organizer_pro/services/vector_store.py:184`; 2026-08-23 pytest output; current API https://lancedb.github.io/lancedb/python/python/
  Touches: `bookmark_organizer_pro/services/vector_store.py`, vector-store fakes and tests, dependency compatibility notes
  Acceptance: Current LanceDB uses `list_tables()` without a warning; the supported older-version fallback is explicit and tested; legacy-generation detection is unchanged; the full suite emits no LanceDB table-discovery deprecation warning.
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

- [ ] P2: R-173: Extract named domain modules from CLI, MCP, and desktop tools
  Why: Three large dispatch files mix unrelated domains, making cross-surface outcome contracts hard to compare and test.
  Evidence: `bookmark_organizer_pro/cli.py`; `bookmark_organizer_pro/mcp_server.py`; `bookmark_organizer_pro/app_mixins/tools.py`; recurring cross-surface fixes in commit history
  Touches: new `bookmark_organizer_pro/cli_commands/` and `bookmark_organizer_pro/mcp_tools/` packages, `bookmark_organizer_pro/app_mixins/tools_data.py`, `bookmark_organizer_pro/app_mixins/tools_maintenance.py`, `bookmark_organizer_pro/app_mixins/tools_research.py`, compatibility facades, packaging contracts
  Acceptance: Migration and import handlers, maintenance handlers, and reader and export handlers move from `cli.py` into named domain modules; library, reader, and maintenance tool specs and handlers move from `mcp_server.py` while transport stays there; data, maintenance, and research desktop actions move from `tools.py` into the named mixins; each original file shrinks by at least 35%, no extracted module exceeds 800 lines, imports remain acyclic, public entry points and generated schemas stay identical, import time does not regress by more than 10%, and the full local gates pass.
  Complexity: L
