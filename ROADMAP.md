# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

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
