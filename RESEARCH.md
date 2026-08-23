# Research: Bookmark Organizer Pro

Date: 2026-08-23. Replaces all prior research.

Confidence labels: **Verified** means reproduced locally or stated by a primary source. **Likely** means the recommendation follows from multiple verified signals but has not been tested with production user data. **Needs live validation** marks the one opportunity whose exact UI demand comes from community reports. `Learn` and `Avoid` lines are fit decisions derived from the preceding verified evidence, not factual claims about shipped behavior.

## Executive Summary

**Verified.** Bookmark Organizer Pro v6.16.0 is a local-first Windows research manager with a Tkinter desktop, 67 CLI commands, a loopback REST API, 34 MCP tools, Chromium and Firefox extensions, offline archives, reader annotations, broad migration support, and JSON or SQLite storage (`README.md`, `bookmark_organizer_pro/app.py`, `bookmark_organizer_pro/cli.py`, `bookmark_organizer_pro/mcp_server.py`). Its strongest current shape is the combination of local ownership, capture depth, recovery controls, and automation surfaces. None of the surveyed products matched that full combination. The highest-value direction is to finish trust contracts that are present but incomplete, then expose existing capabilities consistently. The top opportunities in priority order are: annotation CSV formula neutralization; dependency diagnostics that run before imports fail; persistent trash across desktop, CLI, REST, and MCP; a lossless and visible extension retry journal; disk-backed streaming migration preflights; process-wide test isolation and executable theme checks; revision-bound MCP content paging; safe SQLite activation; portable annotations; and actionable dead-link review.

## Product Map

### Core workflows

- **Verified.** Capture URLs from desktop forms, browser popup, context menu, side panel, Chrome Reading List, file imports, and competitor migrations (`bookmark_organizer_pro/app_mixins/bookmark_crud.py`, `browser-extension/`, `bookmark_organizer_pro/services/batch_import.py`, `bookmark_organizer_pro/services/migration.py`).
- **Verified.** Organize with categories, tags, rules, tag linting, duplicate review, smart collections, structured search, full-text search, semantic search, and hybrid search (`bookmark_organizer_pro/services/organization_rules.py`, `bookmark_organizer_pro/services/tag_linter.py`, `bookmark_organizer_pro/search.py`, `bookmark_organizer_pro/services/vector_store.py`).
- **Verified.** Preserve and read through sanitized snapshots, capture fallbacks, extracted text, reader progress, resilient highlights, snapshot history, feeds, and opt-in transcripts (`bookmark_organizer_pro/services/snapshot.py`, `bookmark_organizer_pro/services/reader_annotations.py`, `bookmark_organizer_pro/services/snapshot_history.py`).
- **Verified.** Diagnose, recover, and transfer data through safepoints, rolling backups, recovery bundles, migration preflights, diagnostics previews, and broad export formats (`bookmark_organizer_pro/core/storage_manager.py`, `bookmark_organizer_pro/services/recovery_bundle.py`, `bookmark_organizer_pro/services/local_state.py`).
- **Verified.** Automate the same library through the CLI, scoped loopback REST credentials, MCP, and the browser extension (`bookmark_organizer_pro/cli.py`, `bookmark_organizer_pro/services/api.py`, `bookmark_organizer_pro/services/mcp_auth.py`).

### User personas

- **Likely.** Researchers and knowledge workers who need durable sources, quotations, citations, and local retrieval. This follows from the reader, highlights, snapshots, Zotero, Obsidian, EPUB, and OPDS workflows (`bookmark_organizer_pro/services/reader_annotations.py`, `bookmark_organizer_pro/services/zotero_interop.py`, `bookmark_organizer_pro/services/obsidian_export.py`).
- **Likely.** Privacy-conscious users who want local files, explicit external-service choices, and recoverable changes (`README.md`, `bookmark_organizer_pro/services/mcp_auth.py`, `bookmark_organizer_pro/services/private_files.py`, `bookmark_organizer_pro/core/storage_manager.py`).
- **Verified.** CLI and agent users who depend on deterministic search, scoped credentials, and machine-readable operations (`bookmark_organizer_pro/cli.py`, `bookmark_organizer_pro/mcp_server.py`, `bookmark_organizer_pro/services/mcp_auth.py`).
- **Likely.** Users leaving Pocket, Omnivore, Readwise, Raindrop, Linkwarden, or Karakeep who need a fidelity report before committing a migration (`bookmark_organizer_pro/importers_extra.py`, `bookmark_organizer_pro/services/migration.py`).

### Platforms and distribution

- **Verified.** The supported product is a Windows desktop application with a locally built PyInstaller artifact; source execution supports Python 3.10 or newer (`README.md`, `pyproject.toml`, `packaging/release_manifest.json`, `scripts/build_release.py`).
- **Verified.** The extension targets Chromium Manifest V3 and Firefox, with a Chrome side panel and Firefox sidebar (`browser-extension/manifest.json`, `browser-extension/manifest.firefox.json`).
- **Verified.** Storage is JSON by default and SQLite by explicit selection. The API binds to loopback only (`bookmark_organizer_pro/managers/bookmarks.py`, `bookmark_organizer_pro/services/api.py`).

### Key integrations and data flows

- **Verified.** Browser capture sends bounded data to the loopback API, then the manager persists the bookmark while snapshot, extraction, timeline, and vector services attach derived artifacts (`browser-extension/shared.js`, `bookmark_organizer_pro/services/api.py`, `bookmark_organizer_pro/services/ingest.py`, `bookmark_organizer_pro/services/processing_timeline.py`).
- **Verified.** AI providers are optional and pass untrusted page evidence through bounded citation isolation before model use (`bookmark_organizer_pro/ai.py`, `bookmark_organizer_pro/services/rag_chat.py`, `bookmark_organizer_pro/services/citation_summarizer.py`).
- **Verified.** Export routes include HTML, JSON, CSV, Markdown, text, OPDS, EPUB, Obsidian, Zotero, portable ZIP, and recovery bundles (`bookmark_organizer_pro/managers/bookmarks.py`, `bookmark_organizer_pro/services/feed_export.py`, `bookmark_organizer_pro/services/epub_export.py`, `bookmark_organizer_pro/services/recovery_bundle.py`).

## Competitive Landscape

### Karakeep

- **Verified.** [Karakeep](https://github.com/karakeep-app/karakeep) is the closest overall feature match. Its 0.33.1 release added paragraph-paged MCP content, Reader View suitability checks, semantic search, and offline mobile work; 0.33.2 fixed memory failures from oversized SingleFile archives.
- **Learn.** Adopt revision-bound paragraph paging, extraction suitability signals, and storage visibility.
- **Avoid.** Do not copy its hosted and mobile operating burden or unconstrained AI tag behavior; issues 1266, 1748, 2344, and 2893 document tag and memory pain.

### Linkwarden

- **Verified.** [Linkwarden](https://github.com/linkwarden/linkwarden) is the strongest preservation and collaboration benchmark, with polished archive presentation and shared collections.
- **Learn.** Preserve imported archive provenance and consider real outlinks only after the current trust work is complete.
- **Avoid.** Shared accounts, server deployment, and synchronous archive behavior conflict with the local single-user model; issues 587, 1597, and 1747 also show export, tag, and DNS-pressure costs.

### Grimoire

- **Verified.** [Grimoire](https://github.com/goniszewski/grimoire) is the nearest architectural comparison: local SQLite, semantic and hybrid retrieval, AI review, checksummed backups, MCP, and signed native archives.
- **Learn.** Keep storage and service boundaries small enough to reason about, especially around CLI and MCP composition.
- **Avoid.** S3 and broader sync are not needed for the current product promise.

### linkding

- **Verified.** [linkding](https://github.com/sissbruecker/linkding) remains the speed and restraint benchmark. Its dead-link request has 40 reactions and its category and AI-tag requests have similarly durable demand.
- **Learn.** Make routine cleanup fast, concrete, and reversible.
- **Avoid.** Do not flatten BOP into a minimal list app or reopen organization features that are already stronger locally.

### Readeck

- **Verified.** [Readeck](https://readeck.org/en/blog/202512-2026-roadmap/) is the strongest portable reading-artifact benchmark, with immutable per-bookmark ZIPs, selected-text clipping, OPDS, EPUB, and migration support.
- **Learn.** Treat highlights and captured article state as portable records, not incidental notes.
- **Avoid.** Do not replace BOP's richer organization and automation model with a read-later-only workflow.

### ArchiveBox

- **Verified.** [ArchiveBox](https://github.com/ArchiveBox/ArchiveBox) leads on forensic capture depth and replay.
- **Learn.** Surface archive provenance, size, MIME family, and capture backend clearly.
- **Avoid.** Full WARC or WACZ replay would add a specialist stack, larger artifacts, and more attack surface without repository demand.

### Raindrop.io

- **Verified.** [Raindrop.io](https://help.raindrop.io/changelog/web) is the commercial organization and MCP benchmark. Its MCP exposes misplaced and mistagged audits, semantic tag search, and tag merges.
- **Learn.** Expose BOP's deterministic tag linter and organization-rule suggestions as read-only MCP previews first.
- **Avoid.** Cloud storage, shared workspaces, and default remote processing would erase the local ownership advantage.

### Readwise Reader

- **Verified.** [Readwise Reader](https://docs.readwise.io/changelog) leads in reading polish, highlight review, export status, and MCP document access.
- **Learn.** Make long content pageable and keep highlight interchange loss-aware.
- **Avoid.** A full hosted reader, audio pipeline, or PDF annotation suite would change the product and add large dependencies.

### start.me

- **Verified.** [start.me](https://support.start.me/en/articles/9182823-broken-link-checker-pro) turns broken-link detection into actions: retry, mark good, edit, search for an alternative, visit the domain, or delete.
- **Learn.** Replace BOP's static dead-link report with a persistent remediation queue that can show an archived copy before removal.
- **Avoid.** Dashboard and portal features unrelated to bookmark repair add no value here.

### LinkAce

- **Verified.** [LinkAce 2.6.1](https://github.com/Kovah/LinkAce/releases/tag/v2.6.1) fixed CSV formula injection, SSRF, and stored XSS defects.
- **Learn.** Apply spreadsheet neutralization to every CSV surface, including annotations.
- **Avoid.** Multi-user authorization and public sharing increase risk without helping BOP's single-user desktop workflow.

### Hypothesis and Obsidian Web Clipper

- **Verified.** [Hypothesis](https://web.hypothes.is/blog/hypothesis-for-web-developers/) combines quote and position selectors for resilient anchoring; [Obsidian Web Clipper](https://github.com/obsidianmd/obsidian-clipper) treats highlights and selections as first-class capture data.
- **Learn.** Map BOP's existing exact, prefix, suffix, and position fields to W3C Web Annotation JSON-LD and capture browser selections as highlights.
- **Avoid.** An arbitrary page-script or executable plugin system would weaken the bounded local security model.

### SingleFile

- **Verified.** [SingleFile](https://github.com/gildas-lormeau/SingleFile) remains the capture-fidelity benchmark and is already integrated.
- **Learn.** Preserve its capture provenance and show storage cost before users need emergency cleanup.
- **Avoid.** Never remove size, media, MIME, redirect, or timeout bounds in pursuit of perfect capture.

## Reported Issues

- **Verified.** The public [issue tracker](https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/issues) has 0 open and 0 closed issues. The [pull request tracker](https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/pulls) also has 0 entries. No roadmap item can claim user-reported demand from this repository.
- **Verified.** [Discussion 1](https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/discussions/1) and [Discussion 2](https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/discussions/2) are maintainer-authored posts with no comments. Their count of 62 CLI commands is stale against the current 67, so they are not feature-demand evidence.
- **Verified.** There are no parent-repository reports because this repository is not a fork. Current roadmap defects come from local reproduction, source tracing, primary standards, and comparable-product evidence.

## Security, Privacy, and Reliability

- **Verified.** Annotation CSV export writes bookmark titles, URLs, highlight text, tags, and notes directly through `csv.DictWriter` (`bookmark_organizer_pro/services/reader_annotations.py:1143`). Ordinary bookmark CSV paths call `csv_safe_cell` (`bookmark_organizer_pro/managers/bookmarks.py:1274`, `bookmark_organizer_pro/ui/workflow_selective_export.py:355`). A crafted annotation can therefore become a spreadsheet formula. LinkAce 2.6.1 confirms this class of defect is exploitable in bookmark exports.
- **Verified.** The README claims recoverable trash, and `BookmarkManager` contains isolated trash helpers, but desktop `DeleteBookmarksCommand`, CLI, REST, MCP, and maintenance paths call permanent deletion instead (`README.md:433`, `bookmark_organizer_pro/commands.py:160`, `bookmark_organizer_pro/cli.py:976`, `bookmark_organizer_pro/services/api.py:1206`, `bookmark_organizer_pro/mcp_server.py:1424`). The helpers also overload `is_archived`, conflating archive state with deletion (`bookmark_organizer_pro/managers/bookmarks.py:943`).
- **Verified.** The extension retry journal silently keeps only the newest 50 items (`browser-extension/shared.js:696`). Background context-menu saves ignore the result (`browser-extension/background.js:122`), so prolonged API downtime can discard old captures without visible failure.
- **Verified.** Competitor migration preflight reads the source once for hashing and again for parsing, while JSON and CSV parsers materialize the full export and the complete converted plan (`bookmark_organizer_pro/services/migration.py:40`, `bookmark_organizer_pro/services/migration.py:57`, `bookmark_organizer_pro/services/migration.py:216`). A bounded design needs a hashing stream, incremental CSV or JSON parsing, and a disk-backed plan. [ijson 3.5.1](https://pypi.org/project/ijson/) provides Python 3.10 through 3.14 Windows wheels and iterative object parsing.
- **Verified.** The first-run banner says data stays local unless an AI key is configured, but non-AI metadata, favicon, link-check, snapshot, feed, transcript, Wayback, and update paths can make network requests (`bookmark_organizer_pro/launcher.py:65`, `README.md:627`). The individual features are bounded or opt-in; the absolute banner is still inaccurate.
- **Verified.** Several test classes redirect `BOOKMARK_DATA_DIR`, but there is no process-wide pre-import isolation. `tests/__init__.py` only snapshots the extension-origin registry after a test, so other default paths can still touch user data.
- **Verified.** The 2026-08-23 local baseline passed 1,111 tests with 3 skips and 600 subtests. Ruff F and E9 checks, dependency vulnerability audit, package contracts, gettext, completions, and gitleaks were clean. The suite emitted 58 LanceDB deprecation warnings from `table_names()` at `bookmark_organizer_pro/services/vector_store.py:184`.

## Architecture Assessment

- **Verified.** The documented dependency-repair path cannot run in an incomplete interpreter. `main.py:58` imports `bookmark_organizer_pro.constants`, which executes eager facades in `bookmark_organizer_pro/__init__.py` and `bookmark_organizer_pro/core/__init__.py` before `launcher.py` reaches `DependencyManager`. On 2026-08-23, `python -c "import bookmark_organizer_pro.constants"` failed on missing `regex`; `bookmark_organizer_pro/utils/dependencies.py` checks only BeautifulSoup, requests, and Pillow despite ten required packages in `pyproject.toml`.
- **Verified.** Duplicate-add outcomes diverge by surface. `BookmarkManager.add_bookmark_clean()` returns the existing row, but desktop and CLI report a new bookmark and the desktop starts a favicon fetch (`bookmark_organizer_pro/managers/bookmarks.py:1116`, `bookmark_organizer_pro/app_mixins/bookmark_crud.py:35`, `bookmark_organizer_pro/cli.py:945`). REST and MCP already return an explicit duplicate outcome (`bookmark_organizer_pro/services/api.py:1090`, `bookmark_organizer_pro/mcp_server.py:728`).
- **Verified.** MCP `get_extracted_text` returns the entire derived file with no size, cursor, paragraph boundary, or content revision (`bookmark_organizer_pro/mcp_server.py:762`). Karakeep 0.33.1 demonstrates the expected bounded contract.
- **Verified.** The annotation store already has exact, prefix, suffix, position, source digest, and orphan recovery, but import and export use a private schema (`bookmark_organizer_pro/services/reader_annotations.py:30`, `bookmark_organizer_pro/services/reader_annotations.py:961`, `bookmark_organizer_pro/services/reader_annotations.py:1205`). It is a close fit for the W3C Web Annotation model.
- **Verified.** LanceDB FTS exposes language and stopword settings but not `base_tokenizer`; analyzer settings are not part of an index generation contract (`bookmark_organizer_pro/services/vector_store.py:665`). Current LanceDB supports ICU, Jieba, Lindera, raw, whitespace, and n-gram tokenizers.
- **Verified.** Desktop dead-link results and smart collections are report-only (`bookmark_organizer_pro/app_mixins/tools.py:1206`, `bookmark_organizer_pro/app_mixins/tools.py:1267`). Search history and saved-search CRUD exist only in memory and have no production persistence or management surface (`bookmark_organizer_pro/search.py:656`).
- **Verified.** The desktop SQLite migration writes a database, then instructs users to set an environment variable or CLI flag; an existing destination requires manual renaming (`bookmark_organizer_pro/app_mixins/tools.py:1525`). It does not activate or roll back the backend choice.
- **Verified.** The largest maintenance seams are `bookmark_organizer_pro/cli.py`, `bookmark_organizer_pro/mcp_server.py`, `bookmark_organizer_pro/app_mixins/tools.py`, `bookmark_organizer_pro/services/api.py`, and `bookmark_organizer_pro/managers/bookmarks.py`. `docs/ARCHITECTURE.md` still calls the now-thin `main.py` the large legacy UI entry point.
- **Verified.** Recent commit history repeatedly fixed gates that passed without observing the intended behavior. Current tests now contain negative controls for Firefox consent, snapshot ownership, retired passphrase backups, and generated product counts (`tests/test_packaging.py:360`, `tests/test_browser_extension.py:1546`, `tests/test_services.py:2806`). Several desktop smoke paths still call `set_theme()` without checking its result (`scripts/visual_regression_smoke.py:776`, `:822`, `:851`, `:956`), so theme activation remains the narrow open gate defect.
- **Verified.** Accessibility, theme, localization, and packaging gates currently pass (`tests/test_accessibility_contracts.py`, `scripts/visual_regression_smoke.py`, `scripts/extension_e2e_smoke.py`, `bookmark_organizer_pro/i18n.py`). New UI work should extend those existing matrices. The remaining language-specific product gap is lexical tokenization, not untranslated framework code.

## Rejected Ideas

- **Hosted sync, multi-user collaboration, and federation.** Rejected because they replace the local single-user trust model with identity, conflict resolution, and server operations. Floccus issue 1787 and Nextcloud Bookmarks issue 2374 show the resulting integrity risk.
- **Live bidirectional browser-bookmark sync.** Rejected because deletion propagation and conflicts can lose data. Existing imports, XBEL, and extension capture cover portability without a live second writer.
- **Full WARC or WACZ capture and replay.** Rejected because a specialist replay stack increases artifact size and attack surface without repository demand. ArchiveBox and ReplayWeb.page should remain external specialists.
- **Full PDF annotation, text-to-speech, or audio playlists.** Rejected as current priorities because they add large platform and dependency commitments. Zotero and Readwise already specialize in them.
- **Arbitrary executable plugins.** Rejected because data-driven rules, templates, CLI, REST, and MCP already provide bounded extension points without loading untrusted code.
- **Cloud AI or telemetry by default.** Rejected because local ownership and explicit provider choice are core differentiators (`bookmark_organizer_pro/ai.py`, `bookmark_organizer_pro/services/local_state.py`).
- **A universal local document warehouse.** Rejected because BOP's schema and workflows are URL-centered. Narrow format imports remain appropriate when source fidelity is known.
- **Immediate MCP v2 or FastMCP 4 migration.** Rejected until FastMCP 4 is stable or the project deliberately adopts the raw MCP SDK. The current `mcp<2` and `fastmcp<4` bounds remain defensible (`pyproject.toml`, `Roadmap_Blocked.md`).
- **Matryoshka embeddings, sqlite-vec, or free-threaded Python.** Rejected without a measured search, memory, or concurrency bottleneck. These remain blocked or speculative (`Roadmap_Blocked.md`).
- **Full web/PWA, mobile clients, browser-store publication, native messaging, and signed MSIX work.** Rejected from the active plan because their recorded prerequisites remain unresolved (`Roadmap_Blocked.md`).
- **Immediate PyInstaller 6.22.2 upgrade.** Deferred because no reviewed advisory affects 6.21.0, while 6.22.2 changes Tcl/Tk and Windows one-file behavior. Revisit through the complete frozen-artifact regression, not as an isolated version bump.
- **Grid view, the removed cross-encoder reranker, and retired placeholder surfaces.** Rejected because commits `cf9904b8fb12b3225da26303903a34a028b5dcc5`, `224f39935781db6b223d7777ea8ee1730104535d`, and `3b27a0ada9e62b89f1130c22f9103b46294528e7` deliberately removed them and no new demand changes those decisions.

## Sources

### Project and tracker

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/issues

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/pulls

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/discussions/1

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/discussions/2

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/releases/tag/v6.16.0

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/commit/63715916ff5658f3b8db66eb16cb0c4f938b7f29

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/commit/584799be1f3bf471a45480c107a99ceb427ec5b5

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/commit/cf9904b8fb12b3225da26303903a34a028b5dcc5

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/commit/224f39935781db6b223d7777ea8ee1730104535d

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/commit/3b27a0ada9e62b89f1130c22f9103b46294528e7

### OSS competitors

https://github.com/karakeep-app/karakeep

https://github.com/karakeep-app/karakeep/releases/tag/v0.33.1

https://github.com/karakeep-app/karakeep/releases/tag/v0.33.2

https://github.com/karakeep-app/karakeep/issues/1266

https://github.com/karakeep-app/karakeep/issues/1748

https://github.com/karakeep-app/karakeep/issues/2344

https://github.com/karakeep-app/karakeep/issues/2893

https://github.com/linkwarden/linkwarden

https://github.com/linkwarden/linkwarden/issues/587

https://github.com/linkwarden/linkwarden/issues/1597

https://github.com/linkwarden/linkwarden/issues/1747

https://github.com/linkwarden/linkwarden/pull/1700

https://github.com/goniszewski/grimoire

https://github.com/goniszewski/grimoire/blob/main/docs/roadmap.md

https://github.com/sissbruecker/linkding

https://github.com/sissbruecker/linkding/issues/68

https://github.com/sissbruecker/linkding/issues/285

https://github.com/sissbruecker/linkding/issues/917

https://codeberg.org/readeck/readeck/raw/branch/main/CHANGELOG.md

https://readeck.org/en/blog/202512-2026-roadmap/

https://github.com/ArchiveBox/ArchiveBox

https://github.com/ArchiveBox/ArchiveBox/wiki/Roadmap

https://github.com/Kovah/LinkAce/releases/tag/v2.6.1

https://github.com/Kovah/LinkAce/security/advisories/GHSA-cj8f-h888-m57m

https://github.com/floccusaddon/floccus/releases/tag/v5.10.2

https://github.com/floccusaddon/floccus/issues/1787

https://github.com/nextcloud/bookmarks/releases/tag/v16.2.6

https://github.com/nextcloud/bookmarks/issues/2374

### Commercial and adjacent products

https://help.raindrop.io/changelog/web

https://help.raindrop.io/integrations/mcp

https://help.raindrop.io/premium-features

https://docs.readwise.io/changelog

https://readwise.io/mcp

https://readwise.io/pricing/reader

https://support.start.me/en/articles/9182823-broken-link-checker-pro

https://start.me/pricing

https://goodlinks.app/releases/

https://goodlinks.app/api/

https://anybox.app/

https://github.com/gildas-lormeau/SingleFile

https://github.com/obsidianmd/obsidian-clipper

https://web.hypothes.is/blog/hypothesis-for-web-developers/

https://www.zotero.org/support/pdf_reader

https://github.com/webrecorder/replayweb.page/releases/tag/v2.5.0

### Standards, APIs, and research

https://www.w3.org/TR/annotation-model/

https://www.w3.org/TR/annotation-protocol/

https://wicg.github.io/scroll-to-text-fragment/

https://developer.chrome.com/docs/extensions/reference/api/bookmarks

https://developer.chrome.com/docs/extensions/reference/api/readingList

https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/

https://blog.modelcontextprotocol.io/posts/2026-07-28/

https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0

https://lancedb.github.io/lancedb/python/python/

https://www.inkandswitch.com/essay/local-first/local-first.pdf

https://specs.webrecorder.net/wacz/1.1.1/

https://www.rfc-editor.org/info/rfc7089/

### Dependencies and security

https://github.com/psf/requests/releases/tag/v2.34.2

https://github.com/psf/requests/security/advisories/GHSA-gc5v-m9x4-r6x2

https://github.com/urllib3/urllib3/security/advisories/GHSA-mf9v-mfxr-j63j

https://github.com/lxml/lxml/security/advisories/GHSA-vfmq-68hx-4jfw

https://pillow.readthedocs.io/en/stable/releasenotes/12.3.0.html

https://github.com/PrefectHQ/fastmcp/security/advisories/GHSA-vv7q-7jx5-f767

https://github.com/PrefectHQ/fastmcp/security/advisories/GHSA-rww4-4w9c-7733

https://cryptography.io/en/stable/changelog/

https://github.com/lancedb/lancedb/releases/tag/v0.37.1

https://pyinstaller.org/en/latest/CHANGES.html

https://pypi.org/project/ijson/

https://gofastmcp.com/updates

### Community and discovery

https://github.com/topics/bookmark-manager

https://github.com/dogancelik/awesome-bookmarking

https://github.com/awesome-selfhosted/awesome-selfhosted

https://www.reddit.com/r/selfhosted/comments/1nq9drl/linkwarden_v213_opensource_collaborative_bookmark/

https://www.reddit.com/r/selfhosted/comments/1raq3b0/selfhosted_bookmark_manager_with_android_app_that/

https://news.ycombinator.com/item?id=44381555

https://news.ycombinator.com/item?id=44063662

https://lobste.rs/s/yzecpu/localfirst_you_keep_using_word

## Open Questions

None. Every recommended item can be implemented from the cited code, tests, and primary specifications.
