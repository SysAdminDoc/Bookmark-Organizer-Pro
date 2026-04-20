"""Command-line interface for bookmark operations."""

from __future__ import annotations

from pathlib import Path
from typing import List

import requests

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION
from bookmark_organizer_pro.core import CategoryManager, get_category_icon
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from bookmark_organizer_pro.url_utils import URLUtilities


# =============================================================================
# CLI Tool
# =============================================================================
class BookmarkCLI:
    """
        Represents a single bookmark with all metadata.
        
        Attributes:
            id: Unique integer identifier
            url: Bookmark URL
            title: Display title
            category: Category name
            tags: List of tag names
            ai_tags: List of AI-suggested tags
            description: Optional description
            favicon_url: URL to favicon image
            created_at: ISO timestamp of creation
            updated_at: ISO timestamp of last update
            visited_at: ISO timestamp of last visit
            visit_count: Number of times visited
            is_valid: Whether URL validation passed
            is_pinned: Whether bookmark is pinned
            ai_category: AI-suggested category
            ai_summary: AI-generated summary
            notes: User notes
        
        Methods:
            to_dict(): Serialize to dictionary
            from_dict(d): Deserialize from dictionary
            matches_search(query): Check if bookmark matches search
        """
    
    def __init__(self):
        self.category_manager = CategoryManager()
        self.tag_manager = TagManager()
        self.bookmark_manager = BookmarkManager(self.category_manager, self.tag_manager)
    
    def run(self, args: List[str]):
        """Run CLI command"""
        if not args:
            self._print_help()
            return
        
        command = args[0].lower()
        cmd_args = args[1:]
        
        commands = {
            "list": self._cmd_list,
            "add": self._cmd_add,
            "delete": self._cmd_delete,
            "search": self._cmd_search,
            "import": self._cmd_import,
            "export": self._cmd_export,
            "categories": self._cmd_categories,
            "tags": self._cmd_tags,
            "stats": self._cmd_stats,
            "check": self._cmd_check,
            "help": self._print_help,
            # v6.0.0 commands
            "ingest": self._cmd_ingest,
            "snapshot": self._cmd_snapshot,
            "embed": self._cmd_embed,
            "semantic": self._cmd_semantic,
            "hybrid": self._cmd_hybrid,
            "summarize": self._cmd_summarize,
            "chat": self._cmd_chat,
            "ask": self._cmd_ask,
            "lint-tags": self._cmd_lint_tags,
            "dups": self._cmd_dups,
            "scan": self._cmd_scan,
            "digest": self._cmd_digest,
            "flow": self._cmd_flow,
            "feed": self._cmd_feed,
            "import-pocket": self._cmd_import_pocket,
            "import-readwise": self._cmd_import_readwise,
            "import-pinboard": self._cmd_import_pinboard,
            "import-instapaper": self._cmd_import_instapaper,
            "import-reddit": self._cmd_import_reddit,
            "zip-export": self._cmd_zip_export,
            "encrypt": self._cmd_encrypt,
            "decrypt": self._cmd_decrypt,
            "read-later": self._cmd_read_later,
            "mcp-server": self._cmd_mcp_server,
        }
        
        if command in commands:
            commands[command](cmd_args)
        else:
            print(f"Unknown command: {command}")
            self._print_help()
    
    def _print_help(self, args=None):
        """Print help message"""
        print(f"""
{APP_NAME} CLI v{APP_VERSION}

Usage: python bookmark_organizer.py [command] [options]

Commands:
  list [category]        List bookmarks (optionally filter by category)
  add <url> [title]      Add a new bookmark
  delete <id>            Delete a bookmark by ID
  search <query>         Search bookmarks
  import <file>          Import bookmarks from file (HTML/JSON)
  export <file>          Export bookmarks to file
  categories             List all categories
  tags                   List all tags
  stats                  Show statistics
  check                  Check for broken links
  help                   Show this help message

v6.0.0 commands:
  ingest [id...]                Extract text + reading time + language for bookmark(s)
  snapshot <id>                 Capture single-file HTML snapshot of a bookmark
  embed [id...]                 Build/update vector embeddings (uses ingested text)
  semantic <query>              Vector-only semantic search
  hybrid <query>                Hybrid keyword + semantic (RRF) search
  summarize <id>                AI summary with inline [#cN] citations
  chat                          Conversational REPL over your collection (RAG)
  ask <question>                One-shot RAG question against your collection
  lint-tags [--apply]           Detect tag duplicates / casing drift; --apply merges
  dups                          Layered duplicate detector (URL + SimHash + embedding)
  scan [--hours N]              Dead-link scan (default: full library)
  digest                        On-this-day + rediscover + read-later view
  flow {{list|new|add|show}}    Manage research-trail flows
  feed {{list|add|fetch|remove}} Manage RSS/Atom feeds
  import-pocket <file>          Import Pocket export (HTML or JSON)
  import-readwise <csv>         Import Readwise Reader CSV
  import-pinboard <json>        Import Pinboard JSON export
  import-instapaper <csv>       Import Instapaper CSV export
  import-reddit <json>          Import Reddit saved.json
  zip-export [id|all] [path]    Per-bookmark or whole-collection ZIP export
  encrypt <pass> [src] [dst]    Encrypt a JSON file with AES-256-GCM
  decrypt <pass> <src> [dst]    Decrypt an encrypted JSON file
  read-later {{add|next|done|list}} <id>   Manage the read-later queue
  mcp-server                    Run the MCP server (stdio) for Claude/Cursor/etc.

Examples:
  python bookmark_organizer.py list
  python bookmark_organizer.py add https://example.com "Example Site"
  python bookmark_organizer.py hybrid "python async tutorials"
  python bookmark_organizer.py ingest        # ingest all
  python bookmark_organizer.py mcp-server    # expose to Claude Desktop
""")
    
    def _cmd_list(self, args):
        """List bookmarks"""
        if args:
            category = ' '.join(args)
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(category)
            print(f"\nBookmarks in '{category}':")
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
            print(f"\nAll Bookmarks ({len(bookmarks)}):")
        
        for bm in bookmarks[:50]:
            pin = "📌 " if bm.is_pinned else ""
            print(f"  [{bm.id}] {pin}{bm.title[:50]}")
            print(f"       {bm.url[:60]}")
            if bm.tags:
                print(f"       Tags: {', '.join(bm.tags)}")
            print()
    
    def _cmd_add(self, args):
        """Add a bookmark"""
        if not args:
            log.error("Error: URL required")
            return
        
        url = args[0]
        title = ' '.join(args[1:]) if len(args) > 1 else url
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        bookmark = self.bookmark_manager.add_bookmark_clean(
            url=url,
            title=title,
            category="Uncategorized / Needs Review",
        )
        if bookmark is None:
            print("Could not add bookmark: invalid URL or duplicate")
            return
        
        print(f"✓ Added: {title}")
        print(f"  URL: {url}")
        print(f"  ID: {bookmark.id}")
    
    def _cmd_delete(self, args):
        """Delete a bookmark"""
        if not args:
            log.error("Error: Bookmark ID required")
            return
        
        try:
            bm_id = int(args[0])
            bookmark = self.bookmark_manager.get_bookmark(bm_id)
            
            if bookmark:
                self.bookmark_manager.delete_bookmark(bm_id)
                print(f"✓ Deleted: {bookmark.title}")
            else:
                log.error(f"Error: Bookmark with ID {bm_id} not found")
        except ValueError:
            log.error("Error: Invalid bookmark ID")
    
    def _cmd_search(self, args):
        """Search bookmarks"""
        if not args:
            log.error("Error: Search query required")
            return
        
        query = ' '.join(args)
        results = self.bookmark_manager.search_bookmarks(query)
        
        print(f"\nSearch results for '{query}' ({len(results)} found):")
        for bm in results[:20]:
            print(f"  [{bm.id}] {bm.title[:50]}")
            print(f"       {bm.domain} | {bm.category}")
    
    def _cmd_import(self, args):
        """Import bookmarks"""
        if not args:
            log.error("Error: File path required")
            return
        
        filepath = args[0]
        
        if not Path(filepath).exists():
            log.error(f"Error: File not found: {filepath}")
            return
        
        if filepath.endswith('.html') or filepath.endswith('.htm'):
            added, dupes = self.bookmark_manager.import_html_file(filepath)
        elif filepath.endswith('.json'):
            added, dupes = self.bookmark_manager.import_json_file(filepath)
        else:
            log.error("Error: Unsupported file format (use .html or .json)")
            return
        
        print(f"✓ Imported {added} bookmarks ({dupes} duplicates skipped)")
    
    def _cmd_export(self, args):
        """Export bookmarks"""
        if not args:
            log.error("Error: File path required")
            return
        
        filepath = args[0]
        
        if filepath.endswith('.html'):
            self.bookmark_manager.export_html(filepath)
        elif filepath.endswith('.json'):
            self.bookmark_manager.export_json(filepath)
        elif filepath.endswith('.csv'):
            self.bookmark_manager.export_csv(filepath)
        elif filepath.endswith('.md'):
            self.bookmark_manager.export_markdown(filepath)
        else:
            # Default to HTML
            filepath += '.html'
            self.bookmark_manager.export_html(filepath)
        
        count = len(self.bookmark_manager.bookmarks)
        print(f"✓ Exported {count} bookmarks to {filepath}")
    
    def _cmd_categories(self, args):
        """List categories"""
        counts = self.bookmark_manager.get_category_counts()
        
        print(f"\nCategories ({len(counts)}):")
        for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
            icon = get_category_icon(cat)
            print(f"  {icon} {cat}: {count}")
    
    def _cmd_tags(self, args):
        """List tags"""
        counts = self.bookmark_manager.get_tag_counts()
        
        print(f"\nTags ({len(counts)}):")
        for tag, count in sorted(counts.items(), key=lambda x: -x[1])[:30]:
            print(f"  #{tag}: {count}")
    
    def _cmd_stats(self, args):
        """Show statistics"""
        stats = self.bookmark_manager.get_statistics()
        
        print(f"""
Bookmark Statistics
═══════════════════
Total Bookmarks:  {stats['total_bookmarks']}
Categories:       {stats['total_categories']}
Tags:             {stats['total_tags']}
Duplicates:       {stats['duplicate_bookmarks']}
Broken Links:     {stats['broken']}
Uncategorized:    {stats['uncategorized']}
With Tags:        {stats['with_tags']}
With Notes:       {stats['with_notes']}
Pinned:           {stats['pinned']}
Archived:         {stats['archived']}

Top Domains:
""")
        for domain, count in stats['top_domains'][:10]:
            print(f"  {domain}: {count}")
    
    def _cmd_check(self, args):
        """Check for broken links"""
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        
        print(f"Checking {len(bookmarks)} bookmarks for broken links...")
        print("(This may take a while)\n")
        
        broken = []
        for i, bm in enumerate(bookmarks):
            try:
                if not URLUtilities._is_safe_url(bm.url):
                    response = None
                    status_code = 0
                else:
                    response = requests.head(
                        bm.url,
                        timeout=5,
                        allow_redirects=False,
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    try:
                        status_code = response.status_code
                    finally:
                        response.close()
                if status_code >= 400 or status_code == 0:
                    broken.append((bm, status_code))
                    bm.is_valid = False
                else:
                    bm.is_valid = True
                bm.http_status = status_code
            except Exception:
                broken.append((bm, 0))
                bm.is_valid = False
                bm.http_status = 0
            
            # Progress
            if (i + 1) % 10 == 0:
                print(f"  Checked {i + 1}/{len(bookmarks)}...")
        
        self.bookmark_manager.save_bookmarks()

        print(f"\n✓ Check complete. Found {len(broken)} broken links:\n")
        for bm, status in broken[:20]:
            print(f"  [{bm.id}] {bm.title[:40]}")
            print(f"       {bm.url[:50]} (status: {status})")

    # ──────────────────────────────────────────────────────────────────
    # v6.0.0 commands
    # ──────────────────────────────────────────────────────────────────
    def _ai_config(self):
        from bookmark_organizer_pro.ai import AIConfigManager
        if not hasattr(self, "_ai_cfg"):
            self._ai_cfg = AIConfigManager()
        return self._ai_cfg

    def _embedder(self):
        from bookmark_organizer_pro.services.embeddings import EmbeddingService
        if not hasattr(self, "_emb"):
            self._emb = EmbeddingService()
        return self._emb

    def _vector_store(self):
        from bookmark_organizer_pro.services.vector_store import VectorStore
        if not hasattr(self, "_vstore"):
            self._vstore = VectorStore(self._embedder())
        return self._vstore

    def _bookmark_ids(self, args):
        if not args:
            return [b.id for b in self.bookmark_manager.get_all_bookmarks()]
        out = []
        for a in args:
            try:
                out.append(int(a))
            except ValueError:
                pass
        return out

    def _cmd_ingest(self, args):
        from bookmark_organizer_pro.services.ingest import ContentIngestor
        ing = ContentIngestor()
        ids = self._bookmark_ids(args)
        ok = updated = 0
        for bid in ids:
            bm = self.bookmark_manager.get_bookmark(bid)
            if not bm:
                continue
            r = ing.ingest_bookmark(bm)
            if r.success:
                ok += 1
                if r.apply_to(bm):
                    updated += 1
        if updated:
            self.bookmark_manager.save_bookmarks()
        print(f"Ingested {ok}/{len(ids)} bookmarks; {updated} updated.")

    def _cmd_snapshot(self, args):
        if not args:
            print("usage: snapshot <bookmark-id>")
            return
        from bookmark_organizer_pro.services.snapshot import SnapshotArchiver
        bm = self.bookmark_manager.get_bookmark(int(args[0]))
        if not bm:
            print("not found")
            return
        ok, msg = SnapshotArchiver().snapshot(bm)
        if ok:
            self.bookmark_manager.save_bookmarks()
            print(f"snapshot: {msg} ({bm.snapshot_size} bytes)")
        else:
            print(f"failed: {msg}")

    def _cmd_embed(self, args):
        from bookmark_organizer_pro.services.embeddings import EmbeddingService
        emb = self._embedder()
        if not emb.available:
            print("No embedding backend available. Install fastembed or model2vec.")
            return
        store = self._vector_store()
        ids = self._bookmark_ids(args)
        total_chunks = 0
        for bid in ids:
            bm = self.bookmark_manager.get_bookmark(bid)
            if not bm:
                continue
            text = ""
            if bm.extracted_text_path:
                from pathlib import Path as _P
                try:
                    text = _P(bm.extracted_text_path).read_text(encoding="utf-8")
                except OSError:
                    pass
            if not text:
                text = "\n".join(filter(None, [bm.title, bm.description]))
            chunks = EmbeddingService.chunk_text(text)
            n = store.upsert_bookmark(bm.id, chunks)
            if n:
                bm.embedding_model = emb.backend
                bm.embedding_dim = emb.dim
                total_chunks += n
        if total_chunks:
            self.bookmark_manager.save_bookmarks()
        print(f"Indexed {total_chunks} chunks across {len(ids)} bookmarks "
              f"({emb.backend}, dim={emb.dim}).")

    def _cmd_semantic(self, args):
        if not args:
            print("usage: semantic <query>")
            return
        store = self._vector_store()
        hits = store.search(" ".join(args), k=10)
        if not hits:
            print("(no results — did you `embed` first?)")
            return
        for h in hits:
            bm = self.bookmark_manager.get_bookmark(h["bookmark_id"])
            if not bm:
                continue
            print(f"[{bm.id}] {bm.title[:60]}  ({h['score']:.3f})")
            print(f"      {h['text'][:160]}")

    def _cmd_hybrid(self, args):
        if not args:
            print("usage: hybrid <query>")
            return
        from bookmark_organizer_pro.services.hybrid_search import HybridSearch
        hs = HybridSearch(self._vector_store())
        results = hs.search(self.bookmark_manager.get_all_bookmarks(),
                            " ".join(args), limit=15)
        for r in results:
            tag = "K+S" if r.semantic_rank is not None else "K"
            print(f"[{r.bookmark.id}] {r.bookmark.title[:60]}  "
                  f"({tag}, score {r.score:.3f})")

    def _cmd_summarize(self, args):
        if not args:
            print("usage: summarize <bookmark-id>")
            return
        from bookmark_organizer_pro.services.citation_summarizer import CitationSummarizer
        bm = self.bookmark_manager.get_bookmark(int(args[0]))
        if not bm:
            print("not found")
            return
        cs = CitationSummarizer(self._ai_config(), self._embedder())
        out = cs.summarize_bookmark(bm)
        print(out.summary)
        for c in out.citations:
            print(f"  · {c.chunk_id} ({c.char_start}-{c.char_end}): {c.text[:120]}")

    def _cmd_chat(self, args):
        from bookmark_organizer_pro.services.rag_chat import CollectionChat
        chat = CollectionChat(self._ai_config(), self._vector_store())
        print("Chat with your collection (blank line to exit).")
        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q:
                break
            turn = chat.ask(q)
            print(turn.answer)

    def _cmd_ask(self, args):
        if not args:
            print("usage: ask <question>")
            return
        from bookmark_organizer_pro.services.rag_chat import CollectionChat
        chat = CollectionChat(self._ai_config(), self._vector_store())
        turn = chat.ask(" ".join(args))
        print(turn.answer)

    def _cmd_lint_tags(self, args):
        from bookmark_organizer_pro.services.tag_linter import TagLinter
        apply = "--apply" in args
        bms = self.bookmark_manager.get_all_bookmarks()
        report = TagLinter().lint(bms)
        print(f"Tags: {report.total_tags}, Bookmarks: {report.total_bookmarks}")
        for s in report.suggestions[:20]:
            print(f"  {s.canonical}  <- {', '.join(s.variants)}  ({s.bookmark_count} bms)")
        if apply and report.suggestions:
            n = TagLinter().apply(bms, report.suggestions)
            self.bookmark_manager.save_bookmarks()
            print(f"Applied; {n} bookmarks rewritten.")

    def _cmd_dups(self, args):
        from bookmark_organizer_pro.services.dup_hybrid import HybridDuplicateDetector
        d = HybridDuplicateDetector(self._embedder() if self._embedder().available else None)
        rep = d.detect(self.bookmark_manager.get_all_bookmarks())
        for k, v in rep.method_counts.items():
            print(f"  {k}: {v} groups")
        for g in rep.groups[:30]:
            print(f"  [{g.method}] keep={g.canonical_id}  others={g.bookmark_ids[1:]}  "
                  f"conf={g.confidence:.2f}")

    def _cmd_scan(self, args):
        from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner
        hours = 0
        for a in args:
            if a.startswith("--hours"):
                _, _, val = a.partition("=")
                if val:
                    try: hours = int(val)
                    except ValueError: pass
        scanner = DeadLinkScanner(
            get_bookmarks=lambda: self.bookmark_manager.get_all_bookmarks()
        )
        records = scanner.scan_now(only_unchecked_for_hours=hours)
        self.bookmark_manager.save_bookmarks()
        print(f"Scan complete. {len(records)} dead/redirected links recorded.")
        for r in records[:20]:
            print(f"  {r.status} {r.url}  ({r.error})")

    def _cmd_digest(self, args):
        from bookmark_organizer_pro.services.digest import DailyDigestService
        d = DailyDigestService().build(self.bookmark_manager.get_all_bookmarks())
        for sec in d.sections:
            print(f"\n== {sec.title} ==")
            print(f"   {sec.description}")
            for bm in sec.bookmarks[:8]:
                print(f"   - {bm.title[:60]}  [{bm.domain}]")

    def _cmd_flow(self, args):
        from bookmark_organizer_pro.services.flows import FlowManager
        fm = FlowManager()
        if not args or args[0] == "list":
            for f in fm.list_flows():
                print(f"  {f.id[:8]}  {f.name}  ({len(f.steps)} steps)")
            return
        cmd = args[0]
        if cmd == "new":
            name = " ".join(args[1:]) or "Untitled flow"
            f = fm.create(name)
            print(f"Created flow {f.id[:8]} '{f.name}'")
        elif cmd == "add" and len(args) >= 3:
            flow_id, bid = args[1], int(args[2])
            note = " ".join(args[3:])
            for f in fm.list_flows():
                if f.id.startswith(flow_id):
                    fm.add_step(f.id, bid, note)
                    print(f"Added bookmark {bid} to flow '{f.name}'")
                    return
            print("flow not found")
        elif cmd == "show" and len(args) >= 2:
            flow_id = args[1]
            for f in fm.list_flows():
                if f.id.startswith(flow_id):
                    print(f"Flow: {f.name}")
                    for s in f.steps:
                        bm = self.bookmark_manager.get_bookmark(s.bookmark_id)
                        title = bm.title if bm else "(missing)"
                        print(f"  {s.position+1:2d}. [{s.bookmark_id}] {title[:60]}")
                        if s.note:
                            print(f"      note: {s.note}")
                    return
            print("flow not found")

    def _cmd_feed(self, args):
        from bookmark_organizer_pro.services.rss_feeds import FeedRegistry, FeedIngestor
        reg = FeedRegistry()
        if not args or args[0] == "list":
            for f in reg.list_feeds():
                print(f"  {f.id[:8]}  {f.name}  ({f.url})  [{f.ai_mode}]")
            return
        cmd = args[0]
        if cmd == "add" and len(args) >= 2:
            url = args[1]
            name = " ".join(args[2:]) or url
            cfg = reg.add(url, name=name)
            print(f"Added feed {cfg.id[:8]} '{cfg.name}'")
        elif cmd == "remove" and len(args) >= 2:
            for f in reg.list_feeds():
                if f.id.startswith(args[1]):
                    reg.remove(f.id)
                    print(f"Removed {f.name}")
                    return
            print("feed not found")
        elif cmd == "fetch":
            ing = FeedIngestor(
                reg, add_bookmark_callable=self.bookmark_manager.add_bookmark
            )
            results = ing.fetch_all()
            for fid, n in results.items():
                cfg = reg.get(fid)
                print(f"  {cfg.name if cfg else fid}: {n} new")

    def _cmd_import_pocket(self, args):
        if not args: print("usage: import-pocket <file>"); return
        from bookmark_organizer_pro.importers_extra import PocketExportImporter, import_into
        added, dupes = import_into(self.bookmark_manager, PocketExportImporter(), args[0])
        print(f"+{added} ({dupes} duplicates skipped)")

    def _cmd_import_readwise(self, args):
        if not args: print("usage: import-readwise <csv>"); return
        from bookmark_organizer_pro.importers_extra import ReadwiseReaderCSVImporter, import_into
        added, dupes = import_into(self.bookmark_manager, ReadwiseReaderCSVImporter(), args[0])
        print(f"+{added} ({dupes} duplicates skipped)")

    def _cmd_import_pinboard(self, args):
        if not args: print("usage: import-pinboard <json>"); return
        from bookmark_organizer_pro.importers_extra import PinboardJSONImporter, import_into
        added, dupes = import_into(self.bookmark_manager, PinboardJSONImporter(), args[0])
        print(f"+{added} ({dupes} duplicates skipped)")

    def _cmd_import_instapaper(self, args):
        if not args: print("usage: import-instapaper <csv>"); return
        from bookmark_organizer_pro.importers_extra import InstapaperImporter, import_into
        added, dupes = import_into(self.bookmark_manager, InstapaperImporter(), args[0])
        print(f"+{added} ({dupes} duplicates skipped)")

    def _cmd_import_reddit(self, args):
        if not args: print("usage: import-reddit <json>"); return
        from bookmark_organizer_pro.importers_extra import RedditSavedImporter, import_into
        added, dupes = import_into(self.bookmark_manager, RedditSavedImporter(), args[0])
        print(f"+{added} ({dupes} duplicates skipped)")

    def _cmd_zip_export(self, args):
        from bookmark_organizer_pro.services.zip_export import ZipExporter
        ze = ZipExporter()
        if not args or args[0] == "all":
            ok, path = ze.export_collection(self.bookmark_manager.get_all_bookmarks())
            print(f"{'wrote' if ok else 'failed'}: {path}")
        else:
            bm = self.bookmark_manager.get_bookmark(int(args[0]))
            if not bm: print("not found"); return
            ok, path = ze.export_one(bm)
            print(f"{'wrote' if ok else 'failed'}: {path}")

    def _cmd_encrypt(self, args):
        if len(args) < 1:
            print("usage: encrypt <passphrase> [src] [dst]"); return
        from bookmark_organizer_pro.constants import MASTER_BOOKMARKS_FILE
        from bookmark_organizer_pro.services.encryption import EncryptedStore
        passphrase = args[0]
        src = Path(args[1]) if len(args) > 1 else MASTER_BOOKMARKS_FILE
        dst = Path(args[2]) if len(args) > 2 else None
        try:
            out = EncryptedStore(passphrase).encrypt_file(src, dst)
            print(f"encrypted -> {out}")
        except Exception as e:
            print(f"error: {e}")

    def _cmd_decrypt(self, args):
        if len(args) < 2:
            print("usage: decrypt <passphrase> <src> [dst]"); return
        from bookmark_organizer_pro.services.encryption import EncryptedStore
        try:
            out = EncryptedStore(args[0]).decrypt_file(
                Path(args[1]), Path(args[2]) if len(args) > 2 else None,
            )
            print(f"decrypted -> {out}")
        except Exception as e:
            print(f"error: {e}")

    def _cmd_read_later(self, args):
        from bookmark_organizer_pro.services.read_later import ReadLaterQueue
        if not args:
            print("usage: read-later {add|next|done|list} [id]"); return
        sub = args[0]
        if sub == "list":
            for bm in ReadLaterQueue.list_queue(self.bookmark_manager.get_all_bookmarks()):
                print(f"  {bm.read_later_position:3d}. [{bm.id}] {bm.title[:60]}")
            return
        if sub == "next":
            bm = ReadLaterQueue.peek_next(self.bookmark_manager.get_all_bookmarks())
            if bm: print(f"[{bm.id}] {bm.title}\n  {bm.url}")
            else: print("(empty)")
            return
        if sub in {"add", "done"} and len(args) >= 2:
            bm = self.bookmark_manager.get_bookmark(int(args[1]))
            if not bm: print("not found"); return
            if sub == "add":
                ReadLaterQueue.enqueue(bm)
            else:
                ReadLaterQueue.complete(bm)
            self.bookmark_manager.save_bookmarks()
            print("ok")

    def _cmd_mcp_server(self, args):
        from bookmark_organizer_pro.mcp_server import main as _mcp_main
        _mcp_main()
