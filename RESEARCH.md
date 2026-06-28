# Research - Bookmark Organizer Pro

## Executive Summary
Bookmark Organizer Pro is a local-first Python/Tk desktop bookmark manager with a broad CLI, optional semantic search and MCP surfaces, a loopback REST API, a Manifest V3 browser extension, HTML snapshots, reader highlights, OPDS export, and extensive importer/exporter coverage. Its strongest current shape is not raw feature count but private desktop continuity: a user can capture, classify, search, preserve, read, review, and export a large bookmark library without adopting a hosted service. The highest-value direction is trust under scale: close unauthenticated read surfaces, make browser/API behavior executable rather than statically asserted, keep local-only distribution docs accurate, page large libraries consistently, expose preservation failures as recoverable work, add high-fidelity migration paths, and let MCP clients operate on reader/review data.

Top opportunities in priority order:
- Require authentication or an explicit read-only catalog token for `/opds` and `/opds2`.
- Add behavioral extension-to-API round-trip tests for save payloads, duplicates, and `read_later`.
- Remove stale workflow/distribution documentation now that `.github/` is absent and releases are local-only.
- Bring REST `/bookmarks` pagination/filter parity up to the MCP `list_bookmarks` contract.
- Add archive/snapshot failure records with retry/report UI.
- Add Firefox bookmark-backup JSON import to preserve tags/folders lost by HTML export.
- Expose reader highlights, due reviews, and review recording through MCP.

## Product Map
- Core workflows: browser/profile/service import; local categorization with 7,550 patterns across 48 categories; tag, duplicate, smart-collection, and health cleanup; keyword, semantic, hybrid, and natural-language search; snapshots, extracted text, reader highlights, SM-2 review, OPDS/Atom/JSON Feed/EPUB/Obsidian/ZIP export.
- User personas: local-first power organizer; researcher migrating from Pocket, Arc, Readwise, browser reading lists, or Wallabag; privacy-sensitive archivist; CLI/MCP user; browser-extension user who wants one-click capture into the desktop library.
- Platforms and distribution: Python 3.10+ Tk desktop on Windows/macOS/Linux, `bop` CLI, loopback API, optional MCP stdio/HTTP server, unpacked MV3 extension, PyInstaller/Nuitka packaging helpers, disabled-by-default TUF/tufup staging.
- Key integrations and data flows: extension and local tools call `BookmarkAPI`; CLI/MCP call manager/service modules; storage is JSON by default with optional SQLite; keyring-first token storage falls back to locked-down files; archives and support bundles stay under the app data directory.

## Competitive Landscape
- Karakeep: strong capture inbox, browser workflow, archiving, full-text search, and local/cloud model-assisted tagging. Learn from resilient capture and triage queues; avoid server/Docker as the default user journey.
- Linkwarden: strong preservation posture with web capture, collections, reader/highlight flows, and team-ready UI. Learn from explicit archive state and polished collection workflows; avoid making collaboration central to a single-user desktop app.
- Raindrop.io: commercial benchmark for calm UX, nested collections, duplicate/broken-link utilities, reminders, and broad platform coverage. Learn from consistent metadata and recovery affordances; avoid cloud lock-in and paywalled essentials.
- Readwise Reader: commercial benchmark for read-later queues, highlights, review loops, feed ingestion, and migration. Learn from queue ergonomics and review states; avoid turning the app into a hosted content inbox.
- Readeck and ArchiveBox: preservation-focused tools with clear capture artifacts, archive status, and portable exports. Learn from visible preservation failures and retryability; avoid heavy archival requirements that slow normal saves.
- linkding, Shiori, buku, Shaarli, and Floccus: smaller OSS tools that value speed, simple deployment, CLI/browser capture, XBEL/WebDAV/Git sync, and durable export. Learn from low-friction interop; avoid hiding core list/search actions behind feature density.
- Obsidian Web Clipper and adjacent note tools: strong site-specific extraction and template patterns. Learn from domain templates for richer metadata; avoid unbounded scraping rules that become hard to test.

## Security, Privacy, and Reliability
- Verified risk: `bookmark_organizer_pro/services/api.py:176` handles `/opds` and `/opds2` before `_check_auth()` at `bookmark_organizer_pro/services/api.py:214`, so local HTTP clients can read catalog data without the bearer token required for `/bookmarks`, `/search`, `/stats`, `/categories`, `/tags`, and `/digest`.
- Verified gap: `tests/test_browser_extension.py` mostly asserts source strings, while the important boundary is behavioral: `browser-extension/popup.js`, `browser-extension/sidepanel.js`, and `browser-extension/background.js` payloads must round-trip through `BookmarkAPI.do_POST()` into persisted `Bookmark` fields.
- Verified gap: `browser-extension/background.js:39` through `browser-extension/background.js:63` returns `false` on failed context-menu quick-save without a user-visible retry path. This is already represented by the existing roadmap item for extension pending-save queue and retry surface; do not duplicate it.
- Verified drift: `.github/` is absent, but `docs/REPOSITORY_STRUCTURE.md:16` still documents `.github/workflows/` as durable release automation. Existing roadmap items also reference workflow paths that no longer exist; future implementation should update or close those items when touched.
- Verified partial implementation: `scripts/visual_regression_smoke.py` and `tests/test_visual_regression_smoke.py` now exist, so the existing roadmap item for visual regression screenshots should be revalidated before further work.
- Verified reliability gap: `bookmark_organizer_pro/services/snapshot.py:51` through `bookmark_organizer_pro/services/snapshot.py:70` tries multiple backends but collapses user-facing failure into `"All snapshot backends failed"`, losing backend-level diagnostics that preservation tools usually surface.
- Existing guardrails to preserve: SSRF/private URL checks, request body caps, keyring-first secrets, locked-down token fallback files, `defusedxml`, safepoints, redacted support bundles, local-only MCP HTTP bind protection, and optional dependency degradation.

## Architecture Assessment
- API boundary: `BookmarkAPI` should share request filtering/pagination semantics with MCP `t_list_bookmarks()` instead of maintaining a narrower `/bookmarks?limit=` contract. Touch `bookmark_organizer_pro/services/api.py`, extension list views, and API tests.
- Extension boundary: static source checks should be backed by fixtures that exercise real POSTs and duplicate handling. Touch `tests/test_browser_extension.py`, `tests/test_core.py`, and possibly a small test helper for `BookmarkAPI`.
- Preservation boundary: `SnapshotArchiver` should return structured backend attempts and persist last failure state on the bookmark or sidecar report. Touch `bookmark_organizer_pro/services/snapshot.py`, `bookmark_organizer_pro/services/auto_snapshot.py`, dashboard/tools UI, and service tests.
- Reader/MCP boundary: `ReaderAnnotationStore` and SM-2 review state are mature in services/tests, but MCP lacks list/export/review operations for highlights. Touch `bookmark_organizer_pro/mcp_server.py`, `bookmark_organizer_pro/services/mcp_auth.py`, and `tests/test_mcp_tools.py`.
- Migration boundary: import breadth is strong, but Firefox bookmark-backup JSON can preserve tags and folder metadata that Netscape HTML loses. Touch `bookmark_organizer_pro/importers.py`, import/export UI, CLI import routing, and importer tests.
- Documentation boundary: docs should reflect local-only verification and release operations. Touch `docs/REPOSITORY_STRUCTURE.md`, README release/build sections, and any roadmap item evidence that points to removed workflow files.

## Rejected Ideas
- Mandatory hosted sync or accounts from Linkwarden/Raindrop: rejected because they conflict with the local-first desktop posture; optional XBEL/WebDAV/Git interop remains the better path and is already under consideration.
- Docker/server-first deployment from Karakeep, Linkwarden, and ArchiveBox: rejected because setup friction is the opposite of this app's native desktop advantage.
- Native mobile/PWA work now: rejected because `Roadmap_Blocked.md` already gates web/PWA architecture decisions.
- Native browser messaging now: rejected because `Roadmap_Blocked.md` already gates it on extension publication and host registration.
- Full Electron/Tauri rewrite: rejected because the current Python/Tk codebase has working tests, packaging helpers, local storage, and service modules.
- Chrome Prompt API integration now: rejected because `Roadmap_Blocked.md` already marks it gated by browser/API maturity and local hardware validation.
- Multi-user/team workspaces: rejected because they would add auth, roles, sharing, and conflict-resolution complexity without improving the single-user local library.
- Auto-delete duplicate bookmarks: rejected because destructive cleanup should remain reviewable with safepoints and explicit recovery.

## Sources
OSS competitors:
- https://github.com/karakeep-app/karakeep
- https://github.com/linkwarden/linkwarden
- https://github.com/sissbruecker/linkding
- https://github.com/go-shiori/shiori
- https://github.com/wallabag/wallabag
- https://github.com/ArchiveBox/ArchiveBox
- https://codeberg.org/readeck/readeck
- https://github.com/floccusaddon/floccus
- https://github.com/jarun/buku
- https://github.com/shaarli/Shaarli

Commercial, adjacent, and community:
- https://raindrop.io/
- https://readwise.io/read
- https://obsidian.md/clipper
- https://blog.mozilla.org/en/mozilla/update-on-pocket/
- https://support.mozilla.org/en-US/kb/exporting-your-pocket-list
- https://github.com/dogancelik/awesome-bookmarking
- https://github.com/awesome-selfhosted/awesome-selfhosted
- https://news.ycombinator.com/item?id=42648006

Standards and platform:
- https://developer.chrome.com/docs/extensions/reference/api/readingList
- https://developer.chrome.com/docs/extensions/reference/api/sidePanel
- https://developer.chrome.com/docs/extensions/reference/api/storage
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging
- https://modelcontextprotocol.io/specification/
- https://www.w3.org/TR/WCAG22/
- https://www.w3.org/WAI/ARIA/apg/

Dependencies, security, and techniques:
- https://github.com/pypa/pip-audit
- https://requests.readthedocs.io/en/latest/community/updates/
- https://gofastmcp.com/changelog
- https://cryptography.io/en/latest/changelog/
- https://lancedb.github.io/lancedb/
- https://github.com/qdrant/fastembed
- https://trafilatura.readthedocs.io/

## Open Questions
None that block prioritization. Blocked platform and publication decisions are already tracked in `Roadmap_Blocked.md`.
