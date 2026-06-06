# Bookmark Organizer Pro — Completed Work

Append-only completion log. Detailed release notes remain in `CHANGELOG.md`;
this file tracks autonomous project-loop completions and roadmap closures.

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
