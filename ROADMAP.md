# Roadmap — Bookmark Organizer Pro

Actionable work only. Historical and completed roadmap material is archived in CHANGELOG.md; blocked work is kept in Roadmap_Blocked.md.

## Actionable Items


## Research-Driven Additions

Added 2026-08-21 from RESEARCH.md (same date). IDs continue the R-series after R-106.

### P1

### P2

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
