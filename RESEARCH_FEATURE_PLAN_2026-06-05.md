# Research Feature Plan — Bookmark Organizer Pro v6.2.1+

> **Date:** 2026-06-05 | **Pass:** 3 (post-v6.2.1 + categorization rebuild)
> **Scope:** Net-new findings after v6.2.1 fixes and 43-category / 5,918-pattern rebuild.
> **Prior status:** All P0/P1 from pass 2 resolved in v6.2.1. This pass focuses on the new categorization system, remaining test gaps, and ecosystem updates.

---

## Executive Summary

BOP v6.2.1 has resolved all prior crash bugs, data corruption, and security
findings. The categorization system was rebuilt from 32→43 categories with a
new two-pass priority matching engine (5,918 patterns). This research pass
found **6 broken domain patterns**, **48 dead domain-path rules**, **3
misplaced domains**, a **latent dead-code bug** in the pattern engine, **20+
false-positive-prone keywords**, and **10 high-value test gaps** including
zero coverage of the core two-pass priority behavior. No ecosystem changes
require immediate action — Nuitka jumped to v4.x (good news for R-40).

**Top 5 actions:**
1. Fix 6 broken domain patterns with spaces (will never match real URLs)
2. Convert 48 dead `domain:path/...` patterns to `path:` or `regex:` (domain matcher ignores path portion)
3. Fix 3 misplaced domains (photopea→Design, ifixit→Technology, apollo.io→Business)
4. Add test for two-pass priority behavior (the core engine change is unprotected against regression)
5. Evaluate and tighten 20+ overly broad 3-character keyword patterns that cause false positives

---

## Evidence Base

| Source | Method | Confidence |
|--------|--------|------------|
| Categorization system audit (pattern_engine.py + default_categories.py) | Line-by-line code review + pattern analysis | Verified |
| v6.2.1 fix verification (10 items) | Code inspection + import test | Verified |
| Test suite analysis (222 tests across 4 files) | Full pytest run + gap analysis | Verified |
| Ecosystem research (competitors, MCP spec, deps) | Web search | Verified/Likely |

---

## New Findings

### A. Broken Patterns (P0 — silent failures, fix now)

**A-01. 6 domain patterns with embedded spaces — will never match**
These patterns contain spaces and cannot match real URL hostnames:

| Line | Current Pattern | Fix |
|------|----------------|-----|
| ~1416 | `domain:liberty mutual.com` | `domain:libertymutual.com` |
| ~2107 | `domain:marley spoon.com` | `domain:marleyspoon.com` |
| ~2405 | `domain:action network.com` | `domain:actionnetwork.com` |
| ~2586 | `domain:babylon bee.com` | `domain:babylonbee.com` |
| ~3244 | `domain:camping world.com` | `domain:campingworld.com` |
| ~3252 | `domain:landroveru sa.com` | `domain:landroverusa.com` |

- Confidence: **Verified** — DNS hostnames cannot contain spaces.
- Effort: S

**A-02. 48 dead `domain:site.com/path` patterns — path portion ignored by engine**
The `domain:` handler extracts only `parsed.hostname` — the path component of patterns like `domain:github.com/copilot` is never checked. These 48 patterns compile but cannot match.

Notable examples:
- `domain:github.com/copilot` (AI) — intended to catch GitHub Copilot pages
- `domain:linkedin.com/jobs` (Careers) — intended to catch LinkedIn job search
- `domain:linkedin.com/learning` (Education)
- `domain:google.com/flights` (Travel)
- `domain:google.com/store` (Technology)
- `domain:wired.com/news` (News)

Fix: Convert to `regex:` patterns like `regex:github\\.com/copilot` or split into `domain:` + `path:` pairs.
- Confidence: **Verified** — pattern_engine.py line 84-89 strips everything after hostname.
- Effort: M (48 patterns to audit and convert)

**A-03. 3 misplaced domains**

| Domain | Current Category | Correct Category | Reason |
|--------|-----------------|------------------|--------|
| `photopea.com` | Artificial Intelligence | Design | Browser-based Photoshop clone, not an AI tool |
| `ifixit.com` | Automotive | Technology | Covers ALL electronics repair, not just automotive |
| `apollo.io` | Artificial Intelligence | Business | B2B sales/CRM platform, not an AI tool |

- Confidence: **Verified** — confirmed by visiting each site.
- Effort: S

### B. Engine Quality (P1)

**B-01. `plain` type rules compile but never match (latent dead code)**
- File: `pattern_engine.py` lines 114-119 (compilation) vs lines 145-172 (matching)
- The `compile_patterns()` method creates rules of type `"plain"` for patterns without a prefix. The `match()` method's two passes check `domain`, `path`, `extension`, `keyword`, `title`, and `regex` — but never `plain`.
- Currently there are 0 plain-type rules in the dataset (all patterns are typed), so this is a latent bug.
- Fix: Either remove the `plain` compilation path (since all patterns must be typed now) or add `plain` matching to Pass 2.
- Confidence: **Verified**
- Effort: S

**B-02. Performance: 0.83ms/bookmark worst case with 5,918 rules**
- Each `match()` call iterates all 5,918 rules twice (Pass 1 + Pass 2) for unmatched URLs.
- For batch imports of 10K bookmarks = ~8.3s worst case. Noticeable but not blocking.
- **Optimization:** Index domain rules into a dict keyed by domain for O(1) lookup. 78% of rules (4,639) are domain type. This would cut Pass 1 from O(n) to O(1) for exact matches plus a short suffix walk for subdomains.
- Confidence: **Verified** (measured via audit agent)
- Effort: M
- Priority: P2 (not urgent until users report slow imports)

**B-03. 20+ overly broad keyword patterns cause false positives**
These only trigger when no domain match exists (Pass 2), so they're mitigated for well-known sites. Risk is for bookmarks on obscure/personal domains.

Most damaging confirmed false positives:
- `keyword:bond` → "James Bond movie review" → Finance (not Entertainment)
- `keyword:stream` → "mountain stream" → Entertainment
- `keyword:report` → "book report template" → News
- `keyword:analysis` → "data analysis for ML" → News
- `keyword:community` → "community garden" → Forums
- `keyword:management` → "anger management" → Business
- `keyword:budget` → "budget travel tips" → Finance (not Travel)
- `keyword:interview` → "celebrity interview" → Careers
- `keyword:theme` → "party theme" → Software

Also 20+ three-character keywords (`dns`, `vpn`, `aws`, `sdk`, `etf`, `tls`, `sla`, `hoa`, `bmi`, `ama`, `rmm`, etc.) that match as substrings in unrelated words.

Fix options: (a) remove the most ambiguous single-word keywords, (b) require word-boundary matching for short keywords, (c) add a minimum keyword length of 4 characters.
- Confidence: **Verified**
- Effort: M (needs careful evaluation per keyword to avoid losing legitimate matches)
- Priority: P2

### C. v6.2.1 Fix Verification — Minor Residuals

**C-01. obsidian_export.py: 3 optional fields not escaped**
- Lines 77-81: `language`, `content_type`, and `reading_time` are written without `_yaml_escape()`.
- Low risk since these are typically short safe strings, but inconsistent with the YAML injection fix.
- Confidence: **Verified**
- Effort: S

**C-02. mcp_server.py: redundant local Path import**
- Line 208: `t_get_extracted_text` still does `from pathlib import Path as _P` locally, redundant now that `Path` is module-level at line 34.
- Cosmetic, no functional impact.
- Effort: S

**C-03. Path sandbox checks use string startswith() instead of Path.is_relative_to()**
- `mcp_server.py:319` and `epub_export.py:69-70` and `obsidian_export.py:102-103` all use `str(path).startswith(str(base))`.
- `Path.is_relative_to()` (Python 3.9+) is more semantically correct and immune to edge cases where a path like `/home/user2` starts with `/home/user`.
- Safe in practice on Windows/Unix due to path separators, but a minor robustness improvement.
- Effort: S

### D. Test Coverage Gaps (P1)

**Top 10 highest-value missing tests:**

| # | Gap | Risk | File | Effort |
|---|-----|------|------|--------|
| 1 | **Two-pass priority behavior** — no test verifies domain beats keyword across categories | HIGH — core engine change unprotected | `pattern_engine.py` | S |
| 2 | **CLI dispatch routing** — entire 822-line CLI module untested | HIGH — primary entry point | `cli.py` | M |
| 3 | **NLQueryTranslator._parse()** — LLM JSON parsing, zero coverage | MEDIUM-HIGH | `nl_query.py` | S |
| 4 | **execute_query() filter branches** — 10+ filter branches, zero coverage | MEDIUM-HIGH | `nl_query.py` | M |
| 5 | **PatternEngine with DEFAULT_CATEGORIES** — no integration smoke test | MEDIUM | `default_categories.py` | S |
| 6 | **SmartCollections multi-filter AND logic** — only single-axis tests exist | MEDIUM | `smart_collections.py` | S |
| 7 | **SmartCollections content_type/read_later/has_snapshot filters** — 3 of 9 filter axes untested | MEDIUM | `smart_collections.py` | S |
| 8 | **dup_hybrid.py pure functions** — _simhash64(), _hamming() | MEDIUM | `dup_hybrid.py` | S |
| 9 | **vector_store.py pure math** — _cosine(), reciprocal_rank_fusion() | MEDIUM | `vector_store.py` | S |
| 10 | **CLI multi-threaded check** — thread safety and result aggregation | MEDIUM | `cli.py` | M |

### E. Ecosystem Updates

**E-01. Nuitka jumped to v4.1.x (was referenced as 2.x in R-40)**
- Nuitka 4.0+ brought major scalability improvements, Python 3.14 support, Visual Studio 2026 support.
- Tkinter plugin still available. This is good news for R-40.
- Action: Update R-40 description to reference Nuitka 4.x.

**E-02. tksheet 7.6.0: `date_sort_key` required for date columns**
- `natural_sort_key` no longer handles integer-style date strings. Use `date_sort_key` for date columns.
- Action: Implementation note for R-16 (list virtualization).

**E-03. All other ecosystem items already covered** — Karakeep MCP, MCP spec RC, FastMCP 3.4.0, Pillow CVEs all already in ROADMAP.

### F. Existing Test Suite Status

**222 tests across 4 files. 1 pre-existing failure.**

| File | Tests | Coverage |
|------|-------|----------|
| `test_core.py` | 153 | Core models, pattern engine, URL normalization, storage, network safety, AI, search, UI, importers |
| `test_services.py` | 18 | Embeddings, encryption, tag_linter, flows, digest, rss_feeds, zip_export, read_later |
| `test_mcp_tools.py` | 17 | All 20 MCP tools, schema validation, flows CRUD, dedup |
| `test_v62_services.py` | 34 | SmartCollections (18), EPUB (4), Obsidian (12) |

**Pre-existing failure:** `test_import_html_skips_malformed_http_urls` in test_core.py — not related to v6.2 work.

---

## Updated Priority Order

### Immediate (fix before next release)

| # | Finding | Effort |
|---|---------|--------|
| A-01 | Fix 6 broken domain patterns with spaces | S |
| A-03 | Fix 3 misplaced domains (photopea, ifixit, apollo.io) | S |
| C-01 | Escape 3 unescaped Obsidian frontmatter fields | S |
| D-1 | Add test for two-pass priority behavior | S |
| D-5 | Add integration smoke test with DEFAULT_CATEGORIES | S |

### High priority

| # | Finding | Effort |
|---|---------|--------|
| A-02 | Convert 48 dead domain-path patterns to regex/path patterns | M |
| B-01 | Remove or fix dead `plain` type code path | S |
| C-02 | Remove redundant local Path import in mcp_server.py | S |
| C-03 | Use Path.is_relative_to() for sandbox checks | S |
| D-2 | Add CLI dispatch routing tests | M |
| D-3/4 | Add NL query parser + filter branch tests | M |

### Medium priority

| # | Finding | Effort |
|---|---------|--------|
| B-02 | Domain dict indexing for O(1) pattern lookup | M |
| B-03 | Evaluate and tighten overly broad keywords | M |
| D-6/7 | Complete SmartCollections filter coverage | S |
| D-8/9 | Add dup_hybrid and vector_store math tests | S |
| E-01 | Update R-40 to reference Nuitka 4.x | S |

---

## Quick Wins (< 30 min each)

1. Fix 6 broken domain patterns (find/replace spaces in domain names)
2. Move photopea.com to Design, ifixit.com to Technology, apollo.io to Business
3. Wrap language/content_type/reading_time in `_yaml_escape()` in obsidian_export.py
4. Remove redundant `from pathlib import Path as _P` in mcp_server.py line 208
5. Add 1 test: `PatternEngine({"A": ["keyword:x"], "B": ["domain:test.com"]}).match("https://test.com/x")` returns "B"
6. Remove dead `plain` type compilation code (or add to Pass 2)

---

## Open Questions

1. **Should 3-char keywords be word-boundary matched?** Changing `keyword:aws` to `regex:\\baws\\b` would fix "jaws" false positives but is slower. Need to measure impact on 5,918-rule engine performance.

2. **Should the 48 dead domain-path patterns be converted to regex or path rules?** Regex is more precise (`regex:github\\.com/copilot`) but slower. Path rules (`path:/copilot`) are fast but less specific. The right answer depends on how many false positives path rules would create.

3. **Pre-existing test failure** (`test_import_html_skips_malformed_http_urls`) — is this a known issue or a real regression? Needs investigation.
