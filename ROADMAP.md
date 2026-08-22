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

Findings follow.

- [ ] P2 — R-146: Rotating a passphrase leaves a readable copy under the old one
  Category: security
  Where: `bookmark_organizer_pro/services/encryption.py:340-385` (`rotate_passphrase`), backup written at `:364`.
  Problem: Rotation writes `<name>.pre-rotation-<stamp>.bak` next to the library and never removes it. That file is the original ciphertext, so it still opens with the old passphrase. Someone rotating precisely because the old passphrase leaked is left with a file the leaked passphrase decrypts, sitting beside the one it no longer opens, with nothing in the UI or the log line saying so.
  Evidence: `_atomic_write(backup, original)` at `:364`, verified at `:365`, and never referenced again; the success log names the backup but does not say it is readable under the old secret.
  Fix: Keep the verified backup for the duration of the rotation and delete it once the new file has been read back and verified, which the function already does at `:370-374`. If a durable backup is wanted, re-encrypt it under the new passphrase instead of preserving the old ciphertext, and either way say plainly in the CLI output and the log what the file is and which secret opens it.
  Acceptance: After a successful rotation no file that the old passphrase can decrypt remains in the directory, and a test asserts that by attempting decryption with the old passphrase against every file left behind.
  Confidence: Verified
  Effort: S

- [ ] P3 — R-147: The legacy encryption envelope authenticates only the magic bytes
  Category: security
  Where: `bookmark_organizer_pro/services/encryption.py:236-244` (versions 1 and 2 pass `MAGIC` as the AES-GCM associated data).
  Problem: For v1 and v2 the version field, salt, and nonce sit outside the authenticated data, so an attacker who can write the file can relabel a v1 file as v2 and append an unauthenticated recovery record, and the primary payload still decrypts. Versions 3 and 4 fixed this by authenticating the full header, so this only affects files written before the Argon2 envelope landed. No plaintext is disclosed and no key is recovered; the exposure is that a legacy file's trailing bytes are attacker-shaped and parsed.
  Evidence: `decrypt` at `:236` uses `MAGIC` as AAD on the legacy branch, against `header` on the Argon2 branch at `:250`; `_parse_recovery_record` at `:253` is reached with no authentication on the legacy path.
  Fix: Re-encrypt legacy files to the current envelope on first successful open, which is a one-line follow-up to a successful legacy `decrypt`, and drop the legacy write path entirely once nothing produces it.
  Acceptance: Opening a v1 or v2 file rewrites it as v3 or v4, and a test asserts that a relabelled legacy blob is refused rather than parsed.
  Confidence: Verified
  Effort: M

- [ ] P3 — R-149: Keyboard traversal is asserted per widget, never across a window
  Category: accessibility
  Where: `scripts/accessibility_contract_smoke.py:188-240` and `tests/test_accessibility_contracts.py`.
  Problem: The contract proves individual controls are focusable, that activation fires once, and that focus is restored, and three dialogs assert their own keyboard actions. Nothing walks a real window end to end to check that every interactive control is reachable by Tab, that the order follows the visual layout, and that focus does not escape into a dead region. A control that is focusable in isolation can still be unreachable once it sits inside a frame that traps or skips it.
  Evidence: The smoke builds one label and one button rather than a window; no test calls `tk_focusNext` in a loop over a realized main window.
  Fix: In the desktop visual smoke, which already realizes the main window offscreen, walk `tk_focusNext` from the first control until it cycles, and assert that the set of visited widgets covers every widget with `takefocus=1` and that the visited order matches the geometry order top to bottom, left to right.
  Acceptance: The smoke fails when a focusable control is added inside a container that Tab cannot reach.
  Confidence: Verified
  Effort: M
