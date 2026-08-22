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

### P2

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
