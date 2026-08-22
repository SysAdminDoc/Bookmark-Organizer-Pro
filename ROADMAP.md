# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items

## Audit Findings — 2026-08-22

Audit-only pass against `d51beb7` (v6.14.0). Baseline before any finding was logged: `python -m pytest -q` 1049 passed / 3 skipped (Playwright ×2, POSIX ×1) / 129 subtests; `ruff check --select F,E9` clean; `gitleaks detect` 372 commits, no leaks; `scripts/dependency_vulnerability_audit.py` 121 locked deps, 0 unsuppressed; `scripts/generate_completions.py --check` and `python -m bookmark_organizer_pro.i18n --check` current; `bandit -r` 7 hits, all reviewed as false positives (SHA-1/MD5 used for layout/simhash/favicon cache names, `0.0.0.0` appears only in deny-lists, RSS already uses defusedxml with a fail-closed stdlib fallback). Tracker: 0 issues, 0 PRs, 2 maintainer-authored discussions with 0 replies, nothing to triage. Extension smoke needs `py -3.13` (Playwright lives there, not in 3.12).

## Audit Findings — 2026-08-22 (R-137 follow-up pass)

Focused pass over the modules R-137 listed as unaudited. Baseline: `py -3.12 -m pytest -q` 1101 passed / 3 skipped / 596 subtests; `ruff check .` clean; desktop and extension visual smoke green; Firefox smoke green with a zero-error, zero-warning web-ext lint.

Closed by code in this pass, not carried forward:

- **Firefox extension at runtime.** The build failed validation outright. Fixed in 81e717e: the Gecko data collection disclosure needs Firefox 140 and Firefox for Android 142, the manifest claimed 121, and the pinned web-ext was old enough that the lint failed on a different error first. Floors raised, an Android floor added, the builder now refuses a manifest that regresses this, and the extension installs into a real Firefox on a clean profile.
- **Em dashes across the product's own strings.** The writing rule bans them anywhere a person reads, and the audit found roughly fifty in status messages, dialog labels, menu entries, search-syntax help, CLI output, and the Ollama model list. All rewritten, with a guard test that walks string literals and allows only the three uses that are not prose: log lines, a lone dash standing in for an empty table cell, and numeric ranges.
- **The ten non-GitHub themes as rendered.** R-122 checked palette maths only. The desktop smoke now renders every built-in theme, the nine outside the deep matrix once each at the scaled laptop viewport. All twelve pass.

Clean verdicts, no findings:

- **`services/snapshot.py`.** Snapshot filenames come from `int(bookmark.id)` or a SHA-256 prefix, so no caller-controlled path reaches the filesystem; every unlink re-checks that the resolved parent is the snapshots directory; egress runs through `URLUtilities.check_safe_url`; external backends stay behind an explicit environment opt-in; subprocess calls pass argument lists with timeouts and no shell; the 25 MB and 5 MB ceilings are enforced before the write.
- **`services/mcp_auth.py`.** Salted SHA-256 verifiers compared with `secrets.compare_digest` over the whole set with no early exit, scopes validated against their audience, expiry and revocation checked on every authorization, and an audit trail per decision. The verifier is a single hash rather than a slow KDF, which is fine for a 32-byte `token_urlsafe` secret in a private file.
- **`core/sqlite_storage.py`.** No SQL is built by interpolation anywhere in the module; foreign keys, WAL, and `quick_check` are all on; the safepoint label is reduced to alphanumerics before it reaches a filename.
- **`services/updates.py`.** Repository and target URLs are rejected unless HTTPS, and real apply stays gated.
- **`services/ollama_manager.py`.** HTTPS only, hostname allowlist re-checked on every redirect hop, bounded redirects, streamed to a `.part` file, SHA-256 verified against a pinned digest before `os.replace`, and the installer runs as an argument list.
- **`services/rag_chat.py` and `services/citation_summarizer.py` prompt isolation.** Page text goes through `build_untrusted_evidence`, which serializes it as bounded JSON with validated citation IDs, per-chunk and total character ceilings, and a system prompt stating that only the system message defines the task. Page content never reaches the instruction position.

All three findings this pass raised were then drained in the same session, so nothing is left open here. R-146 stopped `rotate_passphrase` leaving a copy the retired passphrase still opens. R-147 moves a legacy v1 or v2 file onto the authenticated envelope the moment its passphrase is available. R-149 walks the Tab ring across the whole window in the desktop smoke.

