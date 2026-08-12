# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

- [ ] P1 — R-93: Audit all user-visible strings through the localization pipeline
  Why: the current i18n check passes while visible Python and extension JavaScript strings can bypass registered translation sinks.
  Evidence: `bookmark_organizer_pro/i18n.py`, `locale/bop.pot`, `tests/test_i18n.py`, browser-extension sources; Chrome i18n API.
  Touches: i18n extractor/audit, Python UI strings, extension `_locales` and runtime messages, translator guidance, tests.
  Acceptance: Static auditing recognizes every approved desktop and extension translation API and fails on unregistered visible literals; catalogs include context/placeholders/plurals, pseudolocalization runs in both surfaces, layout tests cover expansion, and missing keys fall back visibly without raw identifiers.
  Complexity: L

- [ ] P1 — R-94: Add end-to-end assistant cancellation and failure budgets
  Why: long AI operations have no uniform Stop contract across UI workers, streaming clients, retries, caches, and job history.
  Evidence: AI UI/client services and `bookmark_organizer_pro/services/job_ledger.py`; Joplin PR #15946 and PR #15944.
  Touches: provider interfaces, AI workers/dialogs, retry policy, job ledger, partial-output/cache handling, cancellation tests.
  Acceptance: Every AI operation exposes Stop, propagates one cancellation token through network/stream/retry layers, closes resources within a tested deadline, records `cancelled` separately from failure, never caches partial output, and caps attempts, elapsed time, input tokens/characters, and output size with actionable UI errors.
  Complexity: L

- [ ] P1 — R-95: Wire scheduled snapshots into lifecycle and recovery
  Why: The former R-24 completion claim is not reachable: `auto_snapshot.py` and its saved interval exist without a verified application lifecycle that restores, runs, pauses, and recovers the scheduler.
  Evidence: `bookmark_organizer_pro/services/auto_snapshot.py`, snapshot settings, lifecycle mixins, snapshot failure/history services, `CHANGELOG.md`.
  Touches: lifecycle/settings UI, scheduler, job ledger, snapshot history/failure UI, shutdown and clock-control tests.
  Acceptance: Enabling a schedule persists and starts one scheduler; restart restores it; disable/shutdown cancels it; overlapping runs are coalesced; offline/retryable failures use bounded backoff and remain visible; deterministic-clock tests prove due selection, restart, pause, retry, and no duplicate capture.
  Complexity: M

- [ ] P2 — R-96: Clarify extension category and search states
  Why: capture can show a blank default-category affordance, while search lacks explicit loading/no-results/error announcements and robust accessible state.
  Evidence: `browser-extension/popup.html`, `browser-extension/popup.js`, `browser-extension/sidepanel.html`, `browser-extension/sidepanel.js`, visual captures; Chrome bookmarks/storage/i18n APIs.
  Touches: extension popup/options/shared scripts and styles, locale catalogs, browser-extension tests.
  Acceptance: The effective default category is always named and distinguishable from “no category”; category changes persist atomically; debounced search exposes loading, result count, no-results, and error states via live regions; controls have names/descriptions/focus order and remain usable at 200% zoom.
  Complexity: M

- [ ] P2 — R-97: Generate shell completions from CLI parser truth
  Why: The former R-77 completion claim has drifted: hand-maintained files omit 15 parser commands and advertise an invalid `flow delete` command.
  Evidence: `bookmark_organizer_pro/cli.py`, `scripts/completions/bop.bash`, `scripts/completions/bop.zsh`, `scripts/completions/bop.fish`, `CHANGELOG.md`.
  Touches: CLI command model, Bash/Zsh/Fish completion generation, docs, generated-file contract tests.
  Acceptance: One parser-derived command/option model generates all supported shells; a contract test compares every parser path and choice to generated completions, rejects nonexistent paths, and verifies quoting for spaces/non-ASCII values.
  Complexity: S

- [ ] P2 — R-98: Replace the benchmark gate with bounded realistic workloads
  Why: the documented direct command fails on imports and the repaired 500-add case exceeds two minutes, so it cannot provide timely regression signal.
  Evidence: `benchmarks/bench_core.py --gate` execution on 2026-07-29; bookmark manager/storage APIs.
  Touches: benchmark seeding/fixtures, per-operation timers, thresholds, command docs, optional CI performance job.
  Acceptance: Setup uses bulk deterministic fixtures outside measured regions; startup, load, search, sort, save, dedupe, and incremental add are reported separately at named collection sizes; each case has a watchdog and machine-readable output; a warm/cold baseline completes within an explicitly documented local budget.
  Complexity: M

- [ ] P2 — R-99: Expose YouTube transcript ingestion as an explicit workflow
  Why: The former R-12 completion claim is not reachable: a transcript service exists but users cannot discover, consent to, diagnose, or retry it as part of bookmark enrichment.
  Evidence: `bookmark_organizer_pro/services/youtube_transcript.py`, ingest/reader/job-ledger services, `CHANGELOG.md`.
  Touches: bookmark actions and settings, transcript service, content provenance/model, job history, CLI/MCP parity, tests.
  Acceptance: Eligible YouTube bookmarks offer an opt-in transcript action with language choice and provenance; fetched text is bounded, stored as a distinct derived representation, searchable/rebuildable, and removable; unavailable/private/captionless/rate-limited cases are distinguished and retryable without corrupting existing content.
  Complexity: M

- [ ] P2 — R-100: Persist reader progress and add an in-progress queue
  Why: competing readers make resumption a core state, while this reader does not persist a stable location across sessions/content revisions.
  Evidence: `bookmark_organizer_pro/ui/reader_view.py`; Karakeep PR #2302; Readeck and Readwise Reader.
  Touches: reader-state schema/store, reader UI, bookmark filters/smart collections, migration/export tests.
  Acceptance: Using R-83’s selector contract, the app stores per-bookmark progress with representation digest and update time, restores the nearest valid anchored location, marks unread/in-progress/finished explicitly, offers an in-progress filter, and lets users reset progress; updates are throttled and never overwrite newer state.
  Complexity: M

- [ ] P2 — R-101: Complete accessible tag autocomplete
  Why: `TagEditor.available_tags` is documented as not wired, forcing exact free-text entry despite an existing tag vocabulary.
  Evidence: `bookmark_organizer_pro/ui/widget_controls.py::TagEditor`, bookmark/bulk editor call sites, extension tag input.
  Touches: shared tag suggestion model, desktop TagEditor, bulk/bookmark editors, extension popup, keyboard/accessibility tests.
  Acceptance: Suggestions are case-insensitive, ranked deterministically, exclude selected tags, preserve arbitrary new tags, and announce count/selection; arrow, Enter, Escape, Tab, mouse, paste, non-ASCII, and duplicate handling work consistently in desktop and extension without trapping focus.
  Complexity: M

- [ ] P2 — R-102: Add a per-bookmark local processing timeline
  Why: capture, metadata, snapshot, transcript, embedding, and retry state is spread across stores, making failures hard to diagnose or reverse.
  Evidence: `bookmark_organizer_pro/services/job_ledger.py`, snapshot history/failure stores, local diagnostics; ArchiveBox extractor status; linkding issue #797.
  Touches: read-only timeline projection, bookmark details UI, retry/remove actions, diagnostics, job/history migration tests.
  Acceptance: Bookmark details show chronological local events with operation, backend, state, timestamp, artifact size/digest, and sanitized error; users can retry eligible steps or remove derived artifacts without deleting the bookmark; projection tolerates missing/legacy records and never exposes credentials/content in diagnostics.
  Complexity: L

- [ ] P2 — R-103: Add a global highlights workspace
  Why: annotation CRUD and review scheduling exist per bookmark, but users cannot search, filter, export, or repair highlights across the collection.
  Evidence: `bookmark_organizer_pro/services/reader_annotations.py`, reader UI; Zotero 8; Readwise Reader.
  Touches: highlight query/projection service, desktop workspace, export/CLI/MCP adapters, orphan/review integration, accessibility tests.
  Acceptance: After R-83, a keyboard-accessible workspace filters highlights by text, note, tag, color, bookmark, review status, and orphan status; opens the anchored source; supports batch export and safe delete/undo; and paginates without loading all page content.
  Complexity: L

- [ ] P2 — R-104: Productize organization rules with preview and undo
  Why: `SmartTagManager` contains reusable rule logic but is not a discoverable, auditable product workflow.
  Evidence: `bookmark_organizer_pro/services/organization.py::SmartTagManager`, bulk-tag and recovery infrastructure.
  Touches: versioned declarative rule schema, rule evaluator, preview UI, bulk transaction/undo, import/export, tests.
  Acceptance: Users can define enabled rules from allowlisted predicates/actions, preview exact affected bookmarks and conflicts, apply one atomic batch with undo, inspect last-run counts/errors, and export/import versioned rules; evaluation is deterministic, bounded, and never runs arbitrary code.
  Complexity: L

- [ ] P2 — R-105: Add safe declarative extraction repair rules
  Why: site-specific extraction failures need a repair path, but arbitrary scripts would undermine the existing egress and content-safety boundaries.
  Evidence: `bookmark_organizer_pro/services/extraction_templates.py`, ingest/snapshot services; ArchiveBox configuration; Readeck extraction workflows.
  Touches: extraction-template schema/evaluator, preview UI, per-domain matching, import/export, safety and regression tests.
  Acceptance: A versioned rule can match a normalized host and use allowlisted CSS selectors/attribute/text transforms with strict size/time limits; preview compares default and repaired output before save; invalid selectors fail closed; rules cannot execute code or trigger new origins; fixtures lock repairs to representative pages.
  Complexity: L
