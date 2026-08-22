# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

- [ ] P2 — R-105: Add safe declarative extraction repair rules
  Why: site-specific extraction failures need a repair path, but arbitrary scripts would undermine the existing egress and content-safety boundaries.
  Evidence: `bookmark_organizer_pro/services/extraction_templates.py`, ingest/snapshot services; ArchiveBox configuration; Readeck extraction workflows.
  Touches: extraction-template schema/evaluator, preview UI, per-domain matching, import/export, safety and regression tests.
  Acceptance: A versioned rule can match a normalized host and use allowlisted CSS selectors/attribute/text transforms with strict size/time limits; preview compares default and repaired output before save; invalid selectors fail closed; rules cannot execute code or trigger new origins; fixtures lock repairs to representative pages.
  Complexity: L

## Research-Driven Additions

Added 2026-08-21 from RESEARCH.md (same date). IDs continue the R-series after R-106.

### P1

- [ ] P1 — R-107: Declare Firefox data-collection permissions in the extension manifest
  Why: Mozilla requires `browser_specific_settings.gecko.data_collection_permissions` for new extensions since 2025-11-03 and for all existing extensions by mid-2026; the Firefox manifest has no declaration, which blocks any AMO submission and misstates what the extension transmits (sanitized page snapshots and URLs to the localhost API).
  Evidence: `browser-extension/manifest.firefox.json` (no `data_collection_permissions` key); https://blog.mozilla.org/addons/2025/10/23/data-collection-consent-changes-for-new-firefox-extensions/; https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/; `browser-extension/shared.js::captureSanitizedPage`.
  Touches: `browser-extension/manifest.firefox.json`, `scripts/build_extension.py` (manifest validation), `tests/test_packaging.py`, README extension privacy section, `packaging/product_claims.json` if surfaces are counted.
  Acceptance: The Firefox build manifest declares `data_collection_permissions` with `required` and `optional` arrays matching actual behavior (or an explicit `none` with a documented justification per the open question in RESEARCH.md); `scripts/build_extension.py firefox` fails if the key is absent; a packaging test asserts the declared categories; the Chromium manifest is unchanged; README states the declaration verbatim.
  Complexity: S

- [ ] P1 — R-108: Constrain AI tag suggestions to a bounded vocabulary with page-state suppression
  Why: `suggest_tags` asks the model for 5–7 tags that must not duplicate existing tags, which is the exact recipe behind Karakeep's 12.7K-tag sprawl and Linkwarden's 836-tags-for-592-links reports; both projects now ship constrained modes and tag caps.
  Evidence: `bookmark_organizer_pro/services/ai_tools.py` line 329 prompt; https://github.com/karakeep-app/karakeep/issues/1266; https://github.com/karakeep-app/karakeep/issues/529; https://github.com/karakeep-app/karakeep/issues/1892; https://github.com/linkwarden/linkwarden/issues/1597; https://github.com/linkwarden/docs/blob/main/docs/Usage/ai-tagging.md (predefined/existing/auto modes).
  Touches: `services/ai_tools.py::TagSuggester.suggest_tags`, `services/tag_linter.py` (reuse normalization), AI settings mixin (`app_mixins/ai_settings.py`), MCP/CLI tag-suggestion entry points, `tests/test_services.py`.
  Acceptance: A persisted setting selects `existing-only`, `prefer-existing` (default), or `free`; the prompt is built from the library's tag vocabulary with a configurable cap (default 3, max 5); suggestions are normalized through the tag linter before return; bookmarks whose extracted text or title matches error/login/CAPTCHA/cookie-wall signatures return no tags with a ledger reason; tests cover each mode, the cap, and suppression with a fake client.
  Complexity: M

- [ ] P1 — R-109: Import a folder of bookmark exports as one deduplicated batch
  Why: Real migrations arrive as piles of near-identical exports (2026-08-21 corpus: 1,113 files, 95 unique by SHA-256, 149,471 entries → 5,206 URLs); every desktop import path is single-file, and no competitor offers folder ingestion (Karakeep OOMs on large imports, linkding is one Netscape file at a time).
  Evidence: `app_mixins/import_export.py` lines 499/522/841/894 (`askopenfilename`); `services/import_sessions.py`; `services/dup_hybrid.py` (URL normalization); https://github.com/karakeep-app/karakeep/issues/1748; https://github.com/sissbruecker/linkding/releases (v1.46.0 import dedup).
  Touches: `app_mixins/import_export.py` (directory picker + batch flow), `services/import_sessions.py` (batch session model), `importers.py` format detection, `services/dup_hybrid.py` (shared normalized-URL key), Import Center UI, `cli.py import --directory`, `tests/test_core.py` fixtures with duplicate files.
  Acceptance: Selecting a directory (desktop or `cli import <dir>`) hashes every file, skips byte-identical duplicates, auto-detects each unique file's importer, merges entries across files by the existing normalized-URL key keeping newest date and longest title, shows a preview (files, unique URLs, conflicts) before commit, commits in one transactional batch with a single safepoint, and a test with 6 files (3 duplicates, 2 formats) yields the expected unique count.
  Complexity: L

### P2

- [ ] P2 — R-110: Add Markwise CSV and generic column-mapped CSV importers
  Why: Markwise exports (`Title,URL,Main Category,Sub Category,Added At`) had no importer in the 2026-08-21 corpus, and the only CSV importer is Readwise-specific; a mapped CSV importer also covers start.me and Pinboard CSV variants.
  Evidence: `bookmark_organizer_pro/importers_extra.py` (`ReadwiseReaderCSVImporter` only CSV class); corpus files `markwise.app-bookmarks-export*.csv`; https://codeberg.org/readeck/readeck/raw/branch/main/CHANGELOG.md (0.20.0 CSV adapters).
  Touches: `importers_extra.py`, Import Center format list, `cli.py import` format choices, `scripts/generate_completions.py --check`, tests.
  Acceptance: Markwise CSV imports title/URL/two-level category/ISO date; a generic CSV path lets the user map columns (title, url, category, subcategory, tags, date) with a header preview; both reject non-http(s) URLs and dedupe by normalized URL; completions regenerate cleanly.
  Complexity: S

- [ ] P2 — R-111: Add an Omnivore export importer
  Why: Omnivore's JSON export became the migration lingua franca after its 2024-11 shutdown; Karakeep, Linkwarden, and Readeck all import it, and BOP's 21 importers do not.
  Evidence: `importers.py`/`importers_extra.py` class list (no Omnivore); https://docs.karakeep.app/using-karakeep/import/; https://github.com/linkwarden/linkwarden/issues/808; Readeck CHANGELOG 0.15.x.
  Touches: `importers_extra.py`, Import Center, `cli.py`, tests with a fixture zip of `metadata_*.json`.
  Acceptance: A zip or directory of Omnivore `metadata_*.json` files imports URL, title, labels as tags, saved/archived state as read-later/read, and dates; a fixture test imports 3 entries including one archived item.
  Complexity: S

- [ ] P2 — R-112: Suggest organization rules from the existing library
  Why: The pattern engine cannot ship personal domains (8.7% of the 2026-08-21 corpus stayed uncategorized for that reason), the rule engine from R-104 only applies rules users write by hand, and the derivation logic already exists as a dev script.
  Evidence: `scripts/add_user_domains.py`; `services/organization_rules.py`; `core/pattern_engine.py`; https://linkding.link/auto-tagging/ (rule preview UX); https://github.com/karakeep-app/karakeep/releases (v0.33.1 suggestions from similar bookmarks).
  Touches: new `services/rule_suggestions.py`, `ui/organization_rules.py` (Suggest button + review list), `cli.py rules suggest`, tests.
  Acceptance: Given the library, the suggester proposes domain→category rules where ≥N (default 3) manually categorized bookmarks on one host agree and no shipped pattern matches; each proposal shows supporting bookmarks and conflicts; accepted proposals become versioned rules through the existing preview/apply path; a test library with 10 hosts yields the expected proposals and rejects a split-category host.
  Complexity: M

- [ ] P2 — R-113: Make the dead-link scanner host-polite with cached verdicts
  Why: At 5k+ bookmarks the scanner has no per-host concurrency cap, backoff, or Retry-After handling, so rate-limited hosts (429/503) are misreported as dead; lychee's design (retries, rate-limit awareness, result cache) is the reference, and broken-link finding is a feature Raindrop and start.me paywall.
  Evidence: `bookmark_organizer_pro/services/dead_link_scanner.py` (no `Retry-After`/backoff/per-host code); https://github.com/lycheeverse/lychee/releases; https://raindrop.io/pro/buy; https://github.com/sissbruecker/linkding/issues/68.
  Touches: `services/dead_link_scanner.py`, shared egress policy helpers, scan results UI, `cli.py` scan command, tests with a fake server returning 429 + Retry-After.
  Acceptance: Concurrent requests per host are capped (default 2); 429/503 honor Retry-After or exponential backoff up to a bound and are classified `rate-limited`, not dead; verdicts are cached with a TTL so a rescan within the TTL skips unchanged hosts; the fake-server test produces zero false-dead results.
  Complexity: M

- [ ] P2 — R-114: Refresh locked dependencies and pin the lingua Python floor
  Why: The lock is behind on feature releases (trafilatura 2.2.0 extraction overhaul 2026-07-31, lancedb 0.37.1, cryptography 50.0.0) and `lingua-language-detector` 2.2.0 requires Python ≥3.12 while the verified release lane is 3.11, so an unguarded regeneration will fail or silently pin.
  Evidence: `pylock.toml` (lancedb 0.34.0, trafilatura 2.1.0, cryptography 49.0.0, lingua 2.1.1); `pyproject.toml` (`lingua-language-detector>=2.0`, no ceiling); `packaging/release_manifest.json` (python 3.11 lock); https://raw.githubusercontent.com/adbar/trafilatura/master/HISTORY.md; https://github.com/lancedb/lancedb/releases.
  Touches: `pyproject.toml`, `pylock.toml` via `scripts/package_contract_audit.py --update-lock`, extraction regression fixtures (new) under `tests/`, `scripts/dependency_vulnerability_audit.py` run.
  Acceptance: `lingua-language-detector` carries `<2.2; python_version<'3.12'` (or equivalent marker); trafilatura 2.2.x, lancedb 0.37.x, cryptography 50.x are locked; a new fixture set locks extraction output for 5 representative pages and passes after the bump; the vulnerability audit and full suite pass; release contract regenerates with the new SBOM count.
  Complexity: M

- [ ] P2 — R-115: Add a migration guide for Pocket, Pinboard, Omnivore, Readwise, and Markwise refugees
  Why: Pocket (dead 2025-07-08) and Pinboard (domain lapsed 2026-06-16) produced two waves of users actively searching for import paths; competitors captured them with dedicated landing pages, while BOP's README does not name its own Pocket/Pinboard importers.
  Evidence: `README.md` (no migration section); `importers_extra.py` (`PocketExportImporter`, `PinboardJSONImporter`); https://en.wikipedia.org/wiki/Pocket_(service); https://michaelharley.net/posts/2026/06/16/dear-pinboard-im-breaking-up-with-you-its-me-and-its-you/; https://www.instapaper.com/pocket.
  Touches: `README.md` (new "Migrating from…" section with importer matrix), `docs/`, GitHub repo description/topics.
  Acceptance: README lists every importer with its source format, a 3-step path per source (export → import → verify counts), and links to the bulk-folder flow once R-109 lands; written in plain prose per the repo's documentation voice; packaging doc-drift test passes.
  Complexity: S

- [ ] P2 — R-116: Generate and validate MCP registry `server.json` metadata
  Why: The official MCP registry (API v0.1 frozen 2025-10, feeding GitHub's and PulseMCP's directories) is how MCP servers are discovered in 2026; Raindrop and Karakeep ship listed servers and BOP has no `server.json`.
  Evidence: repo grep (no `server.json`); https://modelcontextprotocol.io/registry/about; https://glama.ai/blog/2026-01-24-official-mcp-registry-serverjson-requirements; https://help.raindrop.io/integrations/mcp.
  Touches: new `packaging/server.json` (namespace `io.github.sysadmindoc/bookmark-organizer-pro`), `bookmark_organizer_pro/mcp_server.py` (advertised name/version must match), `scripts/package_contract_audit.py` (schema validation), tests.
  Acceptance: `server.json` validates against the registry schema, declares the stdio `bop-mcp` entry point and the PyPI package, and its version is asserted equal to `APP_VERSION` by a test; the publish step itself stays operator-gated and is documented in `Roadmap_Blocked.md`.
  Complexity: S

### P3

- [ ] P3 — R-117: Expose LanceDB stop-word, tokenization, and hybrid-pagination controls in hybrid search
  Why: lancedb ≥0.35 added custom stop-word lists, table-level query tokenization, and hybrid offset pagination; `hybrid_search.py` surfaces none, so long result sets re-rank the whole candidate set and noise words dilute FTS.
  Evidence: `bookmark_organizer_pro/services/hybrid_search.py`, `services/vector_store.py`; https://github.com/lancedb/lancedb/releases.
  Touches: `services/vector_store.py` (FTS index options), `services/hybrid_search.py` (offset/limit passthrough), search settings UI, REST/MCP search parameters, tests with the JSON fallback store unchanged.
  Acceptance: FTS index creation accepts a configurable stop-word list (default English) and tokenizer; hybrid search accepts offset/limit and returns deterministic pages; the in-memory fallback ignores the options without error; a benchmark case shows no regression in the gate.
  Complexity: M (depends on R-114)

- [ ] P3 — R-118: Replace SM-2 highlight review with recall-probability resurfacing
  Why: SM-2 is dated for this use (Anki switched its default to FSRS in 25.07, 2025-07) and card-style grading fits flashcards, not reading highlights; Readwise's Daily Review uses per-highlight recall half-lives, source weighting, and resurface-when-P(recall)≤50%, which matches how highlights are actually revisited.
  Evidence: `bookmark_organizer_pro/services/reader_annotations.py` (SM-2), `mcp_server.py` tools `list_due_reader_reviews`/`record_reader_review`; https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights; https://blog.readwise.io/adding-intention-to-spaced-repetition/; https://github.com/open-spaced-repetition/fsrs4anki.
  Touches: `services/reader_annotations.py` (scheduler + stored `half_life`/`last_seen` fields with migration from SM-2 records), reader review UI, `cli.py` review commands, MCP tool docs, `tests/test_services.py` section 22.
  Acceptance: Existing SM-2 records migrate without loss; due-for-review is computed from recall probability with per-source up/down weighting and a "Soon/Later/Someday" choice mapping to 7/14/28-day half-lives; the 0–5 quality API remains accepted for compatibility; a deterministic-clock test shows a highlight resurfacing at P≈0.5 and a down-weighted source resurfacing later.
  Complexity: M
