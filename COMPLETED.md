# Bookmark Organizer Pro — Completed Work

Append-only completion log. Detailed release notes remain in `CHANGELOG.md`;
this file tracks autonomous project-loop completions and roadmap closures.

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
