# Changelog

All notable changes to Bookmark-Organizer-Pro will be documented in this file.

## [v6.8.5] - 2026-06-28

### Added

- Added a local visual regression smoke gate that captures desktop and browser-extension surfaces, then fails on blank, missing-text, console-error, or horizontal-overflow regressions.
- Added local accessibility contract checks for extension labels/status/tab semantics and Tk keyboard-focus activation helpers.
- Added a local `pip-audit` vulnerability wrapper with explicit suppression metadata and regression tests.
- Added a local release artifact smoke helper that executes the built distributable and verifies version output before publishing.
- Added behavioral extension-to-local-API round-trip tests for popup, side-panel, Reading List, and context-menu save payloads.
- Synced distribution documentation to local-only build/release commands and added a drift test for removed workflow references.
- Added `/bookmarks` REST pagination and filter parity for tag, read-later, pinned, offset, and deterministic list responses, plus side-panel load-more behavior.
- Added an extension pending-save queue for failed context-menu quick saves, with popup/side-panel pending counts plus Retry and Clear actions.

### Fixed

- Required the local API bearer token for OPDS 1.2 and OPDS 2.0 catalog endpoints, matching the other bookmark-data read endpoints.
- Added regression coverage for unauthorized and authorized OPDS catalog access.
- Drained unauthenticated POST request bodies before returning 401 JSON so local API clients receive stable error responses on Windows.

## [v6.8.4] - 2026-06-27

Trust and metadata repair pass.

### Fixed

- Preserved `read_later` from extension and local API saves, including ordered queue positions for new read-later bookmarks.
- Added API and extension contract coverage for popup saves, side-panel saves, Chrome Reading List imports, context-menu quick saves, auth failures, duplicate handling, and field preservation.
- Refreshed README, working notes, and MCP tool metadata to match the live 56 CLI commands, 452 collected tests, 48 categories, 7,550 rules, keyring-first secret storage, and optional tray availability.
- Replaced blocking maintenance confirmations/results with immediate toast/status/report flows, automatic safepoints, and a Tools-menu restore command for bulk cleanup changes.
- Added in-dialog restore for category deletion so the category manager can delete immediately without a confirmation modal.
- Added About/System diagnostics actions for opening logs, copying a redacted diagnostics summary, and exporting a redacted support bundle without bookmark contents or secrets.
- Regenerated the gettext template and added a local `python -m bookmark_organizer_pro.i18n --check` plus pytest freshness gate so source-string drift fails locally.
- Added an early `main.py --version` exit path and entry-point `freeze_support()` so packaged artifact smoke checks do not start the GUI.
- Documented and collected the `jaraco.text` packaging helper required by PyInstaller's `pkg_resources` runtime hook.
- Stopped `run_with_timeout()` from retaining executor resources after timeout and hardened its regression test against scheduler noise.

## [v6.8.3] - 2026-06-26

Secondary premium-polish pass for dialogs and assistant workflows.

### Changed — UX/UI polish

- Refined Assistant Settings with clearer product language, stronger section hierarchy, and consistent provider/save/test actions.
- Brought reader highlights, graph view, dependency setup, export, assistant activity, category/context menus, and live workflow feedback closer to the shared desktop component language.
- Replaced several raw Tk buttons and decorative emoji/status glyphs with shared ModernButton controls and text-first labels.
- Simplified assistant undo into immediate action plus toast/status feedback, matching the app's no-blocking-confirmation interaction rule.
- Updated README screenshot metadata/version copy for v6.8.3.

## [v6.8.2] - 2026-06-26

Premium-polish pass for the desktop workspace and browser extension.

### Changed — UX/UI polish

- Reworked the default Studio Dark palette so OS dark-mode auto-detection opens a true dark workspace with neutral surfaces, crisp contrast, and mint action accents.
- Tightened shared ttk and custom control states: stronger focus rings, clearer disabled states, calmer hover/selection behavior, and more consistent button/input treatment.
- Refined the main shell, sidebars, selection bar, chat panel, empty states, toasts, bookmark editor, analytics, theme dialogs, category management, quick-add/detail/tag/filter workflows, and About dialog with text-first labels, cleaner hierarchy, and less decorative visual noise.
- Added inline URL validation to the bookmark editor and improved first-run/chat/filtered-empty copy for clearer guidance.
- Brought the MV3 popup, options page, and side panel onto the same Studio visual language with improved status panels, focus states, action hierarchy, empty states, and save/connection feedback.

## [v6.8.0] - 2026-06-08

Default-category expansion, AI-learning loop, and a robustness/security hardening pass.

### Added — Categories & defaults

- **5 new built-in categories** with curated, de-duplicated domain sets and icons:
  Music & Audio, Communication, Cryptocurrency, Maps & Navigation, and
  Books & Literature. 98 previously mis-bucketed sites were relocated into them
  (e.g. all music out of Entertainment, all crypto out of Finance, chat/email
  tools out of Forums/SysAdmin/Social Media) plus 61 new domains. Now 48
  categories / 6,232 domain rules, with the invariant that no domain rule
  appears in two categories.
- **AI-learning loop:** the AI audit log now records the local default-pattern
  prediction next to each AI categorization, and `bop ai-audit learn-defaults`
  mines concrete default improvements (add/fix/confirm) with category-
  concentration weighting and a suspect-case guard that flags search-engine/
  portal artifacts (so e.g. `yandex.com -> Adult Content` isn't auto-applied).
- Verified default corrections derived from a real run (e.g. `frontier.com`
  News->Technology, `gab.com` Forums->Social Media, `themeforest.net`
  Media Production->Design).

### Added — Reliability & UX

- Reusable `LiveWorkflowDialog` with a bounded, drip-revealed activity feed for
  AI categorize/tag/summary runs (memory-safe on very large jobs).
- AI clients gain per-request timeouts and retry/backoff; OpenAI/Groq/DeepSeek
  share one implementation; clearer "model not found" guidance.
- New CI workflow (tests on 3.10-3.13 + ruff) and a focused lint config.

### Fixed — Robustness & security

- Thread-safety in the bookmark store (snapshot-under-lock reads, locked
  merge/empty-trash + dedup), `CategoryManager` lock, SQLite skip-and-log on a
  bad row.
- SSRF IP hardening (IPv4-mapped/NAT64); refuse unsafe XML parsing fallback;
  strip XML-illegal control chars in exporters; constant-time MCP token compare;
  Windows ACL on the AI config file.
- CLI exit codes + stderr errors + delete confirmation; pattern-engine ReDoS
  input cap; teardown/`after()` guards; ScrollableFrame mouse-wheel binding
  leak fixed; `default_categories` moved to a JSON asset.

## [v6.7.0] - 2026-06-08

AI-in-build and bookmark-list interaction release.

### Fixed — AI

- **DeepSeek / OpenAI-compatible providers work in the packaged executable.**
  The `openai` SDK is lazy-imported at runtime via `ensure_package`, which
  PyInstaller could not detect, so the Windows build raised
  `Required package 'openai' is not installed.` for DeepSeek categorization.
  Added `openai` (and its `resources`/`types`/`_streaming` submodules) to the
  PyInstaller hidden imports so the bundled `.exe` can categorize, tag, and
  summarize with DeepSeek out of the box.

### Fixed — Bookmark list (tksheet backend)

- **Row selection is actionable again.** A single click creates a tksheet
  *cell* selection, but `_sync_selection_from_sheet` only read fully-selected
  *rows*, so toolbar/right-click actions saw an empty selection. Now syncs via
  `get_selected_rows(get_cells_as_rows=True)` with a `get_currently_selected`
  fallback, and a button-release safety net.
- **Right-click context menu restored.** Mouse bindings (`<Button-3>`,
  `<Double-1>`, etc.) are now routed to tksheet's internal table canvas (`MT`)
  instead of the outer frame, and `identify_row` resolves rows through
  `MT.identify_row`. Header clicks are routed separately to drive column sort.
- **Selection highlight no longer masked.** Decorative `oddrow`/`evenrow`
  zebra tags are excluded from per-row highlighting so the selection color is
  visible.

### Changed — Packaging / privacy

- Verified the release executable contains no API keys and none of the user's
  bookmark data (all user data lives in `~/.bookmark_organizer/`, outside the
  bundle). Removed a stale local Nuitka smoke-build artifact that had captured
  environment variables; it was gitignored and never committed.

## [v6.6.30] - 2026-06-06

MCP HTTP compatibility release.

### Changed — MCP (R-15/R-58 hardening)

- **Optional mirrored headers** — Streamable HTTP requests no longer require
  `Mcp-Method` and `Mcp-Name` headers, matching standard MCP clients.
- **Validation preserved** — when mirrored headers are present, they still must
  match the JSON-RPC method and tool/resource/prompt name.

### Tests

- Added middleware coverage proving missing mirrored headers replay to the
  downstream MCP app, while existing mismatched-header rejection remains intact.

## [v6.6.29] - 2026-06-06

MCP stdio contract smoke release.

### Added — MCP (R-15 partial)

- **Subprocess stdio smoke** — added a real MCP stdio client test that launches
  the server with `python -m bookmark_organizer_pro.mcp_server`.
- **Contract validation** — the stdio smoke initializes `ClientSession`, lists
  tools, and verifies `chat_with_collection_stream` stream contract metadata.

### Tests

- Extended MCP runtime coverage from in-process FastMCP to subprocess stdio
  metadata validation.

## [v6.6.28] - 2026-06-06

MCP stream contract release.

### Added — MCP (R-15 partial)

- **Stream contract marker** — added `CHAT_STREAM_CONTRACT_VERSION` and
  `CHAT_STREAM_EVENT_TYPES` for the `chat_with_collection_stream` payload.
- **Tool metadata** — raw MCP and FastMCP tool catalogs now expose the stream
  contract version and event types under Bookmark Organizer metadata keys.
- **Client validation** — FastMCP client smoke coverage now verifies the final
  stream payload carries the same contract marker.

### Tests

- Extended MCP streaming/runtime tests for raw payloads, raw tool metadata,
  FastMCP tool metadata, and FastMCP client responses.

## [v6.6.27] - 2026-06-06

Updater apply plan release.

### Added — Distribution (R-41 partial)

- **Apply plan model** — added `UpdateManager.build_apply_plan()` and
  `UpdateApplyPlan` for non-mutating install/rollback planning.
- **CLI plan output** — added `updates plan` to print install directory,
  rollback directory, staged paths, planned actions, and blockers.
- **Rollback design surface** — the plan records a deterministic rollback
  directory without creating, extracting, or replacing files.

### Tests

- Added updater service coverage for unstaged and staged apply plans.
- Added CLI coverage for the default `updates plan` blocker output.

## [v6.6.26] - 2026-06-06

Updater staged cleanup release.

### Added — Distribution (R-41 partial)

- **Staged cleanup** — added `UpdateManager.clear_staged_update()` to remove
  the staged manifest and cached staged target files only.
- **CLI cleanup** — added `updates clean-staged` for removing staged updater
  artifacts without touching trusted metadata or app files.
- **Cleanup reporting** — cleanup now reports whether the manifest was removed,
  which staged targets were deleted, and any errors.

### Tests

- Added updater service coverage for cleanup success and empty cleanup state.
- Added CLI coverage for the default `updates clean-staged` output.

## [v6.6.25] - 2026-06-06

Updater apply preflight release.

### Added — Distribution (R-41 partial)

- **Apply preflight** — added `UpdateManager.apply_preflight()` to report staged
  update readiness and blockers without mutating files.
- **CLI dry run** — `updates apply --dry-run` and `updates apply --preflight`
  now print target details, staged paths, and explicit blockers.
- **Persistent apply gate** — real `updates apply` remains blocked while the
  dry-run path makes missing staged updates and disabled application visible.

### Tests

- Added updater service coverage for unstaged and staged preflight results.
- Added CLI coverage for `updates apply --dry-run` blocker output.

## [v6.6.24] - 2026-06-06

Updater staging manifest release.

### Added — Distribution (R-41 partial)

- **Staged update manifest** — successful `download_update()` calls now write
  `updates/staged_update.json` with current version, latest version, target
  metadata, channel, staged paths, and timestamp.
- **Readback status** — added `UpdateManager.staged_update()` to validate the
  manifest and confirm staged target files still exist inside the update cache.
- **CLI readback** — added `updates staged` to report no staged update,
  incomplete staged files, or present staged targets without applying them.

### Notes

- Update application remains blocked; the manifest is an audit and preflight
  layer for the future apply workflow.

### Tests

- Added updater service coverage for manifest creation and missing staged
  target detection, plus CLI coverage for the default `updates staged` output.

## [v6.6.23] - 2026-06-06

Updater download staging release.

### Added — Distribution (R-41 partial)

- **Trusted target staging** — `UpdateManager.download_update()` now runs the
  same tufup trusted metadata check as `updates check`, then stages the selected
  target files in the update cache with `Client.download_target()`.
- **CLI staging path** — `updates download` now reports staged target paths
  when readiness gates pass, while preserving disabled/not-ready output for
  default installs.
- **Cache boundary guard** — staged target paths are validated to stay under
  the update target cache before they are reported.

### Notes

- `updates apply` remains an explicit refusal gate until install directory
  isolation, rollback, and user confirmation are implemented and tested.

### Tests

- Added updater service coverage for staged target downloads and cache-escape
  rejection, plus CLI coverage for the new `updates download` default output.

## [v6.6.22] - 2026-06-06

Desktop graph view release.

### Added — Graph (R-22)

- **Graph canvas** — added a Tk-native graph dialog that renders bookmarks,
  tags, categories, and domains from the graph service.
- **Navigation** — added canvas pan/zoom, node selection details, and
  double-click opening for bookmark nodes.
- **App entry points** — added Graph View to the Tools menu and command
  palette.
- **GUI export** — graph JSON export is available from the desktop graph
  dialog.

### Tests

- Extended UI import coverage for the graph dialog alongside existing graph
  service and CLI export tests.

## [v6.6.21] - 2026-06-06

Graph foundation release.

### Added — Graph (R-22 partial)

- **Graph model** — added bookmark graph nodes and edges linking bookmarks to
  tags, categories, and domains.
- **Force layout** — added deterministic force-directed layout coordinates for
  graph exports.
- **Graph export** — added `graph-export` CLI command for JSON graph export
  with output path and bookmark limit controls.

### Notes

- R-22 remains open for the desktop canvas graph view and interactive graph
  navigation.

### Tests

- Added graph construction, force layout, JSON export, and CLI export coverage.

## [v6.6.20] - 2026-06-06

Desktop reader pane release.

### Added — Reader (R-21)

- **Reader dialog** — added a Tk-native reader view for selected bookmarks with
  extracted text, saved highlight rendering, highlight list, and note editor.
- **Selection highlights** — users can select text, choose one of four
  highlight colors, and persist the highlight through the reader annotation
  store.
- **GUI export** — reader highlights can now be exported to Markdown from the
  desktop dialog.
- **App entry points** — added reader access through the Tools menu, bookmark
  context menu, and command palette.

### Tests

- Added import coverage for the reader dialog UI surface alongside the reader
  service and CLI tests from v6.6.19.

## [v6.6.19] - 2026-06-06

Reader annotation foundation release.

### Added — Reader (R-21 partial)

- **Reader highlight storage** — added durable JSON-backed reader highlights
  with bookmark ID, selected text range, selected text, note, timestamps, and
  four supported colors.
- **Markdown export** — reader highlights can be exported per bookmark as
  Markdown with source URL, ranges, quotes, colors, and notes.
- **CLI workflow** — added `reader list`, `reader add`, `reader note`,
  `reader delete`, and `reader export` commands against existing extracted
  text.

### Notes

- R-21 remains open for the desktop reader pane, in-text selection UI, and
  interactive highlight editing.

### Tests

- Added service coverage for highlight persistence, range validation, Markdown
  export, and CLI add/list/export routing.

## [v6.6.18] - 2026-06-06

Sun Valley ttk theme release.

### Added — UI (R-18)

- **Optional Sun Valley base theme** — the desktop style manager now uses
  `sv-ttk` when installed, selecting light or dark mode from the active theme
  background before applying BOP's theme color overrides.
- **Installer extra** — added the `sunvalley` optional dependency group for
  users who want the Windows 11-style ttk base without making it a hard
  dependency.
- **Theme diagnostics** — the style manager now exposes the active native base
  theme and fallback/error status for troubleshooting.

### Compatibility

- When `sv-ttk` is not installed or cannot apply, the app keeps the previous
  `clam`/`default` fallback path.
- Existing custom theme colors remain authoritative over widget foreground,
  background, selection, and accent styling.

### Tests

- Added coverage for Sun Valley light/dark mode selection and optional
  dependency metadata.

## [v6.6.17] - 2026-06-06

Live MCP progress bridge release.

### Added — MCP (R-15 partial)

- **Live progress bridge** — `CollectionChat.stream_answer()` now accepts a
  chunk event callback, and the FastMCP tool wrapper bridges those callbacks to
  progress notifications while `chat_with_collection_stream` is running.
- **Threaded FastMCP runner** — chat stream tool execution can run in a worker
  thread while the async FastMCP wrapper forwards chunk progress to the client.
- **Client smoke** — added an in-process FastMCP client test that calls
  `chat_with_collection_stream` with a progress handler and verifies progress
  notifications plus the final result.

### Notes

- The raw MCP path still returns the event payload without FastMCP progress
  notifications.
- R-15 remains open for broader transport/client matrix validation and any
  native streaming adapters beyond OpenAI-compatible providers and Ollama.

### Tests

- Added end-to-end FastMCP client progress coverage for chat stream calls.

## [v6.6.16] - 2026-06-06

MCP progress notification release.

### Added — MCP (R-15 partial)

- **FastMCP progress notifications** — `chat_with_collection_stream` now accepts
  FastMCP's injected context and reports progress for each ordered chunk event
  when the client provides a progress token.
- **Progress replay helper** — added a tested helper that maps stream events to
  bounded progress messages and a final `complete` notification.
- **Schema guard** — FastMCP catalog coverage now verifies the injected context
  is not exposed as a user-provided tool argument.

### Notes

- The final MCP tool result remains unchanged for clients that do not consume
  progress notifications.
- End-to-end client progress smoke testing remains open until a local MCP client
  harness can assert notifications over the transport.

### Tests

- Added MCP coverage for progress reporting and FastMCP context schema hygiene.

## [v6.6.15] - 2026-06-06

Provider streaming release.

### Added — MCP (R-15 partial)

- **Provider streaming adapters** — `AIClient` now exposes `stream_complete()`
  while preserving the existing `complete()` contract.
- **OpenAI-compatible streaming** — OpenAI, Groq, and DeepSeek clients now yield
  chat completion deltas from native streaming responses.
- **Ollama streaming** — local Ollama completions now read line-delimited
  streamed `/api/generate` responses.
- **RAG stream propagation** — `CollectionChat.stream_answer()` now builds MCP
  response events from provider deltas when the selected provider supports
  native streaming.

### Notes

- `chat_with_collection_stream` now reports `mode=provider_stream_events` and
  `provider_streaming=true` when events came from a native provider stream.
- FastMCP progress notifications remain open as the next R-15 transport slice.

### Tests

- Added provider adapter tests and service/MCP coverage for provider-streamed
  chat events.

## [v6.6.14] - 2026-06-06

MCP chat response event release.

### Added — MCP (R-15 partial)

- **Stream-shaped chat tool** — added `chat_with_collection_stream` for RAG
  answers returned as ordered `chunk` events followed by a `complete` metadata
  event.
- **Shared chat scoping** — streamed and non-streamed chat tools now share the
  same bookmark ID, tag, and category scope resolution.
- **Service event helpers** — RAG chat now exposes bounded chunk sizing and
  answer-to-event conversion helpers for future transport-level streaming.

### Notes

- This release provides deterministic client response events from the current
  completed-answer RAG path. Provider-native token streaming remains open under
  R-15.

### Tests

- Added service and MCP tool coverage for chat event reconstruction, metadata,
  scoping, and tool catalog annotations.

## [v6.6.13] - 2026-06-06

OPDS serving release.

### Added — Export (R-26)

- **Loopback OPDS route** — the local API now serves `GET /opds` as an OPDS
  1.2 acquisition feed.
- **Catalog filters** — `/opds` supports `tag`, `category`, `title`, and
  bounded `limit` query parameters.
- **Shared renderer** — OPDS file export and HTTP serving now use the same
  `render_opds()` output path.

### Tests

- Added local API coverage for the OPDS route, content type, media type
  inference, and open-access acquisition links.

## [v6.6.12] - 2026-06-06

OPDS export foundation release.

### Added — Export (R-26 partial)

- **OPDS 1.2 acquisition feed export** — added `export_opds()` to generate
  Atom-based OPDS XML with open-access acquisition links to bookmark URLs.
- **CLI export command** — added `opds-export` with `--output`, `--title`,
  `--tag`, and `--catalog-url` options.
- **Media type inference** — OPDS acquisition links infer EPUB, PDF, or HTML
  media types from bookmark metadata and URL extensions.

### Tests

- Added service coverage for OPDS XML output and CLI coverage for
  `opds-export`.

## [v6.6.11] - 2026-06-06

Updater bootstrap and safety-gate release.

### Added — Distribution (R-41 partial)

- **Updater bootstrap guide** — added `docs/distribution/updater-bootstrap.md`
  with client policy paths, trusted `root.json` placement, optional dependency
  install, HTTPS repository configuration, target naming, repository owner
  checklist, and safety gates.
- **Download/apply refusal gates** — `updates download` and `updates apply`
  now exist as explicit non-mutating commands that refuse to run and point users
  back to `updates check`.

### Tests

- Added CLI coverage for the download/apply gates and documentation coverage for
  trusted root placement and target naming.

## [v6.6.10] - 2026-06-06

Updater availability-check release.

### Added — Distribution (R-41 partial)

- **Non-applying tufup adapter** — `UpdateManager.check_for_updates()` now
  constructs `tufup.client.Client` only when updates are enabled, repositories
  are configured, tufup is importable, and local trusted `root.json` metadata is
  present.
- **Structured availability result** — update checks return current version,
  latest version, target name/path, readiness reason, and error details without
  downloading targets or applying updates.
- **CLI check behavior** — `updates check` now reports update availability,
  no-update, not-ready, or check-failed status from the adapter.
- **Trusted root readiness** — `updates status` now shows whether local trusted
  root metadata is present.

### Tests

- Added fake-client coverage proving the update check path calls
  `check_for_updates()` without invoking download/apply behavior.

## [v6.6.9] - 2026-06-06

Updater policy foundation release.

### Added — Distribution (R-41 partial)

- **Optional updater dependency** — added `bookmark-organizer-pro[updates]`
  with `tufup>=0.10,<0.11`; live package verification confirmed 0.10.0 is the
  current tufup release.
- **Disabled-by-default update policy** — added `UpdateManager`,
  `UpdatePolicy`, and `UpdateStatus` to persist update repository settings
  without downloading or applying binaries automatically.
- **CLI update surface** — added `updates status`, `updates check`, and
  `updates configure` commands. The check path reports readiness only; actual
  download/apply remains gated.
- **HTTPS repository guard** — update metadata and target URLs must use HTTPS
  before they can be persisted.

### Tests

- Added service and CLI coverage for default-disabled status, HTTPS validation,
  tufup readiness, version comparison, and `updates status`.

## [v6.6.8] - 2026-06-06

Nuitka compile-smoke release.

### Added — Distribution (R-40)

- **Smoke compile target** — `packaging/nuitka_build.py` now accepts
  `--target smoke` to build a small console executable that exercises Nuitka
  metadata, icon, asset, report, output, and job-control flags without pulling
  in the full GUI import graph.
- **Smoke entrypoint** — added `packaging/nuitka_smoke.py`, a self-contained
  version-printing executable entrypoint kept in sync with app metadata by
  tests.
- **Artifact validation** — the local standalone smoke compile completed with
  Nuitka 4.1.2/MSVC, emitted `compilation-report.xml`, included icon assets,
  and the generated `BookmarkOrganizerProSmoke.exe --version` reported
  `Bookmark Organizer Pro v6.6.8`.

### Tests

- Added packaging-helper coverage for smoke target command generation and
  smoke entrypoint version sync.

## [v6.6.7] - 2026-06-06

Nuitka build-control release.

### Improved — Distribution (R-40 partial)

- **Compiler job control** — `packaging/nuitka_build.py` now emits
  `--jobs=4` by default and accepts `--jobs N` for bounded local compile
  attempts.
- **Toolchain verification** — active environment verification confirmed
  Nuitka 4.1.2 and MSVC `cl 14.3` availability.
- **Compile-smoke evidence** — an unthrottled full-app standalone compile
  attempt ran past 15 minutes, so the next R-40 pass should use the bounded
  jobs path.

### Tests

- Added packaging-helper coverage for custom `--jobs` values.

## [v6.6.6] - 2026-06-06

Nuitka build-path release.

### Added — Distribution (R-40 partial)

- **Nuitka build helper** — added `packaging/nuitka_build.py` with onefile and
  standalone modes plus dry-run command generation.
- **Tkinter and asset flags** — the generated command enables the Tkinter
  plugin, includes package imports, includes app icons, and writes a
  compilation report.
- **Windows metadata** — the command emits icon, no-console, version,
  product, company, and file-description flags on Windows.
- **Optional packaging extra** — added `bookmark-organizer-pro[nuitka]` for
  installing Nuitka 4.1+ build tooling.

### Tests

- Added packaging-helper tests for command flags, dry-run behavior, and the
  optional dependency declaration.

## [v6.6.5] - 2026-06-06

SQLite runtime selection release.

### Improved — Storage (R-31)

- **Opt-in active backend** — `BookmarkManager` can now use SQLite through
  `storage_backend="sqlite"`, `.sqlite`/`.db` file paths, or
  `BOOKMARK_STORAGE_BACKEND=sqlite`.
- **JSON remains default** — unknown backend names fall back to JSON and the
  default app path still uses the existing JSON storage manager.
- **Large ID compatibility** — SQLite stores bookmark IDs as text columns while
  preserving integer IDs inside bookmark payloads.

### Tests

- Added manager-level backend selection coverage and unsigned bookmark ID
  persistence coverage.

## [v6.6.4] - 2026-06-06

SQLite migration foundation release.

### Added — Storage (R-31 partial)

- **SQLite storage backend** — added `SQLiteStorageManager`, a WAL-enabled
  backend with the same `load()`/`save()` shape as the JSON storage manager.
- **Opt-in migration command** — added `sqlite-migrate [--source JSON]
  [--dest DB]` to copy the current JSON library into SQLite.
- **Indexed payload rows** — SQLite rows preserve the full bookmark JSON payload
  while indexing URL, category, created-at, and modified-at fields.

### Tests

- Added SQLite WAL, round-trip, corrupt-row tolerance, JSON-to-SQLite
  migration, and CLI parser coverage.

## [v6.6.3] - 2026-06-06

MCP Streamable HTTP release.

### Added — MCP (R-58)

- **Streamable HTTP server** — added `mcp-http-server` with `--host`,
  `--port`, and `--path` options. It binds to loopback by default.
- **Stateless HTTP** — the FastMCP HTTP runner starts with stateless HTTP
  enabled.
- **Mirrored header validation** — POST requests are rejected when
  `Mcp-Method` or `Mcp-Name` headers do not match the JSON-RPC body.

### Tests

- Added CLI coverage for the HTTP server command and unit coverage for
  header mismatch rejection/body replay.

## [v6.6.2] - 2026-06-06

MCP stateless-readiness release.

### Improved — MCP (R-58 partial)

- **Stateless stdio mode** — raw SDK and FastMCP transports now run with the
  SDK stateless flag enabled.
- **Cacheable tool catalog** — `tools/list` results now expose `ttlMs` and
  `cacheScope` hints in both raw SDK and FastMCP paths.
- **Tool behavior metadata** — raw SDK and FastMCP tool catalogs now expose
  read-only, destructive, idempotent, open-world, and stateless metadata.
- **Client-neutral server docs** — MCP server module docs no longer name
  specific clients.

### Tests

- Added raw SDK and FastMCP catalog assertions for cache hints, stateless
  metadata, and tool annotations.

## [v6.6.1] - 2026-06-06

MCP dependency compatibility release.

### Improved — MCP (R-59)

- **FastMCP 3.4 floor** — optional MCP dependencies now require
  `fastmcp>=3.4,<4` and `mcp>=1.24,<2`, aligning BOP with the current stable
  FastMCP 3.x line.
- **FastMCP packaging** — PyInstaller hidden imports include `fastmcp` alongside
  the MCP SDK fallback.
- **Runtime verification** — `_build_fastmcp_server()` was verified against
  FastMCP 3.4.2 and MCP 1.27.2.

### Tests

- Added MCP dependency metadata and FastMCP builder compatibility checks.

## [v6.6.0] - 2026-06-06

List performance and release metadata sync release.

### Added — Performance (R-16)

- **Virtualized bookmark list** — the main desktop list now uses a
  `tksheet`-backed table for visible-row rendering instead of fully rebuilding
  a `ttk.Treeview` widget for every refresh.
- **Treeview-compatible adapter** — selection, context menus, sorting,
  sidebar/chat bookmark selection, zoom, and row styling continue to use the
  existing app integration surface.
- **Fallback renderer** — the legacy sortable `ttk.Treeview` remains available
  if `tksheet` cannot be imported.

### Fixed

- Sidebar bookmark deep links now select rows by bookmark ID instead of
  comparing the title column to the bookmark ID.
- Release metadata is synchronized across package metadata, extension manifest,
  PyInstaller spec, Windows version resource, README badge, and runtime
  `APP_VERSION`.

### Tests

- Added a release metadata sync check covering pyproject, extension manifest,
  PyInstaller spec, and Windows version resource.

## [v6.5.2] - 2026-06-05

GUI chat, sidebar surfaces, tree view, keyboard accessibility, and i18n scaffolding. 5 roadmap items shipped.

### Added — AI / RAG (R-60)

- **GUI chat panel** — `widget_chat_panel.ChatPanel` in right sidebar. Conversation
  bubbles (user/assistant), cited source links to bookmarks, threaded async ask
  via `CollectionChat.ask()`, clear conversation, placeholder text, auto-scroll.

### Added — GUI Surfaces (R-67)

- **Read Later sidebar section** — shows READ LATER header with count badge and
  up to 8 queued items. Click to select bookmark in tree. Refreshes with all data.
- **Flows sidebar section** — shows FLOWS header with count badge and up to 8
  research flows with icons. Refreshes with all data.

### Added — UI (R-17)

- **Category tree indentation** — categories with "/" separators now render with
  tree-like indentation. Leaf names shown with depth-based padding for visual
  hierarchy. No collapse/expand yet — flat indented list.

### Added — Accessibility (R-48)

- **F6 section cycling** — cycles keyboard focus between search, sidebar filters,
  bookmark tree, and chat panel. Standard Windows convention.
- **Theme-aware focus rings** — `make_keyboard_activatable` now uses
  `get_theme().accent_primary` for focus indicator instead of hardcoded blue.
- **Tab order** — sidebar filter buttons have `takefocus=1` via
  `make_keyboard_activatable`.

### Added — i18n (R-50)

- **gettext scaffolding** — `bookmark_organizer_pro/i18n.py` with `_()`,
  `ngettext()`, `setup_locale()`, and `_generate_pot()` for template extraction.
  `locale/` directory with translator README. No translations yet — infrastructure
  only.

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
