# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

## Audit Findings — 2026-08-22

Audit-only pass against `d51beb7` (v6.14.0). Baseline before any finding was logged: `python -m pytest -q` 1049 passed / 3 skipped (Playwright ×2, POSIX ×1) / 129 subtests; `ruff check --select F,E9` clean; `gitleaks detect` 372 commits, no leaks; `scripts/dependency_vulnerability_audit.py` 121 locked deps, 0 unsuppressed; `scripts/generate_completions.py --check` and `python -m bookmark_organizer_pro.i18n --check` current; `bandit -r` 7 hits, all reviewed as false positives (SHA-1/MD5 used for layout/simhash/favicon cache names, `0.0.0.0` appears only in deny-lists, RSS already uses defusedxml with a fail-closed stdlib fallback). Tracker: 0 issues, 0 PRs, 2 maintainer-authored discussions with 0 replies, nothing to triage. Extension smoke needs `py -3.13` (Playwright lives there, not in 3.12).

- [ ] P3 — R-137: Unaudited in this pass, needs its own look
  Category: maintainability
  Where: `bookmark_organizer_pro/services/snapshot.py` (1,410 lines; only `import_browser_snapshot` sanitization entry points were spot-checked), `services/mcp_auth.py`, `services/encryption.py`, `services/updates.py`, `services/ollama_manager.py`, `services/rag_chat.py` / `citation_summarizer.py` prompt isolation, `core/sqlite_storage.py`, the ten non-GitHub themes as rendered (only palette math was checked, see R-122), desktop keyboard traversal beyond the a11y contract smoke, and the Firefox build of the extension at runtime (the smoke runs Chromium only).
  Problem: These were either covered by the 2026-07 security passes (`06b01fa`..`f6f4437`) or too large to trace in this pass; they are listed so the next audit does not assume they were checked.
  Evidence: This pass's coverage list.
  Fix: Schedule a focused pass per module; for the themes, the contrast test from R-122 plus one capture per theme through `verify_desktop_viewports` closes most of the visual risk cheaply.
  Acceptance: Each module above has an entry in a later "Audit Findings" section (findings or an explicit clean verdict).
  Confidence: Verified
  Effort: L
