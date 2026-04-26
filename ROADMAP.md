# Bookmark Organizer Pro — Roadmap

Python/Tkinter bookmark manager with 4,224 categorization patterns, 5 AI providers, MCP server, local semantic search (lancedb + fastembed), hybrid RRF, single-file HTML snapshots, citation-aware AI summaries, RAG chat, encrypted DB, dead-link scanner. Post-v6.0.0.

## Planned Features

### Core / Ingest
- **Headless Chromium snapshot** via `playwright` when `monolith` / `single-file` both fail (heavy sites: Twitter/X, Substack gated content)
- **Scheduled auto-snapshot** of selected bookmarks on a cadence (catch silent edits)
- **Reading-progress** persistence per bookmark (scroll position + % read in the embedded viewer)
- **Tags-on-save** inline prediction — show 3 suggestions as the user types
- **Bulk tag replace** with preview + undo

### Semantic / RAG
- **Re-rank step** after RRF using a lightweight cross-encoder (bge-reranker-base) — optional, gated on installed package
- **Chunk-level provenance** in RAG answers (not just bookmark-level)
- **Time-weighted recall** — down-weight old bookmarks unless explicitly requested
- **Collections as retrieval scopes** — every chat can be pinned to a collection from the sidebar
- **Answer caching** by (query_hash, scope_hash) to speed repeat questions

### MCP server
- Add `create_flow` / `append_to_flow` tools so agents can curate research trails
- Add `export_zip` / `list_snapshots` tools
- Server-side auth token with per-tool scopes (some clients should be read-only)
- Streaming responses for `chat_with_collection`

### UI / UX
- **Tree view alongside list view** for deeply nested categories
- **Virtualized list** (current Tkinter `Treeview` chokes past ~10k rows)
- **Graph view** — bookmarks as nodes, tags as edges, fruchterman-reingold layout
- **Web client** — FastAPI + HTMX frontend reading the same SQLite/config
- **Mobile PWA** companion (read-only + add-URL)
- Replace some heavy Tk widgets with `sv-ttk` or migrate the whole shell to `CustomTkinter`

### Importers / Exporters
- **Matter** export format
- **Omnivore** export (already deprecated but users still have dumps)
- **Zotero** `.rdf` import/export (bridge the academic side)
- **Browser live sync** via a tiny companion extension (MV3) that pushes new bookmarks via localhost
- **ATOM / JSON Feed** output per collection

### Safety / Ops
- SSRF allow-list regex (beyond the current private-IP block)
- Auto-rotate encrypted-DB passphrase with audit log
- Per-backup integrity hash + optional S3/B2 off-site upload
- Telemetry-free mode banner on first run

## Competitive Research
- **Linkwarden** ([linkwarden/linkwarden](https://github.com/linkwarden/linkwarden)) — self-hostable, PostgreSQL, screenshots + PDFs + HTML archives, highlights, Wayback integration, collaborative. Reference for team features; our advantage: no server needed, plus MCP + local vectors.
- **Karakeep** ([karakeep-app/karakeep](https://github.com/karakeep-app/karakeep)) — Next.js + Meilisearch, AI auto-tagging. We already have AI tagging + vectors; match the UI polish.
- **Raindrop.io** — cloud, not self-hostable. Reference UX bar. Our edge: fully local, encryptable DB.
- **Readeck** — read-it-later with highlights, video transcripts, e-book export. Worth porting: e-book export + video transcript retrieval.
- **Shaarli** — minimalist link share. Good inspiration for a future "share a collection as a public page" feature.

## Nice-to-Haves
- Browser-history import with dedup against existing bookmarks (one-off migration aid)
- YouTube-video metadata + transcript capture via `yt-dlp` (no download, metadata only)
- EPUB export of a collection for Kobo/Kindle sideload
- Auto-highlight extraction — run local LLM on snapshot, persist N highlights per article
- Public-share static export (single HTML file per collection) — no server required
- Plugin API via `entry_points` so community can add importers without forking

## Open-Source Research (Round 2)

### Related OSS Projects
- **Karakeep (formerly Hoarder)** — https://github.com/karakeep-app/karakeep — self-hostable "bookmark everything" (links, notes, images, PDFs, videos); AI auto-tagging via ChatGPT or Ollama; Meilisearch full-text; screenshots + full-page archive
- **Linkwarden** — https://github.com/linkwarden/linkwarden — collaborative self-hosted manager; auto-capture screenshot/PDF/single-HTML; reader-view with highlight/annotate; Wayback integration; collections/sub-collections; local AI tagging
- **Linkding** — https://github.com/sissbruecker/linkding — minimalist, fast, multi-user, browser extensions, REST API; great pattern for a "no-frills" mode
- **Shiori** — https://github.com/go-shiori/shiori — Go-based Pocket-style bookmarking with offline archive
- **Wallabag** — https://github.com/wallabag/wallabag — PHP, read-it-later focus, mature browser extensions and mobile apps
- **ArchiveBox** — https://github.com/ArchiveBox/ArchiveBox — aggressive archiver; Singlefile/WARC/Wayback/DOM/screenshot multi-format snapshots
- **Readeck** — https://github.com/readeck/readeck — Go, modern read-it-later with clean UI and selfhost focus
- **Omnivore** — https://github.com/omnivore-app/omnivore — polished read-it-later with Obsidian/Logseq integration
- **Briefkasten** — https://github.com/ndom91/briefkasten — minimal React/Next bookmark app
- **LinkAce** — https://github.com/Kovah/LinkAce — PHP, share-collections, multi-user

### Features to Borrow
- Full-page single-HTML snapshot via monolith + WARC dual-archive for redundancy (Linkwarden + ArchiveBox)
- Highlight + annotate on the reader view with per-annotation export to markdown (Linkwarden)
- "Collections / sub-collections" hierarchy plus tags — hybrid of tree + facet (Linkwarden, Karakeep)
- AI tagging with local Ollama as default; OpenAI/Anthropic only if user supplies a key (Karakeep — very privacy-forward)
- Wayback Machine fallback resolver: if archive failed, re-query Wayback for the URL (Linkwarden)
- Browser extension with one-click save, tag picker, and instant archive queue (every major player)
- Multi-user with per-user spaces, shared collections, read/write/owner roles (Linkwarden)
- Mobile PWA with "Share to BOP" intent target (Readeck, Linkwarden)
- Meilisearch/Tantivy-backed full-text search over the archive body, not just title/URL (Karakeep)
- REST + GraphQL API for user-built integrations (Linkding REST, Karakeep GraphQL)
- Import from Pocket/Pinboard/Instapaper/Raindrop/Diigo/Netscape bookmarks.html (all major players support these)
- "Digest" email/RSS: daily/weekly roll-up of newly-saved items with OG preview (community pattern)

### Patterns & Architectures Worth Studying
- Archiver-as-separate-service: saving a URL enqueues jobs for screenshot/PDF/HTML/WARC fetchers independently, each retryable (Linkwarden, ArchiveBox)
- Meilisearch sidecar with BM25-style scoring; app writes docs, Meilisearch owns the index (Karakeep)
- Ollama-vs-hosted-LLM abstraction: a Tagger interface with local/remote implementations, user picks at runtime (Karakeep)
- Container-first deployment with docker-compose covering DB + Meili + worker + app + browser (all playwright-archiver based) (Karakeep, Linkwarden)
- Plain-format export (SQLite dump + raw archive files + JSON of metadata) so migration to another tool is trivial (Linkding and others — "you're never locked in")

## Implementation Deep Dive (Round 3)

### Reference Implementations to Study
- **lancedb/lancedb `python/python/lancedb/table.py`** — https://github.com/lancedb/lancedb/blob/main/python/python/lancedb/table.py — canonical embedded table API; `table.search(query).limit(k).to_list()` is the full hybrid-search signature.
- **lancedb/lancedb hybrid search example** — https://lancedb.github.io/lancedb/notebooks/multi_lingual_example/ — `LinearCombinationReranker(weight=0.7)` for BM25+vector fusion; direct copy for bookmark hybrid search.
- **qdrant/fastembed** — https://github.com/qdrant/fastembed — `TextEmbedding(model_name="BAAI/bge-small-en-v1.5")` — 384-dim ONNX, no PyTorch dep, 30MB model. Reference for `.embed(iterator)` streaming.
- **sbalaraddi/lancedb-learning `02_vector_search.py`** — https://github.com/sbalaraddi/lancedb-learning — minimal CRUD + vector search walkthrough.
- **Y2Z/monolith** — https://github.com/Y2Z/monolith — single-file HTML snapshot (CSS/JS/images inlined); shell out with `--no-js-errors --silent -o <file>.html <url>`.
- **sqlite-utils `sqlite-utils enable-fts`** — https://sqlite-utils.datasette.io/en/stable/cli.html#full-text-search — hybrid BM25 + LanceDB vector; use FTS5 for exact-match fallback.
- **Modelcontextprotocol/servers `src/sqlite`** — https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite — reference MCP server pattern for exposing the bookmark DB to Claude/Cursor.
- **BurntSushi/ripgrep `crates/core/app.rs`** — https://github.com/BurntSushi/ripgrep — reference for NL→structured-query parsing (tags, date ranges) with fast fallback.

### Known Pitfalls from Similar Projects
- LanceDB `connect()` creates a directory, not a file — `~/.bookmark-org/lance.db/` expands into N GB with WAL; document backup semantics.
- fastembed on first run downloads ONNX from HuggingFace — fails behind corporate proxies without `HF_ENDPOINT=https://hf-mirror.com` or pre-bundled model files.
- LinearCombinationReranker weight=0.7 favors vector — bookmarks with exact-URL queries rank worse; bias to 0.3 for URL/title-dominant corpora or switch per query type.
- `pynetdicom` not relevant here; skip.
- monolith with JS-heavy SPAs (React/Next) captures empty shell — shell out to `playwright` headless first, save rendered HTML, then monolith the static result.
- AES-256-GCM nonce reuse on encrypted DB is catastrophic — use `os.urandom(12)` per-write, store nonce alongside ciphertext; do NOT use a KDF-derived static nonce.
- lancedb Python wheel on Windows requires VC++ 2022 redist; bundle `vcruntime140.dll` or document prereq.
- FTS5 MATCH + LanceDB vector results have different ID types — normalize to `int64` rowid in join layer or RRF breaks.

### Library Integration Checklist
- `lancedb==0.16.0` — https://github.com/lancedb/lancedb — key API: `db = lancedb.connect('./db'); tbl = db.create_table('bookmarks', schema=...)`. Gotcha: schema uses pyarrow types; `pa.list_(pa.float32(), 384)` for 384-dim vectors.
- `fastembed==0.5.1` — https://github.com/qdrant/fastembed — `TextEmbedding('BAAI/bge-small-en-v1.5')`. Gotcha: caches model to `~/.cache/fastembed/`; ship offline with `cache_dir=` pointing to bundled path.
- `pyarrow==18.1.0` — LanceDB dependency; pin or lancedb silently downgrades on `pip install -U`.
- `cryptography==44.0.0` — `AESGCM.encrypt(nonce, plaintext, aad)` for AES-256-GCM. Gotcha: `nonce` MUST be 12 bytes and never reused per-key.
- `monolith` (Rust binary) — https://github.com/Y2Z/monolith — ship via `cargo install monolith` in Dockerfile or vendor compiled binary per-platform.
- `playwright==1.49.1` — for JS-rendered snapshot pre-processing. Gotcha: `playwright install chromium` is 180MB; document or bundle.
- `mcp==1.1.2` — official MCP SDK — https://github.com/modelcontextprotocol/python-sdk — `@server.tool()` decorator for bookmark query tools.
- `feedparser==6.0.11` — RSS ingestor; gotcha: Atom 1.0 `<link rel="alternate">` vs RSS `<link>` — feedparser normalizes to `entry.link`, trust it.
