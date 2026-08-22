# Blocked Roadmap Items

Items moved here from ROADMAP.md because they have hard blockers preventing implementation.

## R-41 — tufup auto-update (apply stage)

**Blocker:** Applying downloaded updates requires design decisions about install isolation, rollback safety, user confirmation UI, and binary replacement of a running process. The non-mutating infrastructure (policy, check, download, staging, preflight, cleanup, planning) is complete through v6.6.27. The `apply_preflight()` method deliberately returns "update application is disabled in this release" as a blocker. Unblocking requires:

1. Safe binary extraction and replacement strategy (especially for running executables on Windows)
2. Rollback mechanism that can restore the previous version if the new one fails to start
3. User confirmation UI in the desktop app
4. End-to-end testing with real tufup repositories

**Source:** [S-28][S-88]

## R-02 — Web client (FastAPI + HTMX + PWA)

**Blocker:** XL effort (1-2 weeks). Requires designing a full FastAPI application with HTMX templates, authentication, PWA manifest, and service worker. While SQLite (R-31) is complete, the web client needs its own architecture, routing, template system, and security model. No partial implementation exists.

**Source:** [S-3][S-5][S-6][S-8][S-12]

## R-03 — Mobile PWA share-intent

**Blocker:** Depends on R-02 (web client). Android share-intent requires a served PWA with a Web Share Target API manifest entry. Cannot be implemented without the web client.

**Source:** [S-8][S-12]

## Publish browser extension to Chrome Web Store and Firefox AMO

**Blocker:** Requires $5 Chrome Web Store developer account, Mozilla AMO developer account, store listing screenshots, and a privacy policy URL. These are operator-gated actions that cannot be automated without credentials and human review.

**Source:** [S-5][S-3][S-8] (Karakeep CWS+AMO+Safari; Linkwarden CWS+AMO; Wallabag CWS+AMO)

## Extension native messaging for server-free save

**Blocker:** Depends on the browser extension being published to stores (or at minimum, stable enough for native messaging registration). Native messaging also requires platform-specific manifest registration (Windows registry keys, macOS/Linux JSON manifests) that varies by browser. Implementation is feasible but should follow store publication.

**Source:** S-67 (MDN native messaging), S-97 (Universal Bookmark Manager), S-110 (Zotero connectors)

## Chrome Prompt API integration for zero-cost extension categorization

**Blocker:** Requires Chrome 138+ with Gemini Nano on-device model (2.7-4 GB download, 16 GB RAM). Cannot be tested or validated without a Chrome 138+ browser environment with the Prompt API enabled. Implementation is straightforward once a test environment is available.

**Update 2026-08-21:** The Prompt API has been stable for extensions since Chrome 138 (2025-06) with the extensions channel at Chrome 148, so the test-environment blocker no longer applies. The remaining blocker is the hardware gate (16 GB RAM or >4 GB VRAM, 22 GB free disk on the profile volume, desktop only), which means it can only ever be an optional accelerator over the desktop app's own Ollama/fastembed path, never a default. Source: https://developer.chrome.com/docs/ai/prompt-api (fetched 2026-08-21).

**Source:** [S-130][S-135]

## First community translation (es or zh)

**Blocker:** 263 GUI strings are now wrapped with `_()` and the POT file is generated. However, creating the actual `.po` translation file requires a fluent translator for the target language. This is a human-gated task.

**Source:** [S-128]

## Publish the MCP server to the official registry

**Blocker:** `packaging/server.json` is written and validated by
`scripts/package_contract_audit.py` (name, version, and PyPI identifier are
asserted against the live app), but publishing requires operator-gated actions:
the package must first exist on PyPI under `bookmark-organizer-pro`, and
publishing to registry.modelcontextprotocol.io needs GitHub namespace
authentication for `io.github.sysadmindoc`. Neither can be automated here.

**Source:** https://modelcontextprotocol.io/registry/about; https://glama.ai/blog/2026-01-24-official-mcp-registry-serverjson-requirements

## Awesome-list and ecosystem submissions

**Blocker:** Requires submitting PRs to external repositories (awesome-bookmarking, awesome-mcp-servers, awesome-selfhosted). These are operator-gated actions requiring a GitHub account with permissions to fork and submit PRs to third-party repos, plus waiting for maintainer review.

**Source:** [S-145][S-154]

## MSIX packaging + SignPath Foundation code signing

**Blocker:** Requires operator to apply to SignPath Foundation for free OV code signing (signpath.org), create a Microsoft Partner Center developer account ($19 one-time fee), generate AppxManifest.xml with app identity, and set up MSIX build pipeline. These are account-gated actions.

**Source:** S-121 (research pass), signpath.org, 82phil.github.io MSIX guide

## MCP Apps exploration

**Blocker:** MCP Apps (SEP-1865) is part of the 2026-07-28 Release Candidate spec. The spec finalizes July 28, 2026. Neither the Python MCP SDK (v1.28) nor FastMCP (v3.4) support MCP Apps declarations yet. Implementation requires waiting for SDK support.

**Source:** [S-148]

## SQLite-vec as alternative to LanceDB

**Blocker:** Requires the `sqlite-vec` C extension (github.com/asg017/sqlite-vec) which needs compilation from source on most platforms. L-effort refactor of `services/vector_store.py` to add a third backend alongside LanceDB and in-memory JSON. Should be validated only when SQLite becomes the default storage backend.

**Source:** [S-130]

## Python 3.14 free-threaded mode for embedding generation

**Blocker:** Requires a Python 3.14t (free-threaded) CPython build for testing. Current CI matrix covers 3.10-3.13. The feature can only be validated after 3.14t is available in the CI environment and dependency ecosystem (fastembed, lancedb, etc.) confirms compatibility.

**Source:** [S-145][S-157]

## Re-enable the optional TUF updater dependency

**Blocker:** The latest `tufup` release (0.10.0) pins `tuf==4.0.*`, which is affected by GHSA-qp9x-wp8f-qgjj on Windows; the fix is in `tuf` 7.0.0, but that version is incompatible with tufup's published constraint. Keep updater runtime code dormant and exclude tufup from release extras until an upstream-compatible release exists.

**Source:** PyPI tufup 0.10.0 metadata; PyPI tuf 7.0.0; GHSA-qp9x-wp8f-qgjj

## Roadmap cleanup — 2026-08-10 — ROADMAP.md

**Blocked on:** The source roadmap marked this work as parked, optional, or dependent on external input.

Blocked items moved from the actionable roadmap:

- [ ] P3 — R-106: Prototype the 2026-07-28 MCP specification and MCP Apps
  Why: `Roadmap_Blocked.md` treats MCP Apps as draft-only, but the final 2026-07-28 specification is published and current FastMCP documentation exposes spec-level UI configuration.
  Evidence: MCP 2026-07-28 specification and security guidance; FastMCP changelog; `pyproject.toml` MCP/FastMCP ranges; `bookmark_organizer_pro/mcp_server.py`.
  Touches: dependency compatibility matrix, MCP server resources/tools, optional AppConfig UI, capability negotiation, fallback and security tests, then the stale blocked entry if validation succeeds.
  Acceptance: An isolated prototype runs the existing MCP contract suite against the minimum and latest allowed dependency versions, negotiates capabilities with both pre-2026-07-28 and final-spec clients, renders one read-only bookmark-search app without broadening scopes or exposing content unexpectedly, and documents a keep/reject decision with measured compatibility evidence.
  Complexity: L
  Note 2026-08-21: mcp SDK 2.0.0 shipped 2026-07-28 (stateless requests, `server/discover`, Tasks + MCP Apps extensions, Roots/Sampling/Logging deprecated on a 12-month clock; `FastMCP` class renamed `MCPServer`); fastmcp 4.0.0b3 (2026-08-14) targets SDK v2 but is still beta, and fastmcp 3.4.x pins `mcp<2`. Current pins (`mcp>=1.28,<2.0`, `fastmcp>=3.4.1,<4.0`) are correct until fastmcp 4 goes stable or a decision is made to target the raw SDK. Sources: https://github.com/modelcontextprotocol/python-sdk/releases; https://github.com/jlowin/fastmcp/releases.
