# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

## Audit Findings — 2026-08-22

Audit-only pass against `d51beb7` (v6.14.0). Baseline before any finding was logged: `python -m pytest -q` 1049 passed / 3 skipped (Playwright ×2, POSIX ×1) / 129 subtests; `ruff check --select F,E9` clean; `gitleaks detect` 372 commits, no leaks; `scripts/dependency_vulnerability_audit.py` 121 locked deps, 0 unsuppressed; `scripts/generate_completions.py --check` and `python -m bookmark_organizer_pro.i18n --check` current; `bandit -r` 7 hits, all reviewed as false positives (SHA-1/MD5 used for layout/simhash/favicon cache names, `0.0.0.0` appears only in deny-lists, RSS already uses defusedxml with a fail-closed stdlib fallback). Tracker: 0 issues, 0 PRs, 2 maintainer-authored discussions with 0 replies, nothing to triage. Extension smoke needs `py -3.13` (Playwright lives there, not in 3.12).

- [ ] P3 — R-142: Twenty-eight "(s)" placeholders remain in desktop copy outside the four dialogs already fixed
  Category: ux
  Where: `bookmark_organizer_pro/app_mixins/tools.py` (21 sites, e.g. `:285`, `:356`, `:1005`, `:1092`, `:1204`, `:1255`, `:1285`, `:1456`, `:1503`), `app_mixins/selection.py:263,304,330,347`, `app_mixins/tools.py` snapshot/tag-lint messages, `app_mixins/ai_titles.py:178,256`, `app_mixins/dashboard.py:666,681`, `ui/widget_controls.py:806,811,813`, `ui/reader_view.py:536`.
  Problem: R-129 fixed `pluralize`/`plural_of` and the four dialogs the audit screenshots showed (cleanup review, highlights workspace, organization rules, export). The same "(s)" shorthand is still shown in the Tools menu, bulk selection toasts, the dashboard badges, the tag editor, and Reader View, so the product still reads half-finished in those places.
  Evidence: `grep -rn '(s)' bookmark_organizer_pro/ui bookmark_organizer_pro/app_mixins` on 2026-08-22 returns 28 real copy sites (plus one false positive, `ui/import_center.py:347` `self._select(s)`).
  Fix: Convert each to `pluralize(value, "noun")` and shorten the template accordingly, exactly as `ui/organization_rules.py` and `ui/cleanup_review.py` now do. Do NOT do this with a regex sweep: an attempt on 2026-08-22 mis-rewrote `"{action} YouTube transcript(s)"` (where `action` is a verb, not a count) and produced `pluralize(len(x, "bookmark"))` by mismatching a closing paren. Change them explicitly, in small batches, running the suite between batches.
  Acceptance: `grep -rn '(s)' bookmark_organizer_pro/ui bookmark_organizer_pro/app_mixins` returns only `ui/import_center.py:347`; `python -m bookmark_organizer_pro.i18n --check` passes; the desktop visual smoke still passes.
  Confidence: Verified
  Effort: M

- [ ] P3 — R-143: A snapshot save that fails after the row is persisted leaves a bookmark the retry cannot replace
  Category: reliability
  Where: `bookmark_organizer_pro/services/api.py:1025-1060` (browser-snapshot branch), rollback at `:1035`; the retry then hits the duplicate check at `:982` (`bookmark_manager.url_exists`) and gets 409 at `:983`.
  Problem: `add_bookmark_clean` saves the row, then `import_browser_snapshot` plus a second `save_bookmarks()` runs. If storage fails on that second write, the row is already on disk, and the rollback `delete_bookmark` fails for the same reason. The response is now correctly 503 with `Retry-After` (fixed 2026-08-22), so the extension retries as instructed, but the retry finds the URL already present and gets 409 "Bookmark already exists". The extension treats 409 as terminal, so the captured page is discarded even though only the snapshot failed. The bookmark itself survives, so no data is lost, but the user is told the save failed and the offline copy never lands.
  Evidence: Reported by adversarial review on 2026-08-22 with a probe that fails `storage.save` from the second call: attempt 1 returns 503 and persists one record; attempt 2 returns 409 and `snapshot stored? False`. `tests/test_browser_extension.py::test_a_snapshot_storage_failure_after_the_row_is_saved_still_answers_503` now pins the 503 and that the snapshot handler answered, but does not cover the retry.
  Fix: Let a capture attach to an existing bookmark instead of colliding with it. When `POST /bookmarks` carries a `browser_snapshot` and the URL already exists, run the snapshot import against the existing row and answer 200 rather than 409, keeping 409 for a plain duplicate save with no capture. Alternatively make the snapshot path reserve the row only after the archive succeeds, which is a larger change to `import_browser_snapshot`'s contract.
  Acceptance: A test drives the two-attempt sequence (storage fails on the second write, then recovers) and asserts the retry stores the snapshot and returns success, with exactly one bookmark in the library.
  Confidence: Verified
  Effort: M

- [ ] P3 — R-133: Eleven blocking `messagebox.askyesno` confirmations contradict the product rule of immediate action with undo
  Category: ux
  Where: `bookmark_organizer_pro/app_mixins/import_export.py` (2, including the folder-import confirmation at `:871` added in v6.14.0), `app_mixins/ai_settings.py` (1), `app_mixins/tools.py` (1), `ui/highlights_workspace.py:383` (1, delete highlights, which already has Undo), `ui/management_dialogs.py` (2), `ui/organization_rules.py:522` and three more (4, rules apply already has "Undo last" and preview fingerprints).
  Problem: The owner's standing product rule is no confirmation dialogs (immediate action plus toast, with safepoint/undo for anything destructive). Several of these prompts guard actions that are already reversible (highlight delete has undo; rule apply has undo and a preview; folder import commits through a durable session with a rollback safepoint), so the modal adds friction without adding safety. The batch-import one is especially odd: the user has just read the preview in the same dialog.
  Evidence: `grep -rn "messagebox.ask" bookmark_organizer_pro` counts above; undo paths at `ui/highlights_workspace.py:401`, `ui/organization_rules.py:536`, `services/import_sessions.py` rollback.
  Fix: For each site that has an undo/safepoint path, replace the modal with the action plus a toast that names the undo ("Imported 5,206 bookmarks. Undo from Imports."). For the few that are truly irreversible (credential revoke in `management_dialogs.py`, if any), keep a guard but make it an inline two-step button in the dialog rather than a native modal. Record the decision per site in the commit.
  Acceptance: `grep -rn "messagebox.ask" bookmark_organizer_pro` returns only the sites justified in the commit message; each replaced flow has a test or smoke step showing the toast and the undo.
  Confidence: Verified
  Effort: M

- [ ] P3 — R-144: Backfill the 360 em dashes in historical CHANGELOG entries
  Category: docs
  Where: `CHANGELOG.md`, every section below the newest one.
  Problem: The project's writing rule bans em and en dashes in public prose. README is clean and the newest section is now guarded by `tests/test_packaging.py::test_shipping_docs_avoid_em_and_en_dashes`, but 360 remain in entries for already-shipped releases, including structural ones like `### Changed — UX/UI polish`.
  Evidence: `grep -v -E '^## \[' CHANGELOG.md | grep -c -E '—|–'` returns 360 on 2026-08-22; the newest section and README return 0.
  Fix: Rewrite by hand, section by section, oldest first. Do NOT script it: a blind replace of "—" with a period or comma produces broken sentences, which is exactly how the R-129 plural sweep went wrong. The `### Changed — UX/UI polish` style headings can be handled as a separate mechanical pass (drop the suffix or use a colon) because they are structural rather than prose. Extend the guard test to the whole file once a section is clean.
  Acceptance: `grep -c -E '—|–' CHANGELOG.md` returns 0, and the guard test covers the whole file instead of only the newest section.
  Confidence: Verified
  Effort: M

- [ ] P3 — R-137: Unaudited in this pass, needs its own look
  Category: maintainability
  Where: `bookmark_organizer_pro/services/snapshot.py` (1,410 lines; only `import_browser_snapshot` sanitization entry points were spot-checked), `services/mcp_auth.py`, `services/encryption.py`, `services/updates.py`, `services/ollama_manager.py`, `services/rag_chat.py` / `citation_summarizer.py` prompt isolation, `core/sqlite_storage.py`, the ten non-GitHub themes as rendered (only palette math was checked, see R-122), desktop keyboard traversal beyond the a11y contract smoke, and the Firefox build of the extension at runtime (the smoke runs Chromium only).
  Problem: These were either covered by the 2026-07 security passes (`06b01fa`..`f6f4437`) or too large to trace in this pass; they are listed so the next audit does not assume they were checked.
  Evidence: This pass's coverage list.
  Fix: Schedule a focused pass per module; for the themes, the contrast test from R-122 plus one capture per theme through `verify_desktop_viewports` closes most of the visual risk cheaply.
  Acceptance: Each module above has an entry in a later "Audit Findings" section (findings or an explicit clean verdict).
  Confidence: Verified
  Effort: L
