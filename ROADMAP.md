# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

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
