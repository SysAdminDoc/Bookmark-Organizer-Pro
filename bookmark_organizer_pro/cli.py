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

Examples:
  python bookmark_organizer.py list
  python bookmark_organizer.py add https://example.com "Example Site"
  python bookmark_organizer.py search python
  python bookmark_organizer.py export bookmarks.html
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
