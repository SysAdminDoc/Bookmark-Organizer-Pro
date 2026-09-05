# Research: Bookmark Organizer Pro

Date: 2026-09-04. Replaces all prior research.

Confidence labels: **Verified** means reproduced on this machine or stated by a primary source fetched on 2026-09-04. **Likely** means it follows from multiple verified signals but has not been exercised against production user data. **Needs live validation** marks a claim that depends on a measurement nobody has taken.

Method note: Hacker News was reachable and 20 threads were read through its item pages and the Algolia comment API. Reddit and Lobsters refused every fetch from this machine on 2026-09-04, so there is no r/selfhosted or Lobsters evidence in this pass. That is a real sampling bias: the community quotes below skew toward self-hosters and developers.

## Executive Summary

**Verified.** The project sits at `APP_VERSION = "6.16.0"` (`bookmark_organizer_pro/constants.py:9`) with four commits past the `v6.16.0` tag, the last of which (`5ab5007`, 2026-08-23) added the persistent Trash contract that `README.md:439` already advertises. Cut the release before anything below.

The 2026-08-23 pass closed its three top items and left R-153 through R-173 open. Those still stand and are not restated. What this pass found is a different and more uncomfortable class of problem: the application is correct and well-guarded at the size it is tested at, and quietly wrong above it. Near-duplicate detection stops after 5,000 records and reports "none found" for the rest. Every single-bookmark edit rewrites and fsyncs the whole library. The table builds a row object for all of them with no cap. And the benchmark gate that should have caught all three holds every collection size to the same absolute millisecond ceiling, so an O(n²) rewrite passes it. This is the same "a gate that asks the wrong question" pattern the working notes already record twice, applied to scale instead of correctness.

Alongside that, an import-time `SystemExit` added on 2026-08-23 makes `pytest` collect zero tests on the machine's default interpreter, two upstream memory-safety fixes landed with no CVE so the dependency audit reports clean, the CLI and GUI importers disagree about whether a Netscape file has tags and folders, and roughly 1,600 lines of service code have no caller at all.

Top opportunities in priority order:

1. Stop `bookmark_organizer_pro/__init__.py` exiting the process at import. It currently makes the test suite unavailable on Python 3.13.
2. Disclose or remove the 5,000-record cap in near-duplicate detection. It answers "no duplicates" today without saying it only looked at the first 3.8% of a large library.
3. Take `lxml>=6.1.3` and `regex>=2026.8.30`. Both fix defects reachable from user input, and neither carries a CVE.
4. Make the CLI Netscape importer read the tags and folders the GUI importer already reads and the exporter already writes.
5. Make the benchmark thresholds scale with collection size so the gate can see a complexity regression at all.
6. Stop rewriting the whole library on every single-record mutation, and stop building a row object for every bookmark on every refresh.
7. Harden the credential surface: failed authentication currently evicts the audit trail that records it.
8. Install a crash handler. Once `mainloop()` is running, an unhandled exception goes to a stderr nobody sees in a windowed build.
9. Fix the English-only pluralizer that bypasses gettext from more than fifteen call sites.
10. Delete the dead subsystems, or wire the ones worth keeping.

## Product Map

### Core workflows

- **Verified.** Capture through desktop forms, the MV3 popup, context menu, side panel, Chrome Reading List, file drops, and 21 importer classes across `bookmark_organizer_pro/importers.py` and `importers_extra.py`.
- **Verified.** Organize with a nested category tree (`Category.full_path` joins on `" / "`, `models/category.py:32`), tags, versioned organization rules with preview and undo, tag linting, duplicate review, and smart collections.
- **Verified.** Preserve and read through sanitized snapshots with a four-backend fallback, extracted text, reader progress, resilient highlights carrying quote and position selectors, and opt-in transcripts.
- **Verified.** Recover through safepoints, rolling backups, recovery bundles, migration preflights, and a persistent Trash whose purge builds and verifies a recovery bundle before unlinking.
- **Verified.** Automate through 68 CLI subcommands, a loopback REST API with scoped bearer credentials, 37 MCP tools, and the extension.

### User personas

- **Likely.** Researchers who need durable sources and quotations. Follows from the reader, highlight, Zotero, Obsidian, EPUB, and OPDS paths.
- **Verified.** Privacy-conscious desktop users. This is the persona the community evidence most directly confirms: local-only ownership, no subscription, and a standalone application rather than a feature inside a note editor are all explicitly asked for (https://news.ycombinator.com/item?id=47016058, https://news.ycombinator.com/item?id=44925438, https://news.ycombinator.com/item?id=44075451).
- **Verified.** CLI and agent users. The MCP server, scoped credentials, and deterministic search exist for them.
- **Likely.** Migrators leaving Pocket, Omnivore, Readwise, Raindrop, Instapaper, Matter, Wallabag, or Arc, each of which has a dedicated importer.

### Platforms and distribution

- **Verified.** Windows desktop with a locally built PyInstaller artifact. `packaging/release_manifest.json` pins the verified lock to Python 3.11 win32 and lists `3.10`, `3.12`, `3.13` as unlocked supported environments. Python 3.14 is absent and 3.10 reaches end of life on 2026-10-31 (https://devguide.python.org/versions/).
- **Verified.** Extension targets Chromium MV3 and Firefox. Google removed the last MV2 extensions from the Chrome Web Store on 2026-08-31 (https://developer.chrome.com/docs/extensions/develop/migrate/mv2-deprecation-timeline); `browser-extension/manifest.json` is already MV3, so nothing is required.
- **Verified.** Storage is JSON by default, SQLite by explicit choice. The API binds `127.0.0.1` hard-coded (`services/api.py:1291`).

### Key integrations and data flows

- **Verified.** Extension to loopback REST to `BookmarkManager`, then snapshot, extraction, timeline, and vector services attach derived artifacts.
- **Verified.** Embeddings default to `BAAI/bge-small-en-v1.5` at 384 dimensions through fastembed, falling back to `minishlab/potion-base-8M` then `all-MiniLM-L6-v2` (`services/embeddings.py:26-29`). Vectors land in LanceDB or an in-memory JSON cosine store.
- **Verified.** Live archiving runs entirely through `services/snapshot.py`. The Wayback, local archiver, screenshot, PDF, and summarizer classes in `services/web_tools.py` are superseded and have no caller, so the application has no reachable Wayback integration today.

## Competitive Landscape

Only four surveyed projects shipped anything between 2026-08-23 and 2026-09-04. The field is quiet; the useful signal this pass is upstream and community, not competitive.

### Karakeep

- **Verified.** No release since v0.33.2 on 2026-08-11 (https://github.com/karakeep-app/karakeep/releases). Its paragraph-paged MCP content and Reader View suitability work still back open items R-161 and R-171. It is the name HN reaches for first in 2026 when someone asks where to go after Pocket.
- **Learn.** Bounded, revision-bound tool responses.
- **Avoid.** Hosted and mobile operating burden. HN users also praise its local-AI tagging specifically because it is local (https://news.ycombinator.com/item?id=49138919), which is a validation of this project's default, not a reason to copy its architecture.

### Linkwarden

- **Verified.** v2.16.2 on 2026-08-31 (https://github.com/linkwarden/linkwarden/releases/tag/v2.16.2). The whole changelog is case-insensitive sorting in Docker, bug fixes, and dependency bumps.
- **Learn.** Sorting is a durable complaint surface. This project folds case but sorts on codepoint order with no collation, so accented and CJK titles land out of position.
- **Avoid.** Shared accounts and server operation.

### Grimoire

- **Verified.** v1.1.0 on 2026-08-25 (https://github.com/goniszewski/grimoire/releases/tag/v1.1.0): SSRF and bind-policy hardening, an AI provider model catalog picker, a static public demo mode, a v0.5 SQLite migration CLI and API, and aligned artifact checksums.
- **Learn.** Two map onto open work here. The SQLite migration CLI is the shape R-162 needs, and the provider model catalog is worth copying into Assistant Settings while that surface is already being reworked.
- **Avoid.** Public demo mode and S3.

### linkding, LinkAce, ArchiveBox, Readeck

- **Verified.** No release in the window. linkding's latest is v1.46.2 on 2026-08-18, LinkAce's v2.6.1 on 2026-08-03, ArchiveBox's v0.9.31-rc on 2026-05-18. The prior pass's reads on all four still hold.
- **Learn.** ArchiveBox's operational reputation on HN is a warning worth internalizing: its headless Chromium "will break randomly and GFL trying to figure out why" (https://news.ycombinator.com/item?id=45896130). This project's four-backend snapshot chain with a pure-Python final fallback is the right answer to that complaint, and should not be traded away for fidelity.

### SingleFile

- **Verified.** v1.24.0 on 2026-09-03, after v1.23.2 and v1.23.3 on 2026-08-31 and 2026-09-02 (https://github.com/gildas-lormeau/SingleFile/releases). The fastest-moving dependency of the snapshot chain, and the capture tool HN users trust over headless archiving (https://news.ycombinator.com/item?id=40571270).
- **Learn.** The pinned SingleFile revision deserves the same currency cadence as the Python dependencies, because capture fidelity regressions arrive here first.
- **Avoid.** Loosening the size, media, MIME, redirect, or timeout bounds around it.

### floccus, Obsidian Web Clipper, Shiori, Buku

- **Verified.** floccus v5.10.3 on 2026-08-30; Obsidian Web Clipper unchanged since 1.7.1 on 2026-07-22; Shiori dormant since v1.8.0 on 2025-09-26; Buku since v5.1 on 2025-12-07.
- **Learn.** One floccus data point is worth carrying: a user reports it "duplicated tens of thousands of bookmarks" and concludes "bookmark managers also don't scale very well" (https://news.ycombinator.com/item?id=41156568). That is the exact failure mode of the truncated duplicate scan described below, from the other direction.

### Community signal

Twenty HN threads from 2025 and 2026 were read in full. The recurring complaints, each with a thread, are worth recording because this repository's own tracker is empty and these are the only demand evidence available.

- **Search quality is the product.** A 32,000-article Pocket user left because quoted search stopped working (https://news.ycombinator.com/item?id=44063662). "Digital graveyard" appears independently in two threads (https://news.ycombinator.com/item?id=44925438, https://news.ycombinator.com/item?id=47128495). One user reframes the whole category: "the real issue isn't where you store notes, it's whether you find them when you actually need them."
- **Import verification is the single most actionable unmet ask.** "Is there any way to see how many articles should have been imported from Pocket, and how many articles have actually been imported, to make sure it's complete?" went unanswered (https://news.ycombinator.com/item?id=44597668). Large-collection imports "partially lose some data or fail completely" (https://news.ycombinator.com/item?id=41814394).
- **Link rot numbers from real collections.** 10,000 bookmarks scanned, "something like 50 links worked" (https://news.ycombinator.com/item?id=44682175). "Links in bookmarks are 95 pct dead" over decades (https://news.ycombinator.com/item?id=49341551). One user describes this project's exact shape as a wish: a local-only app that snapshots each page, lets you grep the snapshots, and falls back to Wayback when a link is dead (https://news.ycombinator.com/item?id=44925438).
- **Archived bodies are what you cannot migrate.** "I just hope that I can export and migrate all my snapshot data as well" (https://news.ycombinator.com/item?id=45047572). Favicons get lost too and users notice (https://news.ycombinator.com/item?id=42696081).
- **Storage cost is an unquantified worry, not a solved question.** "What's the disk space usage like, average per-day additional storage in your usage?" was asked and not answered (https://news.ycombinator.com/item?id=49351802). This clears the "needs live validation" flag the 2026-08-23 pass put on open item R-166.
- **AI tagging is accepted only when local and only when precision does not matter.** The stated objections are hallucination and convention drift, not cost, and the first question asked of any new tool is whether the pipeline runs on device (https://news.ycombinator.com/item?id=47889110).
- **Subscriptions lose the sale.** Multiple users in one thread say they were ready to buy until they saw a subscription (https://news.ycombinator.com/item?id=44075451). A free MIT desktop application is a positioning asset, not just a licensing choice.

## Reported Issues

**Verified.** `SysAdminDoc/Bookmark-Organizer-Pro` is public, not a fork, has issues and discussions enabled, and the tracker is empty: 0 open issues, 0 closed issues, 0 pull requests ever filed. The only two discussions are maintainer posts from 2026-07-30 with no replies, one of which explicitly asks for usage feedback. There is no `KNOWN_ISSUES.md` or `BUGS.md`. The README troubleshooting section is the only user-facing issue record, covering module-not-found, favicons, high CPU on large imports, blurry text at high DPI, import encoding errors, and AI failures.

No roadmap item in this pass claims user demand from this repository. Every defect below came from local reproduction or source tracing, and the demand evidence comes from the HN threads above, which are about competing products rather than this one. One README entry deserves attention as a self-report: "high CPU on large imports" is documented as a known behavior, and the whole-library rewrite per mutation described below is its cause.

## Security, Privacy, and Reliability

- **Verified.** `bookmark_organizer_pro/__init__.py:16` calls `preflight_or_exit()`, which raises `SystemExit(2)` from `bootstrap_dependencies.py:168` when a manifest import is missing. Because it runs at package import, `py -3.13 -m pytest --collect-only -q` on 2026-09-04 ended in `INTERNALERROR ... SystemExit: 2`, "no tests collected", exit 3. The suite still runs under 3.12. The guidance is right and belongs at the entry points; raising `SystemExit` inside an import turns it into an unreadable traceback for every library, embedding, and test consumer. Introduced by `8b8dd41`.
- **Verified.** Near-duplicate detection silently truncates. `services/dup_hybrid.py:122` and `:154` slice `[:self.MAX_PAIRWISE]` with `MAX_PAIRWISE = 5000` at `:100`, so passes 2 and 3 examine the first 5,000 non-exact-duplicate records and never compare the rest. `DuplicateReport` at `:90-92` carries only `groups` and `method_counts`, with no truncation field, so neither caller can disclose it. Both callers hand over the whole library: GUI at `app_mixins/tools.py:1046-1049`, CLI at `cli.py:1562-1564`. On a 131,000-record library the user is told no near-duplicates were found after 3.8% was examined.
- **Verified.** lxml 6.1.3, published 2026-09-02, fixes LP#2165901: external parameter entity parsing was allowed by default even under `resolve_entities="internal"` (https://raw.githubusercontent.com/lxml/lxml/lxml-6.1.3/CHANGES.txt). The lock is at 6.1.2 and the floor is `>=6.1.1`. This is an XXE-class default and the project parses untrusted bookmark HTML and XML. No CVE or GHSA exists, so `pip-audit` reports clean.
- **Verified.** regex 2026.8.30 fixed four memory-safety defects including a heap out-of-bounds write at pattern compile time (issue 611) and a `count_one()` size underflow (issue 612) (https://raw.githubusercontent.com/mrabarnett/mrab-regex/hg/changelog.txt). The lock is at 2026.7.19. Patterns reach the compiler from the user-editable category-pattern JSON, so the input is reachable, and again there is no CVE.
- **Verified.** Failed authentication evicts its own audit trail. Every `authorize` call, success or failure, appends an event capped at 500 with `del audit[:-MAX_AUDIT_EVENTS]` (`services/mcp_auth.py:490-491`) and rewrites `mcp_tokens.json` under lock (`:758-760`). Five hundred failed requests therefore erase the record of the attack that produced them and cause five hundred disk rewrites. `mcp_auth.py:701` increments `invalid_attempts` but nothing enforces on it, and `services/api.py` has no rate limiting, no 429 path, and no backoff anywhere.
- **Verified.** The REST credential never expires or rotates. `import_legacy_rest_token` (`services/mcp_auth.py:560-578`) creates the read, write, and extension credential with no `expires_at`, while `create_token:537`, `revoke_token:832`, and `list_tokens:945` have no caller, so there is no rotation path in the GUI or CLI. The expiry machinery at `:401-411` exists and is unused for the credential that matters most.
- **Verified.** `services/api.py` has no Host-header validation, unlike `mcp_server.py:610-614` which sets `allowed_hosts`, and `_check_browser_origin` at `api.py:596-605` permits requests carrying no `Origin` header. That is exactly the shape a DNS-rebound page's simple GET takes. The bearer requirement is the only thing standing in the way, which makes the missing attempt limit above more serious than it looks in isolation.
- **Verified.** Crash artifacts vanish once the UI is running. `logging_config.py:41-56` is sound (`RotatingFileHandler`, 5 MB, 3 backups), and all five entry points wire it, but no `report_callback_exception` override, `sys.excepthook`, `threading.excepthook`, or `faulthandler` call exists in application code, `main.py`, or the packaging scripts. The only matches in the tree are inside the vendored `build/release-venv/` site-packages and one uncommitted addition to the visual smoke harness, neither of which is runtime. `main.py:110-150` guards startup only; once `mainloop()` is pumping, Tk's default handler prints to a stderr that a windowed or frozen build discards. Worker threads are inconsistently guarded, unguarded at `app_mixins/ai_settings.py:295` and `app_mixins/selection.py:269-294`, guarded at `ui/live_workflow.py:205-215`. The support bundle redacts well but samples only the last 250 to 1,000 lines of the same log, so a crash can rotate away before the user exports it.
- **Verified.** Export filenames strip `<>:"/\|?*` and cap length (`services/obsidian_export.py:38`, `services/reader_annotations.py:188`) but do not reject Windows reserved device names, so a bookmark titled `CON` or `nul` raises `OSError` partway through an export.
- **Verified.** Two modal dialogs grab the pointer without an Escape binding: `ui/trash.py:57` `TrashDialog` (`grab_set()` at `:80`, closable only by clicking Close at `:111`) and `app_mixins/ai_menu_data.py:196-256`. `ui/live_workflow.py:129-130` is also modal without Escape though it does register a close protocol at `:199`. Roughly a dozen sibling dialogs do bind Escape, so the convention exists and nothing enforces it. The newest surface, added by `5ab5007` on 2026-08-23, is one of the ones that missed it.
- **Verified.** cryptography advisories GHSA-jwv3-5hgf-82ww and GHSA-m2h6-j472-rp4c were updated on 2026-09-04 and 2026-09-02 and affect `<49.0.0`; the lock is 50.0.0 and is unaffected. No advisory published between 2026-08-20 and 2026-09-04 affects any other declared dependency, CPython 3.10 through 3.14, Tcl/Tk, or MV3 extensions. `mcp` 1.29.1 (2026-08-24) applies the 4 MiB request body limit to the SSE and OAuth endpoints and sits inside the current range, above the locked 1.29.0.
- **Verified.** Storage is better than typical for a desktop application: `msvcrt.locking` on a sidecar (`core/storage_manager.py:43-86`), atomic `os.replace`, optimistic revision checks raising `StorageConflictError` at `:189`, and revision-polling auto-reload at `managers/bookmarks.py:452-471`. There is no OS-level single-instance guard, but the realistic two-instance outcome is a raised conflict rather than corruption. How that exception reaches the user has not been traced to a visible message.

## Architecture Assessment

- **Verified.** The benchmark gate cannot detect a superlinear regression. `benchmarks/bench_core.py:337-343` computes `scale = max(1.0, size / largest_size)`, which is exactly 1.0 for every size at or below the largest, so all three tiers are held to the same absolute millisecond ceiling. It is a fixed ceiling, not a complexity gate: an O(n²) rewrite that stays under 750 ms at 5,000 records passes unchanged. `DEFAULT_SIZES` at `:32` is `(100, 1_000, 5_000)`, roughly one raw browser export, against a validation corpus of 131,005 entries. Measured cases are cold and warm start, `StorageManager.load`, `SearchEngine.search`, an in-memory `sorted`, `save`, the cheap O(n) URL-bucket `find_duplicates` at `managers/bookmarks.py:887-898`, and `add_bookmark_clean`. Unmeasured: every path with a widget in it, sidebar and category counts, and `dup_hybrid.detect`, which is the expensive one.
- **Verified.** Every single-record mutation rewrites the whole library. `managers/bookmarks.py:490` `_save_snapshot` builds `[bm.to_dict() for bm in mapping.values()]` at `:501`, then `core/storage_manager.py:200-221` writes through mkstemp, fsync, and `os.replace`. Fourteen mutation sites call it (`:573`, `:604`, `:624`, `:643`, `:947`, `:1029`, `:1055`, `:1265`, `:1370`, `:1469`, `:1498` among them), covering add, edit, delete, and tag change. This is the mechanism behind the README's own "high CPU on large imports" entry.
- **Verified.** The table materializes the full library with no cap. `app_mixins/bookmarks.py:234-334` `_populate_list_view` loops every bookmark building a row spec with a nested six-key `sort_values` dict at `:288-297`, four `truncate_middle` calls, and a favicon cache lookup at `:313`. Its only caller at `:228` passes the unfiltered list, and no paging or row limit exists in `bookmarks.py`, `filters.py`, or `ui/treeview.py`. tksheet virtualizes drawing only. In accessibility mode the fallback at `:319-330` issues one `tree.insert` Tcl call per row. Separately the refresh takes four full library snapshots per call, at `:105`, `:151`, `:159`, and `app_mixins/filters.py:233`, each returning a fresh list from `_iter_snapshot()` (`managers/bookmarks.py:813-815`), and sorts with `b.title.lower()` recomputed per comparison at `:149`.
- **Verified.** Roughly 1,600 lines of service code have no production caller. `services/web_tools.py` is entirely dead at 1,045 lines: `WaybackMachine:52`, `LocalArchiver:174`, `AISummarizer:511`, `ScreenshotCapture:784`, and `PDFExporter:905` are referenced nowhere outside the file and the `services/__init__.py` barrel, superseded by `services/snapshot.py`. In `services/organization.py`, `CollectionManager:231`, `FrequentlyUsedManager:398`, and `SettingsProfileManager:470` have zero references, and `SmartTagManager:87` is touched only at `services/organization_rules.py:478-480` to read a constant. `services/ai_tools.py:695` `AICostTracker` is never instantiated, so `record_usage:798` never fires and AI spend tracking does not exist despite the report renderer at `:891`. In `services/local_state.py`, `VersionHistory:727` is never written to, so per-bookmark history is permanently empty, and `CategoryColorManager:814` and `FontManager:886` are unreferenced. Smaller dead entry points include `flows.remove_step:178`, `flows.project_onto:230`, `smart_collections.evaluate_all:424`, `organization_rules.enable_rule:625` and `disable_rule:628`, `nl_query.heuristic_parse:119`, `ollama_manager.delete_model:227` and `list_local_models:242`, `extraction_repairs.preview_repair:249`, `reader_annotations.parse_annotation_export:1214`, `updates.is_newer_version:53`, and `local_state.redact_text:103`.
- **Verified.** `io_formats/xbel.py` implements XBEL import and export, is exported from the package facade at `bookmark_organizer_pro/__init__.py:107` and `:216`, and has a round-trip test at `tests/test_core.py:924`, but is unreachable from `cli.py`, `app_mixins/`, `ui/`, and `mcp_server.py`. This repeats the R-108 dead-feature pattern the working notes already record.
- **Verified.** SM-2 spaced repetition is half-wired. `services/reader_annotations.py:894` `record_review` is reachable from the CLI at `cli.py:2289` and MCP at `mcp_server.py:1110` but has no desktop caller, while `app_mixins/dashboard.py:748` shows a due count the user cannot act on inside the app. `set_review_pace:863` and `set_source_weight:879` have no caller anywhere. RSS feeds, Zotero interop, EPUB export, and extraction repairs are similarly CLI-only and invisible from the desktop.
- **Verified.** The CLI and GUI importers disagree about the same file format. CLI HTML import at `cli.py:1124` routes to `managers/bookmarks.py:675`, which parses only href, add_date, and icon at `:718-719`, never reads `TAGS`, and recomputes the category with `categorize_url` at `:711` instead of taking the `<H3>` folder. The GUI path at `importers.py:996` does read both. The exporter writes `TAGS` at `:1536` and a flat `<H3>` at `:1528`. Export then reimport through the CLI therefore loses tags and folder placement, silently.
- **Verified.** Native export is lossy in both formats. Netscape HTML drops notes, description, created and modified times, category nesting (flattened at `managers/bookmarks.py:1528`), read-later, pinned, archived, visit counts, reader progress, and AI tags; Firefox's `TAGS` attribute paired with a `<DD>` element is the format's only lossless path for tags and notes (https://learn.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/platform-apis/aa753582(v=vs.85)). Native JSON export writes top-level `categories` and `tags` maps at `:1548-1551` that the importer at `:747` never reads, so category colors and empty categories are lost. Highlights and annotations live in `reader_annotations.py` and are exported by no native format at all. No native round-trip test exists: `tests/test_core.py:80` covers `to_dict`/`from_dict` only, and `:1905` exports HTML without reimporting it.
- **Verified.** i18n is scaffolding with a hole in the middle. `locale/` holds `bop.pot` and a README, with zero `.po` or `.mo` files repo-wide, and `browser-extension/_locales/` has only `en`. `i18n.py` implements real `ngettext` and `npgettext`, but the desktop uses a parallel English-only pluralizer, `text_format.pluralize()` at `text_format.py:14-32`, from more than fifteen sites including `app_mixins/tools.py:1028`, `:1122`, `:1200`, and `:1241`, whose output is never wrapped in `_()`. The POT freshness gate cannot see this, which is the same failure the 2026-08-22 working note records about nesting a Python pluralizer inside a translator call. `locale.setlocale()` is never called, so `strftime("%b %d, %Y")` at `app_mixins/bookmarks.py:33` is always English, and table sorting uses NFKC plus casefold codepoint order in `ui/treeview.py` with no `locale.strxfrm`, so accented, German, and CJK collation is wrong. `is_rtl()` and `pseudo_localize()` at `i18n.py:147-166` are unit-tested and called by nothing.
- **Verified.** `i18n.py:33` resolves `_LOCALE_DIR` to `Path(__file__).resolve().parent.parent / "locale"`, which exists only in a source checkout. `pyproject.toml` package-data ships `bookmark_organizer_pro = ["**/*.json"]` and nothing else, and neither `packaging/bookmark_organizer.spec` nor `packaging/nuitka_build.py` nor `scripts/build_release.py` mentions `locale`. A catalog could not load from a wheel install or a frozen release, which is a second unrecorded blocker behind the parked first-translation task.
- **Verified.** The accessibility gate is real but stops at Tk's boundary. `scripts/accessibility_contract_smoke.py:117-173` does genuine label checks on the three extension pages and `:188-309` drives a live headless `tk.Tk()` asserting `takefocus`, Return and space bindings, and that a native `ttk.Treeview` backs accessible mode. What it cannot reach is the platform: there is no UIA, MSAA, IAccessible, or comtypes reference anywhere, so `_bop_accessible_name` at `ui/tk_interactions.py:75` is a plain attribute only the smoke test reads and Narrator never sees. The worst surface is `ui/graph_view.py:181`, a `tk.Canvas` with hand-rolled directional Tab navigation and no accessible name at all.
- **Verified.** `mcp_server.py:1963-1975` builds the FastMCP server behind `getattr(fastmcp_mod, "FastMCP", None)` and a bare `except Exception: return None`, and `main()` at `:2286` then logs the fallback at info level and continues without auto-schema, ToolAnnotations, or cache hints. Any renamed symbol, constructor change, or import error degrades the server silently.
- **Verified.** FastMCP 4.0.0 went stable on 2026-08-31, with 4.0.2 on 2026-09-02 (https://github.com/jlowin/fastmcp/releases). It targets the MCP 2026-07-28 revision, is sessionless, and negotiates protocol era per connection. Its breaking changes matter here: server-initiated sampling and roots are removed, `ctx.elicit()` becomes old-protocol-only, model fields move to snake_case, and background tasks split into `fastmcp-tasks`. The MCP Python SDK is at v2.1.1 (2026-08-25) with v1.x on security fixes only. The `fastmcp<4.0` and `mcp<2.0` caps now pin the server to a maintenance branch, and the 2026-08-21 note in `Roadmap_Blocked.md` calling FastMCP 4 beta is stale.
- **Verified.** Tk 9.0.4 reached CPython Windows builds in 3.14.7 on 2026-08-05; 3.14.0 through 3.14.6 shipped Tk 8.6.15. The DLLs were renamed from `tcl86t.dll` and `tk86t.dll` to `tcl90.dll` and `tcl9tk90.dll` with a new `libtommath.dll`, and Tk 9 embeds its script library inside the DLL (CPython `PCbuild/tcltk.props`, https://github.com/python/cpython/issues/124111). Nuitka 4.2 (2026-08-27) adds official 3.14 support, and PyInstaller 6.22.2 (2026-08-17) fixes a Windows-only spurious security validation error when a onefile executable launches from a symlinked directory or junction, against the 6.21.0 the manifest records.
- **Verified.** lancedb 0.38.0 (2026-08-31) is inside the declared `>=0.37,<1.0` range but makes table existence manifest-authoritative and requires pydantic v2, so a routine lock regeneration can change vector-store behavior with no version-bound signal. This interacts with open item R-160.
- **Verified.** `services/organization.py` and `mcp_server.py` carry repo-wide ruff `F821` exemptions in `pyproject.toml`, and `services/organization.py` has no test file referencing it, so a genuine `NameError` there is invisible to both gates. `services/icons.py` and `services/zotero_interop.py` are also untested, as are all eight AI app_mixins, `bookmark_crud.py`, `command_palette.py`, `zoom.py`, eleven UI modules including the six `workflow_*` files, and `desktop_bootstrap.py`, `logging_config.py`, and `text_format.py`.
- **Verified.** Five declared extension points do nothing: `commands.py:19` `merge()` is a no-op paired with `can_merge()` returning `False`, so command coalescing is declared and unimplemented; `app_mixins/app_shell.py:41` `_setup_styles()` is empty behind a docstring promising treeview tag colors; `app_mixins/selection.py:62` `_on_bookmark_click()` is empty; `app_mixins/lifecycle.py:129` `_try_enable_window_dnd()` is a documented no-op. Two exception swallows are worth naming, at `services/api.py:1288` and `ui/treeview.py:476`.
- **Verified.** The repository contains zero real TODO, FIXME, HACK, XXX, or `@deprecated` markers. Working-tree state on 2026-09-04 is eleven modified files, unstaged, removing the in-app Ollama installer in favor of the vendor download page, teaching `bootstrap_dependencies.py` about Nuitka's `__compiled__` marker, and adding assistant-settings coverage to the visual smoke. None of it touches the open R-156 theme gate.

## Rejected Ideas

- **CPU cross-encoder reranking.** Rejected. Commit `3b27a0ad` deliberately removed the reranker and the evidence does not support reviving it: the widely quoted 1,800 documents per second for `ms-marco-MiniLM-L6-v2` is measured on a V100 GPU (https://sbert.net/docs/cross_encoder/pretrained_models.html), and no primary source publishes a rigorous CPU millisecond-per-pair figure. The only real CPU datapoint found is 20 to 30 seconds falling to 8 to 15 with ONNX int8 for `bge-reranker-base` on a quad-core (https://github.com/microsoft/onnxruntime/issues/19494), far outside an interactive budget.
- **Late-interaction ColBERT retrieval.** Rejected for now. `answerdotai/answerai-colbert-small-v1` is genuinely attractive at 33M parameters, Apache-2.0, 34 MB int8 ONNX, and 53.79 BEIR average, and `fast-plaid` and `pylate-rs` ship Windows CPU wheels. But it stores one vector per token, RAM during index build is the binding constraint, and it would be a second retrieval stack beside LanceDB with no measured bottleneck in the first one. Revisit only after the benchmark gate measures search at a realistic size.
- **Embedding quantization to int8 or binary.** Rejected until measured. The technique is real (roughly 4x smaller at 99.3% retention, 32x at 96% with rescoring, https://huggingface.co/blog/embedding-quantization), but at 384 dimensions a 50,000-bookmark library is about 77 MB of vectors, which does not justify a schema migration yet.
- **WACZ or WARC snapshot output.** Still rejected, with a correction for whoever revisits it: WACZ 1.1.1 is the current stable release and 1.2.0 states plainly that it "has no official standing of any kind" (https://specs.webrecorder.net/wacz/1.2.0/), so any future adapter targets 1.1.1. The original reasons hold: a replay stack, larger artifacts, more attack surface, no demand.
- **OPDS 2.0 as bookmark interchange.** Rejected as interchange. It models ebook publication and acquisition and nothing in the bookmark schema survives the mapping. The existing OPDS catalog export for reader clients is a different use and stays.
- **JSON Feed, ActivityPub bookmarks, and Data Transfer Project adapters.** Rejected. JSON Feed 1.1 has no folder tree and no annotation anchors. FEP-4772 is a draft dated 2026-07-04 with no verified implementations, worth revisiting in 2027 only because its `DocumentCopy` attachment mirrors the snapshot model. The Data Transfer Project has no bookmark vertical; a code search for "bookmark" across `dtinit/data-transfer-project` returns zero hits.
- **Memento server support.** Rejected. RFC 7089 is Informational and was never on the standards track, and the aggregator has rotted: `timetravel.mementoweb.org` and `labs.mementoweb.org` were NXDOMAIN on 2026-09-04 while `https://web.archive.org/web/timemap/link/` still answers 200. Consuming Wayback's own TimeMap is the only live path, and it belongs inside the archived-copy work in open item R-165.
- **W3C Web Annotation Protocol.** Rejected, unlike the Data Model. The Protocol is a dead LDP server API whose working group closed on 2017-03-02 with no activity since. Open item R-164 correctly targets the Data Model only.
- **Free-threaded Python for embedding work.** Still rejected. PEP 779 was accepted and 3.14 calls free-threading supported rather than experimental, but Tcl interpreters are per-thread and Tk is single-threaded, so the UI gains nothing and no measured bottleneck exists in the embedding path.
- **Safari `Bookmarks.plist`, Notion, and Diigo importers.** Rejected for now. Each is real work against an undocumented or authenticated source, and no evidence in this pass shows demand for them. Vivaldi, Opera, and Zen are a different matter and need only profile-path entries at `importers.py:366-388`, which is why they appear on the roadmap and these do not.
- **Hosted sync, multi-user collaboration, live bidirectional browser sync, arbitrary executable plugins, cloud AI or telemetry by default, full PDF or audio suites, and a universal document warehouse.** All still rejected for the reasons recorded on 2026-08-23. Nothing in this window changes any of them, and the community evidence above strengthens the local-only position rather than weakening it.

## Sources

### Project

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/issues

https://github.com/SysAdminDoc/Bookmark-Organizer-Pro/pulls

### Competitors and adjacent projects

https://github.com/linkwarden/linkwarden/releases/tag/v2.16.2

https://github.com/goniszewski/grimoire/releases/tag/v1.1.0

https://github.com/karakeep-app/karakeep/releases

https://github.com/sissbruecker/linkding/releases

https://github.com/Kovah/LinkAce/releases

https://github.com/ArchiveBox/ArchiveBox/releases

https://github.com/gildas-lormeau/SingleFile/releases

https://github.com/floccusaddon/floccus/releases

https://github.com/obsidianmd/obsidian-clipper/releases

https://github.com/go-shiori/shiori/releases

https://github.com/jarun/buku/releases

### Community threads

https://news.ycombinator.com/item?id=44063662

https://news.ycombinator.com/item?id=44597668

https://news.ycombinator.com/item?id=44925438

https://news.ycombinator.com/item?id=45047572

https://news.ycombinator.com/item?id=47128495

https://news.ycombinator.com/item?id=49351802

https://news.ycombinator.com/item?id=49138919

https://news.ycombinator.com/item?id=47016058

https://news.ycombinator.com/item?id=44075451

https://news.ycombinator.com/item?id=41814394

https://news.ycombinator.com/item?id=41156568

https://news.ycombinator.com/item?id=44682175

https://news.ycombinator.com/item?id=49341551

https://news.ycombinator.com/item?id=42696081

https://news.ycombinator.com/item?id=45896130

https://news.ycombinator.com/item?id=40571270

https://news.ycombinator.com/item?id=47889110

https://news.ycombinator.com/item?id=48540592

### MCP and protocol

https://github.com/jlowin/fastmcp/releases

https://github.com/jlowin/fastmcp/releases/tag/v4.0.0

https://gofastmcp.com/getting-started/upgrading/from-fastmcp-3

https://github.com/modelcontextprotocol/python-sdk/releases

### Standards and formats

https://www.w3.org/TR/annotation-model/

https://www.w3.org/groups/wg/annotation/

https://wicg.github.io/scroll-to-text-fragment/

https://caniuse.com/url-scroll-to-text-fragment

https://xbel.sourceforge.net/

https://learn.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/platform-apis/aa753582(v=vs.85)

https://specs.webrecorder.net/wacz/1.1.1/

https://specs.webrecorder.net/wacz/1.2.0/

https://www.rfc-editor.org/rfc/rfc7089.html

https://codeberg.org/fediverse/fep/raw/branch/main/fep/4772/fep-4772.md

https://github.com/dtinit/data-transfer-project

### Dependencies and platform

https://raw.githubusercontent.com/lxml/lxml/lxml-6.1.3/CHANGES.txt

https://raw.githubusercontent.com/mrabarnett/mrab-regex/hg/changelog.txt

https://raw.githubusercontent.com/pyca/cryptography/main/CHANGELOG.rst

https://nuitka.net/changelog/Changelog.html

https://raw.githubusercontent.com/pyinstaller/pyinstaller/develop/doc/CHANGES.rst

https://api.osv.dev/v1/query

https://github.com/advisories

https://devguide.python.org/versions/

https://docs.python.org/3.14/whatsnew/3.14.html

https://github.com/python/cpython/blob/3.14/PCbuild/tcltk.props

https://github.com/python/cpython/issues/124111

https://core.tcl-lang.org/tips/doc/trunk/tip/733.md

https://developer.chrome.com/docs/extensions/develop/migrate/mv2-deprecation-timeline

### Retrieval research

https://huggingface.co/answerdotai/answerai-colbert-small-v1

https://huggingface.co/blog/embedding-quantization

https://sbert.net/docs/cross_encoder/pretrained_models.html

https://github.com/microsoft/onnxruntime/issues/19494

## Open Questions

- **Needs live validation.** What library size should the desktop support? The benchmark stops at 5,000, the maintainer's corpus deduplicates to 5,217 unique URLs from 131,005 raw entries, and a multi-profile browser export routinely exceeds 20,000. The answer sets the acceptance threshold for the scale items and decides whether the table needs true paging or only fewer full scans, and whether near-duplicate detection needs a better algorithm or only honest disclosure of its cap.
- **Needs live validation.** Should the supported matrix add Python 3.14 in the same change that drops 3.10? The two are separable, and claiming 3.14 support without a Tk 9.0.4 frozen-artifact smoke would be a false claim.
- **Needs live validation.** Does `StorageConflictError` from a second running instance reach the user as a readable message, or only as a log line? The exception path is correct; the presentation was not traced.
