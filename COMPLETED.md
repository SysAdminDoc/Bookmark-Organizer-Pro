# Bookmark Organizer Pro — Completed Work

Append-only completion log. Detailed release notes remain in `CHANGELOG.md`;
this file tracks autonomous project-loop completions and roadmap closures.

## 2026-06-06 — v6.6.13 OPDS Loopback Serving

- Completed R-26: local API now serves OPDS 1.2 acquisition feeds at `GET /opds`.
- Added tag/category/title/limit query filters for catalog clients.
- Split OPDS rendering from file export so CLI export and HTTP serving share one
  XML generation path.
- Added API route coverage for OPDS content type, PDF media inference, and
  open-access acquisition links.
- Verification: compileall passed, focused OPDS/API/release metadata tests
  passed with 16 tests, and the full suite passed with 322 tests.

## 2026-06-06 — v6.6.12 OPDS Export Foundation

- Advanced R-26: added OPDS 1.2 acquisition feed export for bookmark
  collections.
- Added `opds-export` CLI command with output path, title, tag filtering, and
  optional self catalog URL.
- Added EPUB/PDF/HTML media type inference for open-access acquisition links.
- Verified official OPDS guidance: 1.x is Atom-based and OPDS 2.0 is the newer
  JSON-LD/manifest line, so the first BOP slice targets broad OPDS 1.2 client
  compatibility.
- Verification: compileall passed, focused OPDS/release metadata tests passed
  with 15 tests, CLI OPDS export smoke passed, and the full suite passed with
  321 tests.

## 2026-06-06 — v6.6.11 Updater Bootstrap Gates

- Advanced R-41: added `docs/distribution/updater-bootstrap.md` covering
  update policy files, trusted `root.json` placement, optional dependency
  install, HTTPS repository configuration, tufup target naming, and repository
  owner checklist.
- Added explicit `updates download` and `updates apply` CLI gates that refuse
  mutating update actions in this release.
- Added tests for the mutation gates and bootstrap documentation invariants.
- Verification: compileall passed, focused CLI/packaging/release metadata tests
  passed with 14 tests, both refusal-gate CLI smokes passed, and the full suite
  passed with 319 tests.

## 2026-06-06 — v6.6.10 Updater Availability Check

- Advanced R-41: added a non-applying tufup client adapter for trusted metadata
  availability checks.
- Added local trusted-root readiness: checks require `root.json` under the
  updater metadata cache before the tufup client is constructed.
- Added structured `UpdateCheckResult` output for available, no-update,
  not-ready, and failed checks.
- Updated `updates check` to report adapter results while keeping download/apply
  unavailable.
- Verified tufup 0.10.0's installed API exposes `Client.check_for_updates()`
  and pins `tuf==4.0.*` internally.
- Verification: compileall passed, focused updater/CLI/release metadata tests
  passed with 19 tests, `updates check` reported disabled/not-ready correctly,
  and the full suite passed with 317 tests.

## 2026-06-06 — v6.6.9 Updater Policy Foundation

- Advanced R-41: added an optional `updates` dependency extra for tufup 0.10.x.
- Added a disabled-by-default update policy service that persists HTTPS
  metadata/target repository URLs, channel, prerelease preference, and readiness
  status without downloading or applying binaries.
- Added `updates status`, `updates check`, and `updates configure` CLI commands.
- Verified live package availability: `tufup` latest is 0.10.0 and `tuf` latest
  is 7.0.0.
- Verification: compileall passed, focused updater/CLI/release metadata tests
  passed with 17 tests, and the full suite passed with 315 tests.

## 2026-06-06 — v6.6.8 Nuitka Compile Smoke

- Completed the local compile-smoke checkpoint for R-40.
- Added `--target smoke` to `packaging/nuitka_build.py`, preserving the default
  app target while enabling a small console artifact for compiler validation.
- Added `packaging/nuitka_smoke.py` with app-version output and tests that keep
  its metadata in sync with the application constants.
- Confirmed the package-import smoke attempt was too broad because it compiled
  the app dependency graph; the final self-contained target compiled 6 C files.
- Verification: smoke entrypoint source run passed, smoke dry-run passed,
  standalone Nuitka smoke compile completed, generated artifact `--version`
  passed, compileall passed, targeted packaging/release metadata tests passed
  with 11 tests, and the full suite passed with 309 tests.

## 2026-06-06 — v6.6.7 Nuitka Build Controls

- Advanced R-40: installed and verified Nuitka 4.1.2 in the active Python 3.12
  environment.
- Verified Nuitka sees MSVC `cl 14.3`.
- Attempted a full-app standalone compile; it exceeded a 15-minute smoke
  timeout and the leftover compiler process tree was stopped.
- Added `--jobs` support to `packaging/nuitka_build.py`, defaulting to a
  conservative `--jobs=4` with CLI override.
- Verification: Nuitka version check passed, throttled dry-run passed,
  compileall passed, targeted packaging/release metadata tests passed with
  9 tests, and the full suite passed with 307 tests.

## 2026-06-06 — v6.6.6 Nuitka Build Path

- Advanced R-40: added `packaging/nuitka_build.py` to generate a reproducible
  Nuitka build command for onefile or standalone output.
- Included Tkinter plugin, package inclusion, assets, Windows icon/no-console
  flags, version/product metadata, and compilation report output.
- Added an optional `nuitka` package extra pinned to Nuitka 4.1+.
- Added tests for command generation, dry-run behavior, and dependency
  declaration.
- Verification: Nuitka dry-run passed, compileall passed, targeted
  packaging/release metadata tests passed with 8 tests, and the full suite
  passed with 306 tests.
- Remaining R-40 work: install/verify Nuitka and perform an actual compile
  smoke on the local toolchain.

## 2026-06-06 — v6.6.5 SQLite Runtime Selection

- Completed R-31: `BookmarkManager` now supports opt-in SQLite runtime storage
  through a constructor argument, `.sqlite`/`.db` file paths, or
  `BOOKMARK_STORAGE_BACKEND=sqlite`.
- Preserved JSON as the default runtime backend.
- Fixed SQLite storage to preserve unsigned 64-bit bookmark IDs by storing the
  indexed ID column as text while preserving integer IDs in payload JSON.
- Added manager-level backend selection tests and unsigned bookmark ID
  persistence coverage.
- Verification: compileall passed, targeted manager/storage/CLI/browser-extension
  tests passed with 32 tests, and the full suite passed with 303 tests.

## 2026-06-06 — v6.6.4 SQLite Migration Foundation

- Advanced R-31: added a WAL-enabled `SQLiteStorageManager` with the same
  `load()`/`save()` shape as the existing JSON storage manager.
- Added `sqlite-migrate [--source JSON] [--dest DB]` to copy JSON bookmarks to
  SQLite without changing the default JSON workflow.
- Added SQLite indexes for URL, category, created-at, and modified-at fields
  while preserving full bookmark payload JSON for compatibility.
- Added storage and CLI tests for WAL mode, round-trip fidelity, corrupt-row
  tolerance, migration, and command parsing.
- Verification: compileall passed, targeted storage/CLI/browser-extension tests
  passed with 28 tests, and the full suite passed with 299 tests.
- Remaining R-31 work: add a runtime selection/config path before using SQLite
  as an active app backend.

## 2026-06-06 — v6.6.3 MCP Streamable HTTP

- Completed R-58: added an opt-in `mcp-http-server` command for FastMCP
  Streamable HTTP with stateless HTTP enabled.
- Added `--host`, `--port`, and `--path` CLI options with loopback defaults.
- Added `Mcp-Method` and `Mcp-Name` validation middleware that rejects header
  mismatches before the JSON-RPC body reaches FastMCP.
- Added tests for command parsing, HTTP runner options, header mismatch
  rejection, and body replay.
- Verification: compileall passed, targeted MCP/CLI/browser-extension tests
  passed with 63 tests, and the full suite passed with 294 tests.

## 2026-06-06 — v6.6.2 MCP Stateless Readiness

- Advanced R-58: enabled MCP SDK stateless mode for raw SDK and FastMCP stdio
  transports.
- Added cache hints to `tools/list` results in both MCP paths.
- Added read/write/destructive/idempotent/open-world annotations and stateless
  metadata to raw SDK and FastMCP tool catalogs.
- Cleaned MCP server module documentation so it stays client-neutral.
- Verification: compileall passed, targeted MCP/browser-extension tests passed
  with 29 tests, and the full suite passed with 288 tests.
- Remaining R-58 work: HTTP Streamable transport header validation is still
  open because this app currently exposes MCP through stdio.

## 2026-06-06 — v6.6.1 FastMCP 3.4 Compatibility

- Completed R-59: bumped optional MCP dependency floors to `fastmcp>=3.4,<4`
  and `mcp>=1.24,<2`.
- Verified `_build_fastmcp_server()` against FastMCP 3.4.2 and MCP 1.27.2.
- Added PyInstaller hidden import coverage for `fastmcp`.
- Added MCP dependency metadata and FastMCP builder compatibility tests.
- Verification: compileall passed, targeted MCP/browser-extension tests passed
  with 27 tests, and the full suite passed with 286 tests.

## 2026-06-06 — v6.6.0 List Virtualization

- Completed R-16: replaced the main bookmark list with a `tksheet`-backed
  virtual table while preserving selection, context menus, sorting, zoom, row
  styling, and the legacy Treeview fallback.
- Fixed sidebar/chat bookmark deep links so they select rows by bookmark ID.
- Fixed service regressions found during verification: NL query heuristic
  compatibility, dead-link result persistence compatibility, batch-save
  coalescing, and the snapshot archiver `archive()` alias.
- Added release metadata sync coverage for pyproject, extension manifest,
  PyInstaller spec, and Windows version metadata.
- Synchronized public version metadata to v6.6.0 across runtime constants,
  package metadata, README badge, extension manifest, PyInstaller spec, and
  Windows version resources.
- Verification: compileall passed, tksheet widget smoke passed, targeted
  extension/CLI tests passed with 33 tests, targeted service regressions passed
  with 8 tests, and the full suite passed with 284 tests.

## 2026-06-06 — v6.4.1 CLI Reliability and Planning Sync

- Fixed BUG-13: `scan --hours N` now honors the documented space-separated
  argument form, keeps `--hours=N` compatibility, and rejects invalid values
  before starting a dead-link scan.
- Fixed BUG-14: added the missing `bookmark_organizer_pro.cli:main` entrypoint
  used by the `bop` console script and module execution.
- Added CLI regression tests for both accepted `scan --hours` syntaxes,
  invalid value handling, and the CLI entrypoint.
- Synchronized public version metadata to v6.4.1 across package metadata,
  runtime constants, PyInstaller spec/version resources, README badges, and
  About dialog Python-version text.
- Consolidated the root research feature plan into `docs/research/` and
  reconciled roadmap status markers for already-shipped v6.3 work.

## 2026-06-06 — v6.4.2 Browser Extension MVP

- Added the first R-01 browser-extension slice under `browser-extension/`:
  Manifest V3 manifest, popup, options page, shared dark styling, and local API
  save flow for the active HTTP/HTTPS tab.
- Added `api-server [--port N]` to keep the existing local HTTP API available
  for extension and bookmarklet workflows.
- Added static extension tests and API-server CLI tests.
- Left R-01 marked in progress because native messaging, packaged browser
  validation, and offline category/tag suggestions remain open.
