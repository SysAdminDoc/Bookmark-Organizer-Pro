# Changelog

All notable changes to Bookmark-Organizer-Pro will be documented in this file.

## [v4.4.0] - 2026-04-18

### Added
- **Soft Delete / Trash** — `soft_delete_bookmark()`, `restore_from_trash()`, `get_trash()`, `empty_trash()`. Bookmarks go to a recoverable trash instead of permanent deletion. Inspired by LinkAce (1K+ stars)
- **LinkChecker Redirect Detection** — Detects HTTP redirects during link checking, stores final URL + redirect chain in custom_data. `get_redirected_bookmarks()` lists affected bookmarks, `fix_redirect()` updates URL to final destination. Inspired by bookmarks-organizer (209 stars) and TidyMark (196 stars)
- **Random Bookmark Rediscovery** — `get_random_bookmark()` returns a random bookmark for rediscovering forgotten saves. Inspired by Buku (7.1K stars)
- **Batch Metadata Refresh** — `batch_refresh_metadata()` re-fetches titles/descriptions/favicons for all bookmarks using ThreadPoolExecutor (configurable 1-10 workers). Progress callback support. Inspired by Buku's multi-threaded DB refresh
- **Auto-Clean URL on Add** — `add_bookmark_clean()` strips tracking params, normalizes URL, auto-categorizes, and checks for duplicates in one call. Inspired by Shaarli's transparent UTM stripping
- **XBEL Import/Export** — `XBELHandler.export()` and `XBELHandler.import_from_xbel()` support XML Bookmark Exchange Language, a standard interchange format. Round-trip preserves titles, URLs, categories, tags, descriptions, and dates. Atomic file writes. Inspired by Buku (supports 7 formats)

### Changed
- LinkChecker now tracks redirect chains (stores redirect_url, redirect_count, redirect_chain per bookmark)
- Netscape importer error logging uses `log.error()` instead of `print()`

## [v4.3.0] - 2026-04-18

### Added
- **URL Normalization Engine** — Academic-grade URL canonicalization (RFC 3986 + web heuristics). Strips 60+ tracking parameters, normalizes scheme/host/port/path, removes fragments, sorts query params, strips www prefix, removes default index files. Based on ACM CIKM 2009 research on URL normalization for de-duplication
- **Page Metadata Fetcher** — `fetch_page_metadata(url)` auto-fetches title, meta description, and favicon URL from live pages. Handles both `name` and `property` meta attributes, resolves relative favicon paths
- **Wayback Machine Integration** — `wayback_check(url)` queries archive.org API for existing snapshots; `wayback_save(url)` submits pages for archival. Inspired by Linkwarden/Shiori
- **Bookmark Health Scoring** — `calculate_health_score(bookmark)` returns 0-100 score based on 7 factors: link validity (40pts), title quality (10pts), description/notes (10pts), tags (10pts), recency (10pts), staleness (10pts), categorization (10pts). Inspired by Hoarder's health monitoring
- **Smart Duplicate Merger** — `merge_duplicate_bookmarks()` combines duplicate entries keeping best title, earliest created date, latest visit, combined tags (union), longest description, summed visit counts, and best favicon. Inspired by BrowserBookmarkChecker and Buku
- **BookmarkManager.merge_duplicates()** — One-call method to find and merge all duplicates with dry-run support
- **BookmarkManager.get_health_scores()** — Returns all bookmarks with health scores, sorted worst-first
- **BookmarkManager.fetch_metadata_for_bookmark()** — Updates a bookmark's title/description/favicon from the live URL
- **BookmarkManager.check_wayback()** / **save_to_wayback()** — Wayback Machine check and save per bookmark

### Changed
- `find_duplicates()` now uses the new `normalize_url()` canonicalization instead of simple path-only stripping. Catches far more duplicates (http vs https, www vs non-www, tracking params, sorted query params)
- `import_html_file()` now normalizes URLs before duplicate checking
- `import_json_file()` now normalizes URLs before duplicate checking

## [v4.2.0] - 2026-04-18

### Added
- 5 new categories: SysAdmin & IT, Weather & Meteorology, Downloads & Torrents, Media Production & Design, Software & Customization, Productivity & Tools
- 894 categorization patterns (up from ~150) across 32 categories
- Expanded icon mapping with 65+ keyword-to-emoji associations
- Domain patterns for 500+ popular websites derived from real-world bookmark analysis

### Changed
- PatternEngine domain matching now uses proper suffix matching instead of substring (fixes false positives like `t.co` matching inside `reddit.com`)
- Government & Legal `.gov` pattern uses regex to prevent false matches
- Redirects & Shorteners patterns converted to `domain:` type for precision
- Categories expanded from 27 to 32 with comprehensive pattern coverage

### Fixed
- Domain matching bug: `domain:t.co` no longer falsely matches `reddit.com`
- Plain pattern `redirect.` no longer catches unrelated URLs
- StorageManager: atomic write via os.replace() prevents data loss on Windows
- Bookmark ID: os.urandom() for true uniqueness instead of collision-prone time+hash
- Bookmark.from_dict(): validates URL is non-empty
- StorageManager.load(): skips individual corrupt entries instead of failing entire load
- SearchQuery: domain filter uses suffix matching, tag filter uses exact match
- HTML import: decodes HTML entities in titles, normalizes URLs for dedup
- JSON import: per-item error handling with logging
- HTML export: escapes tag values in TAGS attribute
- JSON export: atomic write via temp file + os.replace()
- Backup rotation: handles unlink failures gracefully
- Replaced print() error calls with structured log.error()

## [v4.1.0] - 2026-01

- Initial public release
- Multi-format import (HTML, JSON, CSV, OPML, TXT)
- AI-powered categorization (OpenAI, Anthropic, Google, Groq, Ollama)
- 10+ built-in themes
- Advanced search with boolean operators
- Undo/redo command stack
- System tray integration
- Favicon caching
- Automatic backups
