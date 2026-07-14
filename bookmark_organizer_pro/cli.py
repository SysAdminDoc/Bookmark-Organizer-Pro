"""Command-line interface for bookmark operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION, MASTER_BOOKMARKS_FILE
from bookmark_organizer_pro.core import CategoryManager, get_category_icon
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from bookmark_organizer_pro.url_utils import URLUtilities


# =============================================================================
# CLI Tool
# =============================================================================
class _CLIParser(argparse.ArgumentParser):
    """Argument parser with compact, script-safe usage errors."""

    def error(self, message: str) -> None:  # noqa: D401 – override
        # When argparse cannot match a subcommand it says
        # "argument command: invalid choice: 'x' (choose from …)" —
        # detect that and emit the legacy "Unknown command" text.
        if "invalid choice" in message:
            # Extract the bad token from the argparse message.
            token = message.split("'")[1] if "'" in message else message
            print(f"Unknown command: {token}", file=sys.stderr)
        else:
            prog = self.prog or "bop"
            print(f"usage: {prog.split()[-1]} — {message}", file=sys.stderr)
        raise SystemExit(2)


class BookmarkCLI:
    """Command-line interface for Bookmark Organizer Pro."""

    def __init__(self):
        from bookmark_organizer_pro.constants import ensure_directories
        ensure_directories()
        self.category_manager = CategoryManager()
        self.tag_manager = TagManager()
        self.bookmark_manager = BookmarkManager(self.category_manager, self.tag_manager)

    @staticmethod
    def _error(message: str) -> None:
        """Print a user-facing error to stderr so pipes/scripts can see it.

        Many handlers previously logged errors via ``log.error`` (which may not
        reach the terminal) and the process still exited 0, so callers couldn't
        detect failures. Errors now go to stderr and handlers return non-zero.
        """
        print(message, file=sys.stderr)

    @classmethod
    def _failure(cls, message: str) -> int:
        """Report an operational or not-found failure."""
        cls._error(message)
        return 1

    @classmethod
    def _usage_error(cls, message: str) -> int:
        """Report invalid command usage."""
        cls._error(message)
        return 2

    # ──────────────────────────────────────────────────────────────────
    # Parser construction
    # ──────────────────────────────────────────────────────────────────
    def _build_parser(self) -> _CLIParser:
        parser = _CLIParser(
            prog="bop",
            description=f"{APP_NAME} CLI v{APP_VERSION}",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "--version", "-V", action="version",
            version=f"{APP_NAME} v{APP_VERSION}",
        )

        sub = parser.add_subparsers(
            dest="command", metavar="command",
            parser_class=_CLIParser,
        )

        # ── Core ────────────────────────────────────────────────────
        p = sub.add_parser("list", help="List bookmarks (optionally filter by category)")
        p.add_argument("category", nargs="*", help="Category to filter by")
        p.add_argument("--all", action="store_true", dest="show_all", help="Show all bookmarks")
        p.set_defaults(func=self._cmd_list)

        p = sub.add_parser("add", help="Add a new bookmark")
        p.add_argument("url", help="URL to bookmark")
        p.add_argument("title", nargs="*", help="Bookmark title")
        p.set_defaults(func=self._cmd_add)

        p = sub.add_parser("delete", help="Delete a bookmark by ID")
        p.add_argument("bookmark_id", type=int, help="Bookmark ID")
        p.add_argument("--force", "-y", "--yes", action="store_true", help="Skip confirmation")
        p.set_defaults(func=self._cmd_delete)

        p = sub.add_parser("search", help="Search bookmarks")
        p.add_argument("query", nargs="+", help="Search query")
        p.set_defaults(func=self._cmd_search)

        p = sub.add_parser("import", help="Import bookmarks from file (HTML/JSON)")
        p.add_argument("file", help="File path to import")
        p.set_defaults(func=self._cmd_import)

        p = sub.add_parser("migration", help="Preflight or apply a competitor export")
        p.add_argument("action", choices=["preflight", "apply"], help="Parse only or import after preflight")
        p.add_argument("source", choices=["linkwarden", "karakeep", "raindrop", "readwise"])
        p.add_argument("file", help="Competitor export path")
        p.add_argument("--report", help="Optional JSON report output path")
        p.set_defaults(func=self._cmd_migration)

        p = sub.add_parser("export", help="Export bookmarks to file")
        p.add_argument("file", help="Output file path")
        p.set_defaults(func=self._cmd_export)

        p = sub.add_parser("categories", help="List all categories")
        p.set_defaults(func=self._cmd_categories)

        p = sub.add_parser("tags", help="List all tags")
        p.set_defaults(func=self._cmd_tags)

        p = sub.add_parser("stats", help="Show statistics")
        p.set_defaults(func=self._cmd_stats)

        p = sub.add_parser("check", help="Check for broken links")
        p.set_defaults(func=self._cmd_check)

        p = sub.add_parser("help", help="Show help message")
        p.set_defaults(func=self._cmd_help)

        # ── AI ──────────────────────────────────────────────────────
        p = sub.add_parser("ai-audit", help="Inspect AI audit log")
        p.add_argument("action", nargs="?", default="learn-defaults",
                        help="Subcommand: stats | learn-defaults (default: learn-defaults)")
        p.add_argument("--min-confidence", type=float, default=0.7,
                        help="Ignore AI categories below this (default 0.7)")
        p.add_argument("--min-support", type=int, default=2,
                        help="Require >= N confident samples per domain (default 2)")
        p.add_argument("--json", action="store_true", dest="as_json",
                        help="Print the full machine-readable JSON report")
        p.add_argument("--out", help="Write the full JSON report to FILE")
        p.set_defaults(func=self._cmd_ai_audit)

        # ── v6.0.0 ─────────────────────────────────────────────────
        p = sub.add_parser("ingest", help="Extract text + reading time + language")
        p.add_argument("ids", nargs="*", type=int, help="Bookmark IDs (default: all)")
        p.add_argument("--templates", help="Optional JSON/YAML structured extraction templates")
        p.set_defaults(func=self._cmd_ingest)

        p = sub.add_parser("structured", help="Show structured metadata for a bookmark")
        p.add_argument("bookmark_id", type=int, help="Bookmark ID")
        p.add_argument("--json", action="store_true", dest="as_json", help="Print raw JSON payload")
        p.set_defaults(func=self._cmd_structured)

        p = sub.add_parser("snapshot", help="Capture single-file HTML snapshot")
        p.add_argument("bookmark_id", type=int, help="Bookmark ID")
        p.set_defaults(func=self._cmd_snapshot)

        p = sub.add_parser("embed", help="Build/update vector embeddings")
        p.add_argument("ids", nargs="*", type=int, help="Bookmark IDs (default: all)")
        p.add_argument("--model", dest="model", help="Embedding model name or key")
        p.set_defaults(func=self._cmd_embed)

        p = sub.add_parser("semantic", help="Vector-only semantic search")
        p.add_argument("query", nargs="+", help="Search query")
        p.set_defaults(func=self._cmd_semantic)

        p = sub.add_parser("hybrid", help="Hybrid keyword + semantic (RRF) search")
        p.add_argument("query", nargs="+", help="Search query")
        p.set_defaults(func=self._cmd_hybrid)

        p = sub.add_parser("summarize", help="AI summary with inline citations")
        p.add_argument("bookmark_id", type=int, help="Bookmark ID")
        p.set_defaults(func=self._cmd_summarize)

        p = sub.add_parser("chat", help="Conversational REPL over your collection (RAG)")
        p.set_defaults(func=self._cmd_chat)

        p = sub.add_parser("ask", help="One-shot RAG question")
        p.add_argument("question", nargs="+", help="Question to ask")
        p.set_defaults(func=self._cmd_ask)

        p = sub.add_parser("lint-tags", help="Detect tag duplicates / casing drift")
        p.add_argument("--apply", action="store_true", help="Apply merge fixes")
        p.set_defaults(func=self._cmd_lint_tags)

        p = sub.add_parser("dups", help="Layered duplicate detector")
        p.set_defaults(func=self._cmd_dups)

        p = sub.add_parser("scan", help="Dead-link scan")
        p.add_argument("--hours", type=int, default=0, help="Only scan unchecked for N hours")
        p.set_defaults(func=self._cmd_scan)

        p = sub.add_parser("digest", help="On-this-day + rediscover + read-later view")
        p.set_defaults(func=self._cmd_digest)

        # ── Flows ───────────────────────────────────────────────────
        p = sub.add_parser("flow", help="Manage research-trail flows")
        p.add_argument("action", nargs="?", default="list",
                        choices=["list", "new", "add", "show"],
                        help="Action: list, new, add, show")
        p.add_argument("flow_args", nargs="*", help="Action-specific arguments")
        p.set_defaults(func=self._cmd_flow)

        # ── Feeds ───────────────────────────────────────────────────
        p = sub.add_parser("feed", help="Manage RSS/Atom feeds")
        p.add_argument("action", nargs="?", default="list",
                        choices=["list", "add", "remove", "fetch"],
                        help="Action: list, add, remove, fetch")
        p.add_argument("feed_args", nargs="*", help="Action-specific arguments")
        p.set_defaults(func=self._cmd_feed)

        p = sub.add_parser("jobs", help="Inspect and manage local capture/index jobs")
        p.add_argument("action", nargs="?", default="health",
                       choices=["health", "list", "retry", "clear"])
        p.add_argument("job_id", nargs="?", help="Job ID prefix for retry")
        p.add_argument("--type", dest="job_type", default="", help="Filter by job type")
        p.add_argument("--outcome", choices=["running", "success", "failure", "cancelled"])
        p.add_argument("--retryable", action="store_true", help="Show retryable jobs only")
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--json", action="store_true", dest="as_json")
        p.set_defaults(func=self._cmd_jobs)

        p = sub.add_parser("imports", help="Inspect, retry, cancel, or roll back import sessions")
        p.add_argument("action", nargs="?", default="list",
                       choices=["list", "show", "retry", "cancel", "rollback"])
        p.add_argument("session_id", nargs="?", help="Import session ID prefix")
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--json", action="store_true", dest="as_json")
        p.set_defaults(func=self._cmd_import_sessions)

        # ── Importers ──────────────────────────────────────────────
        _importer_usage = {
            "import-pocket": "import-pocket <file>",
            "import-firefox-backup": "import-firefox-backup <file>",
            "import-readwise": "import-readwise <csv>",
            "import-pinboard": "import-pinboard <json>",
            "import-instapaper": "import-instapaper <csv>",
            "import-reddit": "import-reddit <json>",
            "import-matter": "import-matter <path_to_matter_export.csv>",
            "import-zotero": "import-zotero <path_to_zotero_export.rdf>",
            "import-wallabag": "import-wallabag <path_to_wallabag_export.json>",
            "import-arc": "import-arc <path_to_StorableSidebar.json>",
        }
        for name, helptext in [
            ("import-pocket", "Import Pocket export (HTML or JSON)"),
            ("import-firefox-backup", "Import Firefox bookmarkbackups JSON"),
            ("import-readwise", "Import Readwise Reader CSV"),
            ("import-pinboard", "Import Pinboard JSON export"),
            ("import-instapaper", "Import Instapaper CSV export"),
            ("import-reddit", "Import Reddit saved.json"),
            ("import-matter", "Import Matter export CSV"),
            ("import-zotero", "Import Zotero RDF export"),
            ("import-wallabag", "Import Wallabag JSON export"),
            ("import-arc", "Import Arc Browser StorableSidebar.json"),
        ]:
            p = sub.add_parser(name, help=helptext)
            p.add_argument("file", nargs="?", help="File to import")
            p.set_defaults(
                func=getattr(self, f"_cmd_{name.replace('-', '_')}"),
                _usage_hint=_importer_usage[name],
            )

        p = sub.add_parser("import-browser",
                          help="Import bookmarks from Chrome/Firefox/Edge/Brave profiles")
        p.add_argument("browser", nargs="?",
                       choices=["chrome", "firefox", "edge", "brave"],
                       help="Browser to import from (auto-detect if omitted)")
        p.add_argument("--profile", help="Profile name (default: Default)")
        p.set_defaults(func=self._cmd_import_browser)

        # ── Exporters ──────────────────────────────────────────────
        p = sub.add_parser("zip-export", help="Per-bookmark or whole-collection ZIP export")
        p.add_argument("target", nargs="?", default="all", help="Bookmark ID or 'all'")
        p.add_argument("path", nargs="?", help="Output path")
        p.set_defaults(func=self._cmd_zip_export)

        p = sub.add_parser("obsidian-export", help="Export to Obsidian vault")
        p.add_argument("vault_path", nargs="?", help="Path to Obsidian vault")
        p.add_argument("--tag", help="Filter by tag")
        p.add_argument("--category", help="Filter by category")
        p.add_argument("--since", help="Filter by date")
        p.set_defaults(func=self._cmd_obsidian_export)

        p = sub.add_parser("epub-export", help="Export bookmarks as EPUB")
        p.add_argument("--title", default="Bookmark Collection", help="EPUB title")
        p.add_argument("--output", help="Output path")
        p.add_argument("--tag", help="Filter by tag")
        p.set_defaults(func=self._cmd_epub_export)

        p = sub.add_parser("atom-export", help="Export Atom feed")
        p.add_argument("--title", default="Bookmarks", help="Feed title")
        p.add_argument("--output", help="Output path")
        p.add_argument("--tag", help="Filter by tag")
        p.set_defaults(func=self._cmd_atom_export)

        p = sub.add_parser("json-feed", help="Export JSON Feed")
        p.add_argument("--title", default="Bookmarks", help="Feed title")
        p.add_argument("--output", help="Output path")
        p.add_argument("--tag", help="Filter by tag")
        p.set_defaults(func=self._cmd_json_feed)

        p = sub.add_parser("opds-export", help="Export OPDS 1.2 acquisition feed")
        p.add_argument("--title", default="Bookmarks", help="Feed title")
        p.add_argument("--output", help="Output path")
        p.add_argument("--tag", help="Filter by tag")
        p.add_argument("--catalog-url", default="", help="Catalog URL")
        p.set_defaults(func=self._cmd_opds_export)

        p = sub.add_parser("opds2-export", help="Export OPDS 2.0 JSON-LD acquisition feed")
        p.add_argument("--title", default="Bookmarks", help="Feed title")
        p.add_argument("--output", help="Output path")
        p.add_argument("--tag", help="Filter by tag")
        p.add_argument("--catalog-url", default="", help="Catalog URL")
        p.set_defaults(func=self._cmd_opds2_export)

        p = sub.add_parser("graph-export", help="Export bookmark relationship graph JSON")
        p.add_argument("--output", help="Output path")
        p.add_argument("--limit", type=int, default=300, help="Max bookmarks (default 300)")
        p.set_defaults(func=self._cmd_graph_export)

        p = sub.add_parser("zotero-export", help="Export as Zotero RDF")
        p.add_argument("output", nargs="?", help="Output path")
        p.set_defaults(func=self._cmd_zotero_export)

        # ── Crypto ─────────────────────────────────────────────────
        p = sub.add_parser("encrypt", help="Encrypt a JSON file with AES-256-GCM")
        p.add_argument("passphrase", nargs="?", help="Encryption passphrase")
        p.add_argument("src", nargs="?", help="Source JSON file")
        p.add_argument("dst", nargs="?", help="Destination file")
        p.add_argument("--no-recovery", dest="recovery", action="store_false",
                       default=True, help="Skip recovery key generation")
        p.set_defaults(func=self._cmd_encrypt)

        p = sub.add_parser("decrypt", help="Decrypt an encrypted JSON file")
        p.add_argument("passphrase", nargs="?", help="Decryption passphrase")
        p.add_argument("src", nargs="?", help="Source encrypted file")
        p.add_argument("dst", nargs="?", help="Destination file")
        p.add_argument("--recovery-key", help="Decrypt using recovery key instead of passphrase")
        p.set_defaults(func=self._cmd_decrypt)

        # ── Read-later ─────────────────────────────────────────────
        p = sub.add_parser("read-later", help="Manage read-later queue")
        p.add_argument("action", choices=["add", "next", "done", "list"],
                        help="Action: add, next, done, list")
        p.add_argument("bookmark_id", nargs="?", type=int, help="Bookmark ID")
        p.set_defaults(func=self._cmd_read_later)

        # ── Reader ─────────────────────────────────────────────────
        p = sub.add_parser("reader", help="Manage reader highlights/notes")
        p.add_argument("action", nargs="?", default=None,
                        choices=["list", "add", "note", "delete", "due", "review", "export"],
                        help="Action: list, add, note, delete, due, review, export")
        p.add_argument("reader_args", nargs="*", help="Action-specific arguments")
        p.add_argument("--color", default="yellow",
                        choices=["yellow", "green", "blue", "pink"],
                        help="Highlight color (default: yellow)")
        p.add_argument("--note", default="", help="Note text")
        p.add_argument("--output", help="Export output directory")
        p.add_argument("--format", choices=["markdown", "csv", "json"], default="markdown",
                        help="Reader export format (default: markdown)")
        p.add_argument("--template", help="JSON annotation export template")
        p.add_argument("--changed-since", help="Only export highlights modified at/after ISO timestamp")
        p.set_defaults(func=self._cmd_reader)

        # ── Servers ────────────────────────────────────────────────
        p = sub.add_parser("api-server", help="Run the local HTTP API")
        p.add_argument("--port", type=int, default=8765, help="Port number (default 8765)")
        p.set_defaults(func=self._cmd_api_server)

        p = sub.add_parser("mcp-server", help="Run the MCP server (stdio)")
        p.set_defaults(func=self._cmd_mcp_server)

        p = sub.add_parser("mcp-http-server", help="Run the MCP Streamable HTTP server")
        p.add_argument("--host", default="127.0.0.1", help="Host (default 127.0.0.1)")
        p.add_argument("--port", type=int, default=8766, help="Port (default 8766)")
        p.add_argument("--path", default="/mcp", help="Endpoint path (default /mcp)")
        p.set_defaults(func=self._cmd_mcp_http_server)

        # ── Data ───────────────────────────────────────────────────
        p = sub.add_parser("sqlite-migrate", help="Copy JSON bookmarks into SQLite DB")
        p.add_argument("--source", help="Source JSON file")
        p.add_argument("--dest", help="Destination SQLite DB")
        p.set_defaults(func=self._cmd_sqlite_migrate)

        p = sub.add_parser("recovery-bundle", help="Create or restore a full-library backup")
        p.add_argument("action", choices=["create", "validate", "restore"])
        p.add_argument("path", help="Recovery bundle ZIP path")
        p.add_argument(
            "--apply", action="store_true",
            help="Apply a verified restore (restore is validation-only by default)",
        )
        p.set_defaults(func=self._cmd_recovery_bundle)

        p = sub.add_parser("updates", help="Manage update policy")
        p.add_argument("action", nargs="?", default="status",
                        choices=["status", "check", "configure", "download",
                                 "staged", "clean-staged", "plan", "apply"],
                        help="Action (default: status)")
        p.add_argument("--dry-run", "--preflight", action="store_true",
                        dest="dry_run", help="Preflight check only")
        # configure options
        p.add_argument("--enable", action="store_true", default=None,
                        dest="updates_enable", help="Enable updates")
        p.add_argument("--disable", action="store_true", default=None,
                        dest="updates_disable", help="Disable updates")
        p.add_argument("--metadata-url", help="Metadata URL")
        p.add_argument("--targets-url", help="Targets URL")
        p.add_argument("--channel", help="Update channel")
        p.add_argument("--allow-prerelease", action="store_true", default=None,
                        dest="allow_prerelease", help="Allow prerelease")
        p.add_argument("--no-prerelease", action="store_true", default=None,
                        dest="no_prerelease", help="Disallow prerelease")
        p.set_defaults(func=self._cmd_updates)

        # ── Collections ────────────────────────────────────────────
        p = sub.add_parser("smart-collections", help="Manage smart collections")
        p.add_argument("action", nargs="?", default="list",
                        choices=["list", "eval", "create", "update"],
                        help="Action: list, eval, create, update")
        p.add_argument(
            "collection_id",
            nargs="?",
            help="Collection ID/prefix, or collection name for create",
        )
        p.add_argument("--name", help="Replacement name for update")
        p.add_argument("--icon", help="Collection icon")
        p.add_argument("--tags", help="Comma-separated tags")
        p.add_argument("--categories", help="Comma-separated categories")
        p.add_argument("--domains", help="Comma-separated exact domains")
        p.add_argument("--content-types", help="Comma-separated content types")
        p.add_argument("--keywords", help="Comma-separated keywords")
        p.add_argument("--after", help="ISO-8601 lower date bound")
        p.add_argument("--before", help="ISO-8601 upper date bound")
        p.add_argument(
            "--read-later-only",
            action=argparse.BooleanOptionalAction,
            default=None,
        )
        p.add_argument(
            "--has-snapshot",
            action=argparse.BooleanOptionalAction,
            default=None,
        )
        p.set_defaults(func=self._cmd_smart_collections)

        p = sub.add_parser("nl-query", help="Natural language query")
        p.add_argument("query", nargs="*", help="Natural language query")
        p.set_defaults(func=self._cmd_nl_query)

        return parser

    # ──────────────────────────────────────────────────────────────────
    # Dispatch
    # ──────────────────────────────────────────────────────────────────
    def run(self, args: List[str]) -> int:
        """Run a CLI command. Returns a process exit code (0 = success)."""
        parser = self._build_parser()

        if not args:
            self._print_help()
            return 0

        try:
            ns = parser.parse_args(args)
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 2

        if not hasattr(ns, "func"):
            self._print_help()
            return 0

        try:
            result = ns.func(ns)
        except KeyboardInterrupt:
            self._error("Interrupted")
            return 130
        except Exception as exc:
            log.error(f"Command '{ns.command}' failed", exc_info=True)
            self._error(f"Error: {exc}")
            return 1
        return result if isinstance(result, int) else 0

    def _print_help(self, ns=None):
        """Print help message"""
        print(f"""
{APP_NAME} CLI v{APP_VERSION}

Usage: python main.py [command] [options]

Commands:
  list [category]        List bookmarks (optionally filter by category)
  add <url> [title]      Add a new bookmark
  delete <id>            Delete a bookmark by ID
  search <query>         Search bookmarks
  import <file>          Import bookmarks from file (HTML/JSON/Firefox JSONLZ4)
  migration <preflight|apply> <linkwarden|karakeep|raindrop|readwise> <file>
                         Report migration fidelity before a reversible import
  export <file>          Export bookmarks to file
  categories             List all categories
  tags                   List all tags
  stats                  Show statistics
  ai-audit [sub]         Inspect AI audit log; 'ai-audit learn-defaults' mines
                         default-category improvements from past AI runs
  check                  Check for broken links
  help                   Show this help message

v6.0.0 commands:
  ingest [id...]                Extract text + reading time + language for bookmark(s)
  structured <id>               Show structured metadata extracted from templates
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
  jobs {{health|list|retry|clear}} Inspect and manage local capture/index jobs
  import-pocket <file>          Import Pocket export (HTML or JSON)
  import-firefox-backup <file>  Import Firefox bookmarkbackups JSON
  import-readwise <csv>         Import Readwise Reader CSV
  import-pinboard <json>        Import Pinboard JSON export
  import-instapaper <csv>       Import Instapaper CSV export
  import-reddit <json>          Import Reddit saved.json
  import-wallabag <json>        Import Wallabag JSON export
  import-arc <json>             Import Arc Browser StorableSidebar.json
  opds-export [--output PATH]   Export an OPDS 1.2 acquisition feed
  graph-export [--output PATH]  Export bookmark relationship graph JSON
  zip-export [id|all] [path]    Per-bookmark or whole-collection ZIP export
  encrypt <pass> [src] [dst]    Encrypt a JSON file with AES-256-GCM
  decrypt <pass> <src> [dst]    Decrypt an encrypted JSON file
  read-later {{add|next|done|list}} <id>   Manage the read-later queue
  reader {{list|add|note|delete|due|review|export}}   Manage reader highlights/notes
    export <id|all> [--format markdown|csv|json] [--template FILE] [--changed-since ISO]
  smart-collections {{list|eval|create|update}}
                                Manage validated saved collection filters.
  api-server [--port N]          Run the local HTTP API for extensions/bookmarklet
  mcp-server                    Run the MCP server (stdio) for compatible clients.
  mcp-http-server [--host H] [--port N] [--path /mcp]
                                Run the MCP Streamable HTTP server on loopback.
  sqlite-migrate [--source JSON] [--dest DB]
                                Copy JSON bookmarks into an opt-in SQLite DB.
  updates [status|check|configure|download|staged|clean-staged|plan|apply [--dry-run]]
                                Manage disabled-by-default update policy.

Examples:
  python main.py list
  python main.py add https://example.com "Example Site"
  python main.py hybrid "python async tutorials"
  python main.py ingest        # ingest all
  python main.py structured 42 # show structured metadata
  python main.py mcp-server    # expose to an MCP-compatible client
  python main.py mcp-http-server --port 8766
  python main.py sqlite-migrate
  python main.py updates status
""")

    # ──────────────────────────────────────────────────────────────────
    # Core command handlers
    # ──────────────────────────────────────────────────────────────────
    def _cmd_help(self, ns: argparse.Namespace):
        """Show help."""
        self._print_help()

    def _cmd_list(self, ns: argparse.Namespace):
        """List bookmarks"""
        show_all = ns.show_all
        if ns.category:
            category = " ".join(ns.category)
            bookmarks = self.bookmark_manager.get_bookmarks_by_category(category)
            print(f"\nBookmarks in '{category}':")
        else:
            bookmarks = self.bookmark_manager.get_all_bookmarks()
            print(f"\nAll Bookmarks ({len(bookmarks)}):")

        limit = len(bookmarks) if show_all else 50
        for bm in bookmarks[:limit]:
            pin = "\U0001f4cc " if bm.is_pinned else ""
            print(f"  [{bm.id}] {pin}{bm.title[:50]}")
            print(f"       {bm.url[:60]}")
            if bm.tags:
                print(f"       Tags: {', '.join(bm.tags)}")
            print()
        if not show_all and len(bookmarks) > limit:
            print(f"  Showing {limit} of {len(bookmarks)}. Use --all to see everything.")

    def _cmd_add(self, ns: argparse.Namespace):
        """Add a bookmark"""
        url = ns.url
        title = " ".join(ns.title) if ns.title else url

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        bookmark = self.bookmark_manager.add_bookmark_clean(
            url=url,
            title=title,
            category="Uncategorized / Needs Review",
        )
        if bookmark is None:
            self._error("Could not add bookmark: invalid URL or duplicate")
            return 1

        print(f"✓ Added: {title}")
        print(f"  URL: {url}")
        print(f"  ID: {bookmark.id}")
        return 0

    def _cmd_delete(self, ns: argparse.Namespace):
        """Delete a bookmark (prompts for confirmation unless --force/-y)."""
        bm_id = ns.bookmark_id
        bookmark = self.bookmark_manager.get_bookmark(bm_id)
        if not bookmark:
            self._error(f"Error: Bookmark with ID {bm_id} not found")
            return 1

        if not ns.force:
            try:
                answer = input(f"Delete [{bm_id}] {bookmark.title[:60]}? [y/N] ").strip().lower()
            except EOFError:
                answer = ""
            if answer not in ("y", "yes"):
                print("Cancelled")
                return 0

        self.bookmark_manager.delete_bookmark(bm_id)
        print(f"✓ Deleted: {bookmark.title}")
        return 0

    def _cmd_search(self, ns: argparse.Namespace):
        """Search bookmarks"""
        query = " ".join(ns.query)
        results = self.bookmark_manager.search_bookmarks(query)

        print(f"\nSearch results for '{query}' ({len(results)} found):")
        for bm in results[:20]:
            print(f"  [{bm.id}] {bm.title[:50]}")
            print(f"       {bm.domain} | {bm.category}")
        return 0

    def _cmd_ai_audit(self, ns: argparse.Namespace):
        """Inspect the AI audit log and mine default-pattern improvements."""
        import json as _json
        from bookmark_organizer_pro.services.ai_audit_log import (
            analyze_for_default_improvements, get_audit_stats,
        )

        sub = ns.action

        if sub == "stats":
            print(_json.dumps(get_audit_stats(), indent=2, ensure_ascii=False))
            return 0

        if sub not in ("learn-defaults", "defaults", "learn"):
            return self._usage_error(f"Unknown ai-audit subcommand: {sub}")

        min_conf = ns.min_confidence
        min_support = ns.min_support

        report = analyze_for_default_improvements(
            min_confidence=min_conf, min_support=min_support)

        if ns.out:
            out_path = ns.out
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_text(
                _json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote full report to {out_path}")

        if ns.as_json:
            print(_json.dumps(report, indent=2, ensure_ascii=False))
            return 0

        # Human-readable summary.
        s = report["summary"]
        print(f"\nAI categorization vs. shipped defaults "
              f"({report['categorize_entries_with_evaluation']} evaluated, "
              f"{report['unique_domains']} domains, conf>={min_conf}, support>={min_support}):")
        print(f"  + add patterns:    {s['add_patterns']}  (defaults missed; AI was confident)")
        print(f"  ~ review patterns: {s['review_patterns']}  (defaults disagree with AI)")
        print(f"  = confirmed:       {s['confirmed']}  (defaults already correct)\n")

        if report["add_patterns"]:
            print("Top default patterns to ADD (domain → category, support, avg-conf):")
            for r in report["add_patterns"][:30]:
                print(f"  domain:{r['domain']:<32} → {r['suggested_category']:<28} "
                      f"(n={r['support']}, conf={r['avg_confidence']})")
        if report["review_patterns"]:
            print("\nExisting defaults the AI consistently DISAGREES with "
                  "(⚠ = likely AI artifact, do not auto-apply):")
            for r in report["review_patterns"][:20]:
                flag = f"  ⚠ {r['suspect_reason']}" if r.get("suspect") else ""
                print(f"  {r['domain']:<30} default={r['current_default']!r} "
                      f"→ AI={r['suggested_category']!r} "
                      f"(n={r['support']}, share={r.get('share', 0):.0%}, "
                      f"conf={r['avg_confidence']}){flag}")
        if report["summary"].get("suspect_flagged"):
            print(f"\n  ({report['summary']['suspect_flagged']} candidate(s) flagged suspect "
                  f"— search-engine/portal or sensitive reclassification)")
        print()
        return 0

    def _cmd_import(self, ns: argparse.Namespace):
        """Import bookmarks"""
        filepath = ns.file

        if not Path(filepath).exists():
            self._error(f"Error: File not found: {filepath}")
            return 1

        lower_path = filepath.lower()
        if lower_path.endswith(".html") or lower_path.endswith(".htm"):
            added, dupes = self.bookmark_manager.import_html_file(filepath)
        elif lower_path.endswith(".json"):
            from bookmark_organizer_pro.importers import FirefoxBookmarkBackupImporter
            if FirefoxBookmarkBackupImporter.looks_like_backup(filepath):
                from bookmark_organizer_pro.importers_extra import import_into
                importer = FirefoxBookmarkBackupImporter()
                added, dupes = import_into(self.bookmark_manager, importer, filepath)
                print(
                    f"✓ Imported {added} bookmarks ({dupes} duplicates skipped; "
                    f"{importer.stats.skipped} invalid/missing URL skipped)"
                )
                return 0
            added, dupes = self.bookmark_manager.import_json_file(filepath)
        elif lower_path.endswith(".jsonlz4"):
            from bookmark_organizer_pro.importers import FirefoxBookmarkBackupImporter
            from bookmark_organizer_pro.importers_extra import import_into
            importer = FirefoxBookmarkBackupImporter()
            added, dupes = import_into(self.bookmark_manager, importer, filepath)
            print(
                f"✓ Imported {added} bookmarks ({dupes} duplicates skipped; "
                f"{importer.stats.skipped} invalid/missing URL skipped)"
            )
            return 0
        else:
            self._error("Error: Unsupported file format (use .html, .json, or .jsonlz4)")
            return 1

        print(f"✓ Imported {added} bookmarks ({dupes} duplicates skipped)")
        return 0

    def _cmd_export(self, ns: argparse.Namespace):
        """Export bookmarks"""
        filepath = ns.file

        if filepath.endswith(".html"):
            self.bookmark_manager.export_html(filepath)
        elif filepath.endswith(".json"):
            self.bookmark_manager.export_json(filepath)
        elif filepath.endswith(".csv"):
            self.bookmark_manager.export_csv(filepath)
        elif filepath.endswith(".md"):
            self.bookmark_manager.export_markdown(filepath)
        else:
            print(f"Note: unrecognized extension; writing HTML to {filepath}.html")
            filepath += ".html"
            self.bookmark_manager.export_html(filepath)

        count = len(self.bookmark_manager.get_all_bookmarks())
        print(f"✓ Exported {count} bookmarks to {filepath}")
        return 0

    def _cmd_migration(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.migration import apply_migration, preflight_migration

        try:
            plan = preflight_migration(
                ns.source,
                ns.file,
                existing_urls=[bookmark.url for bookmark in self.bookmark_manager.get_all_bookmarks()],
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return self._failure(f"Migration preflight failed: {exc}")
        report = plan.report.to_dict()
        rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
        print(rendered)
        if ns.report:
            report_path = Path(ns.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered + "\n", encoding="utf-8")
            print(f"Migration report written: {report_path}")
        if ns.action == "preflight":
            print("Dry run only; library unchanged.")
            return 0
        try:
            result = apply_migration(self.bookmark_manager, plan)
        except RuntimeError as exc:
            return self._failure(f"Migration blocked: {exc}")
        print(
            f"Migration applied: {result.added} added, {result.duplicates} duplicates skipped; "
            f"restore safepoint {result.safepoint}"
        )
        return 0

    def _cmd_categories(self, ns: argparse.Namespace):
        """List categories"""
        counts = self.bookmark_manager.get_category_counts()

        print(f"\nCategories ({len(counts)}):")
        for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
            icon = get_category_icon(cat)
            print(f"  {icon} {cat}: {count}")

    def _cmd_tags(self, ns: argparse.Namespace):
        """List tags"""
        counts = self.bookmark_manager.get_tag_counts()

        print(f"\nTags ({len(counts)}):")
        for tag, count in sorted(counts.items(), key=lambda x: -x[1])[:30]:
            print(f"  #{tag}: {count}")

    def _cmd_stats(self, ns: argparse.Namespace):
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
        for domain, count in stats["top_domains"][:10]:
            print(f"  {domain}: {count}")

    def _cmd_check(self, ns: argparse.Namespace):
        """Check for broken links (multi-threaded)"""
        from bookmark_organizer_pro.services.egress import public_egress as requests
        from concurrent.futures import ThreadPoolExecutor, as_completed
        bookmarks = self.bookmark_manager.get_all_bookmarks()

        print(f"Checking {len(bookmarks)} bookmarks for broken links...")
        print("(Using 5 concurrent workers)\n")

        def _check_one(bm):
            try:
                if not URLUtilities._is_safe_url(bm.url):
                    return bm.id, 0, False
                response = requests.head(
                    bm.url, timeout=5, allow_redirects=False,
                    headers={"User-Agent": "BookmarkOrganizerPro/6.2 LinkChecker"},
                )
                status = response.status_code
                response.close()
                return bm.id, status, status < 400
            except Exception:
                return bm.id, 0, False

        broken = []
        checked = 0
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_check_one, bm): bm for bm in bookmarks}
            for future in as_completed(futures):
                bm = futures[future]
                bm_id, status, is_valid = future.result()
                bm.http_status = status
                bm.is_valid = is_valid
                if not is_valid:
                    broken.append((bm, status))
                checked += 1
                if checked % 20 == 0:
                    print(f"  Checked {checked}/{len(bookmarks)}...")

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

    def _bookmark_ids_from_ns(self, ns: argparse.Namespace):
        """Extract bookmark IDs from namespace; empty list means all."""
        ids = getattr(ns, "ids", None) or []
        if not ids:
            return [b.id for b in self.bookmark_manager.get_all_bookmarks()]
        return ids

    def _cmd_ingest(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.ingest import ContentIngestor
        ing = ContentIngestor(template_path=getattr(ns, "templates", None))
        ids = self._bookmark_ids_from_ns(ns)
        ok = updated = missing = 0
        for bid in ids:
            bm = self.bookmark_manager.get_bookmark(bid)
            if not bm:
                missing += 1
                continue
            r = ing.ingest_bookmark(bm)
            if r.success:
                ok += 1
                if r.apply_to(bm):
                    updated += 1
        if updated:
            self.bookmark_manager.save_bookmarks()
        print(f"Ingested {ok}/{len(ids)} bookmarks; {updated} updated.")
        if missing:
            return self._failure(f"{missing} requested bookmark(s) were not found")
        return 0

    def _cmd_structured(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.extraction_templates import (
            format_structured_value,
            structured_metadata_fields,
            structured_metadata_payload,
        )

        bm = self.bookmark_manager.get_bookmark(ns.bookmark_id)
        if not bm:
            return self._failure("Bookmark not found")
        payload = structured_metadata_payload(bm)
        if not payload:
            print("No structured metadata.")
            return
        if ns.as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return
        template = payload.get("template") or "Structured metadata"
        print(f"Structured metadata: {template}")
        fields = structured_metadata_fields(bm)
        for key, value in sorted(fields.items()):
            print(f"- {key}: {format_structured_value(value)}")

    def _cmd_snapshot(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.snapshot import SnapshotArchiver
        bid = ns.bookmark_id
        bm = self.bookmark_manager.get_bookmark(bid)
        if not bm:
            return self._failure("Bookmark not found")
        ok, msg = SnapshotArchiver().snapshot(bm)
        if ok:
            self.bookmark_manager.save_bookmarks()
            print(f"snapshot: {msg} ({bm.snapshot_size} bytes)")
        else:
            return self._failure(f"Snapshot failed: {msg}")
        return 0

    def _cmd_embed(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.embeddings import EmbeddingService, RECOMMENDED_MODELS
        model_name = None
        if ns.model:
            key = ns.model
            if key in RECOMMENDED_MODELS:
                model_name = RECOMMENDED_MODELS[key]["model"]
            else:
                model_name = key
        if model_name:
            self._emb = EmbeddingService(model_name=model_name)
        emb = self._embedder()
        if not emb.available:
            return self._failure(
                "No embedding backend available. Install fastembed or model2vec."
            )
        store = self._vector_store()
        ids = self._bookmark_ids_from_ns(ns)
        total_chunks = missing = 0
        for bid in ids:
            bm = self.bookmark_manager.get_bookmark(bid)
            if not bm:
                missing += 1
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
        if missing:
            return self._failure(f"{missing} requested bookmark(s) were not found")
        return 0

    def _cmd_semantic(self, ns: argparse.Namespace):
        store = self._vector_store()
        hits = store.search(" ".join(ns.query), k=10)
        if not hits:
            print("(no results — did you `embed` first?)")
            return
        for h in hits:
            bm = self.bookmark_manager.get_bookmark(h["bookmark_id"])
            if not bm:
                continue
            print(f"[{bm.id}] {bm.title[:60]}  ({h['score']:.3f})")
            print(f"      {h['text'][:160]}")

    def _cmd_hybrid(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.hybrid_search import HybridSearch
        hs = HybridSearch(self._vector_store())
        results = hs.search(self.bookmark_manager.get_all_bookmarks(),
                            " ".join(ns.query), limit=15)
        for r in results:
            tag = "K+S" if r.semantic_rank is not None else "K"
            print(f"[{r.bookmark.id}] {r.bookmark.title[:60]}  "
                  f"({tag}, score {r.score:.3f})")

    def _cmd_summarize(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.citation_summarizer import CitationSummarizer
        bid = ns.bookmark_id
        bm = self.bookmark_manager.get_bookmark(bid)
        if not bm:
            return self._failure("Bookmark not found")
        cs = CitationSummarizer(self._ai_config(), self._embedder())
        out = cs.summarize_bookmark(bm)
        print(out.summary)
        for c in out.citations:
            print(f"  · {c.chunk_id} ({c.char_start}-{c.char_end}): {c.text[:120]}")

    def _cmd_chat(self, ns: argparse.Namespace):
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

    def _cmd_ask(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.rag_chat import CollectionChat
        chat = CollectionChat(self._ai_config(), self._vector_store())
        turn = chat.ask(" ".join(ns.question))
        print(turn.answer)

    def _cmd_lint_tags(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.tag_linter import TagLinter
        apply = ns.apply
        bms = self.bookmark_manager.get_all_bookmarks()
        report = TagLinter().lint(bms)
        print(f"Tags: {report.total_tags}, Bookmarks: {report.total_bookmarks}")
        for s in report.suggestions[:20]:
            print(f"  {s.canonical}  <- {', '.join(s.variants)}  ({s.bookmark_count} bms)")
        if apply and report.suggestions:
            n = TagLinter().apply(bms, report.suggestions)
            self.bookmark_manager.save_bookmarks()
            print(f"Applied; {n} bookmarks rewritten.")

    def _cmd_dups(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.dup_hybrid import HybridDuplicateDetector
        d = HybridDuplicateDetector(self._embedder() if self._embedder().available else None)
        rep = d.detect(self.bookmark_manager.get_all_bookmarks())
        for k, v in rep.method_counts.items():
            print(f"  {k}: {v} groups")
        for g in rep.groups[:30]:
            print(f"  [{g.method}] keep={g.canonical_id}  others={g.bookmark_ids[1:]}  "
                  f"conf={g.confidence:.2f}")

    def _cmd_scan(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner
        hours = ns.hours
        scanner = DeadLinkScanner(
            get_bookmarks=lambda: self.bookmark_manager.get_all_bookmarks()
        )
        records = scanner.scan_now(only_unchecked_for_hours=hours)
        self.bookmark_manager.save_bookmarks()
        print(f"Scan complete. {len(records)} dead/redirected links recorded.")
        for r in records[:20]:
            print(f"  {r.status} {r.url}  ({r.error})")

    def _cmd_digest(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.digest import DailyDigestService
        d = DailyDigestService().build(self.bookmark_manager.get_all_bookmarks())
        for sec in d.sections:
            print(f"\n== {sec.title} ==")
            print(f"   {sec.description}")
            for bm in sec.bookmarks[:8]:
                print(f"   - {bm.title[:60]}  [{bm.domain}]")

    def _cmd_flow(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.flows import FlowManager
        fm = FlowManager()
        cmd = ns.action
        flow_args = ns.flow_args or []

        if cmd == "list":
            for f in fm.list_flows():
                print(f"  {f.id[:8]}  {f.name}  ({len(f.steps)} steps)")
            return
        if cmd == "new":
            name = " ".join(flow_args) or "Untitled flow"
            f = fm.create(name)
            print(f"Created flow {f.id[:8]} '{f.name}'")
            return 0
        elif cmd == "add" and len(flow_args) >= 2:
            try:
                bid = int(flow_args[1])
            except ValueError:
                return self._usage_error("error: bookmark ID must be an integer")
            flow_id = flow_args[0]
            note = " ".join(flow_args[2:])
            for f in fm.list_flows():
                if f.id.startswith(flow_id):
                    fm.add_step(f.id, bid, note)
                    print(f"Added bookmark {bid} to flow '{f.name}'")
                    return 0
            return self._failure("Flow not found")
        elif cmd == "show" and flow_args:
            flow_id = flow_args[0]
            for f in fm.list_flows():
                if f.id.startswith(flow_id):
                    print(f"Flow: {f.name}")
                    for s in f.steps:
                        bm = self.bookmark_manager.get_bookmark(s.bookmark_id)
                        title = bm.title if bm else "(missing)"
                        print(f"  {s.position + 1:2d}. [{s.bookmark_id}] {title[:60]}")
                        if s.note:
                            print(f"      note: {s.note}")
                    return 0
            return self._failure("Flow not found")
        return self._usage_error("usage: flow {list|new|add|show} [arguments]")

    def _cmd_feed(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.rss_feeds import FeedRegistry, FeedIngestor
        reg = FeedRegistry()
        cmd = ns.action
        feed_args = ns.feed_args or []

        if cmd == "list":
            for f in reg.list_feeds():
                print(f"  {f.id[:8]}  {f.name}  ({f.url})  [{f.ai_mode}]")
            return
        if cmd == "add" and feed_args:
            url = feed_args[0]
            name = " ".join(feed_args[1:]) or url
            cfg = reg.add(url, name=name)
            print(f"Added feed {cfg.id[:8]} '{cfg.name}'")
            return 0
        elif cmd == "remove" and feed_args:
            for f in reg.list_feeds():
                if f.id.startswith(feed_args[0]):
                    reg.remove(f.id)
                    print(f"Removed {f.name}")
                    return 0
            return self._failure("Feed not found")
        elif cmd == "fetch":
            ing = FeedIngestor(
                reg, add_bookmark_callable=self.bookmark_manager.add_bookmark
            )
            results = ing.fetch_all()
            for fid, n in results.items():
                cfg = reg.get(fid)
                print(f"  {cfg.name if cfg else fid}: {n} new")
            failures = sum(1 for count in results.values() if count < 0)
            if failures:
                return self._failure(f"{failures} feed(s) failed to fetch")
            return 0
        return self._usage_error("usage: feed {list|add|remove|fetch} [arguments]")

    def _cmd_jobs(self, ns: argparse.Namespace):
        """Inspect, retry, or clear the local-only capture/index ledger."""
        from bookmark_organizer_pro.services.job_ledger import JobLedger

        ledger = JobLedger()
        if ns.action == "health":
            health = ledger.health()
            if ns.as_json:
                print(json.dumps(health, indent=2))
                return
            print(
                f"Jobs: {health['jobs']} completed, {health['running']} running, "
                f"{health['failures']} failed ({health['failure_rate']:.1%})"
            )
            print(
                f"Retryable: {health['retryable_failures']}; average: "
                f"{health['average_duration_ms']} ms; 7d processed: "
                f"{health['storage_growth_7d_bytes']} bytes"
            )
            for job_type, metrics in sorted(health["by_type"].items()):
                print(
                    f"  {job_type}: {metrics['jobs']} jobs, "
                    f"{metrics['failures']} failed, {metrics['bytes']} bytes"
                )
            return

        if ns.action == "list":
            records = ledger.list_records(
                job_type=ns.job_type,
                outcome=ns.outcome or "",
                retryable=True if ns.retryable else None,
                limit=ns.limit,
            )
            if ns.as_json:
                from dataclasses import asdict
                print(json.dumps([asdict(record) for record in records], indent=2))
                return
            if not records:
                print("No matching local jobs.")
                return
            for record in records:
                subject = f"bookmark={record.bookmark_id}" if record.bookmark_id is not None else record.domain
                retry = " retryable" if record.retryable else ""
                print(
                    f"{record.job_id} {record.job_type:<12} {record.outcome:<9} "
                    f"{record.duration_ms:>6} ms {record.bytes_processed:>9} bytes "
                    f"{subject or '-'}{retry}"
                )
                if record.error:
                    print(f"  {record.error}")
            return

        if ns.action == "clear":
            removed = ledger.clear(job_type=ns.job_type, outcome=ns.outcome or "")
            print(f"Cleared {removed} local job record(s).")
            return

        if ns.action == "retry":
            if not ns.job_id:
                return self._usage_error("usage: jobs retry <job-id>")
            record = ledger.get(ns.job_id)
            if record is None:
                return self._failure("Job not found or ID prefix is ambiguous.")
            if not record.retryable:
                return self._failure("Job is not retryable.")
            ok, detail = self._retry_local_job(record)
            if not ok:
                return self._failure("Retry failed: " + detail)
            print("Retried: " + detail)
            return 0

    def _retry_local_job(self, record) -> tuple[bool, str]:
        """Dispatch a durable job record without storing sensitive arguments."""
        bookmark = (
            self.bookmark_manager.get_bookmark(record.bookmark_id)
            if record.bookmark_id is not None else None
        )
        if record.job_type in {"snapshot", "ingest", "embedding", "metadata", "link_check"} and not bookmark:
            return False, "bookmark no longer exists"

        if record.job_type == "snapshot":
            from bookmark_organizer_pro.services.snapshot import SnapshotArchiver
            ok, detail = SnapshotArchiver().snapshot(bookmark)
            if ok:
                self.bookmark_manager.save_bookmarks()
            return ok, detail
        if record.job_type == "ingest":
            from bookmark_organizer_pro.services.ingest import ContentIngestor
            result = ContentIngestor().ingest_bookmark(bookmark)
            if result.success and result.apply_to(bookmark):
                self.bookmark_manager.save_bookmarks()
            return result.success, result.error or "content ingested"
        if record.job_type == "embedding":
            from bookmark_organizer_pro.services.embeddings import EmbeddingService
            text = "\n".join(filter(None, [bookmark.title, bookmark.description]))
            if bookmark.extracted_text_path:
                try:
                    text = Path(bookmark.extracted_text_path).read_text(encoding="utf-8")
                except OSError:
                    pass
            chunks = EmbeddingService.chunk_text(text)
            count = self._vector_store().upsert_bookmark(bookmark.id, chunks)
            if count:
                bookmark.embedding_model = self._embedder().backend
                bookmark.embedding_dim = self._embedder().dim
                self.bookmark_manager.save_bookmarks()
            return bool(count), f"indexed {count} chunk(s)"
        if record.job_type == "metadata":
            from bookmark_organizer_pro.utils.metadata import fetch_page_metadata
            metadata = fetch_page_metadata(bookmark.url)
            changed = False
            for field in ("title", "description", "favicon_url"):
                value = metadata.get(field)
                if value and getattr(bookmark, field, "") != value:
                    setattr(bookmark, field, value)
                    changed = True
            if changed:
                self.bookmark_manager.save_bookmarks()
            return bool(metadata.get("title") or metadata.get("description")), "metadata refreshed"
        if record.job_type == "link_check":
            from bookmark_organizer_pro.link_checker import LinkChecker
            valid, status = LinkChecker()._check_url(bookmark)
            bookmark.is_valid = valid
            bookmark.http_status = status
            self.bookmark_manager.save_bookmarks()
            return bool(status), f"HTTP {status}" if status else "no HTTP response"
        if record.job_type == "rss":
            from bookmark_organizer_pro.services.job_ledger import safe_domain
            from bookmark_organizer_pro.services.rss_feeds import FeedIngestor, FeedRegistry
            registry = FeedRegistry()
            matches = [feed for feed in registry.list_feeds() if safe_domain(feed.url) == record.domain]
            if len(matches) != 1:
                return False, "feed no longer exists or domain is ambiguous"
            count = FeedIngestor(registry, self.bookmark_manager.add_bookmark).fetch_one(matches[0].id)
            return True, f"added {count} item(s)"
        return False, f"retry is unavailable for {record.job_type} jobs"

    @staticmethod
    def _print_import_session(importer) -> None:
        report = getattr(importer, "last_session_report", None)
        if not report:
            return
        causes = "; ".join(f"{cause} ({count})" for cause, count in report.causes.items()) or "none"
        print(
            f"  session={report.session_id} status={report.status} failed={report.failed} "
            f"losses={report.losses} pending={report.pending} duration={report.duration_ms}ms "
            f"causes={causes}"
        )

    def _cmd_import_sessions(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

        sessions = ImportSessionManager()
        action = ns.action
        if action == "list":
            reports = sessions.list(ns.limit)
            if ns.as_json:
                print(json.dumps([report.to_dict() for report in reports], indent=2))
            else:
                for report in reports:
                    print(
                        f"{report.session_id} {report.status:<11} {report.source:<24} "
                        f"added={report.added} duplicate={report.duplicates} "
                        f"failed={report.failed} loss={report.losses} "
                        f"pending={report.pending} duration={report.duration_ms}ms"
                    )
            return 0
        if not ns.session_id:
            self._error(f"imports {action} requires a session ID")
            return 2
        try:
            if action == "show":
                session = sessions.get(ns.session_id)
                if not session:
                    raise RuntimeError("Import session was not found or the prefix is ambiguous")
                report = sessions.report(ns.session_id)
            elif action == "retry":
                report = sessions.retry(self.bookmark_manager, ns.session_id)
            elif action == "cancel":
                if not sessions.request_cancel(ns.session_id):
                    raise RuntimeError("Import session was not found")
                report = sessions.report(ns.session_id)
            else:
                report = sessions.rollback(self.bookmark_manager, ns.session_id)
        except RuntimeError as exc:
            self._error(str(exc))
            return 1
        if ns.as_json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            causes = "; ".join(f"{cause} ({count})" for cause, count in report.causes.items()) or "none"
            print(
                f"Session {report.session_id}: {report.status}; {report.added} added, "
                f"{report.duplicates} duplicates, {report.failed} failed, "
                f"{report.losses} losses, {report.pending} pending, "
                f"{report.duration_ms}ms; causes: {causes}"
            )
        return 0

    def _cmd_import_pocket(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import PocketExportImporter, import_into
        importer = PocketExportImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"+{added} ({dupes} duplicates skipped)")
        self._print_import_session(importer)

    def _cmd_import_firefox_backup(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers import FirefoxBookmarkBackupImporter
        from bookmark_organizer_pro.importers_extra import import_into
        importer = FirefoxBookmarkBackupImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(
            f"Firefox backup import: {added} added, {dupes} duplicates skipped, "
            f"{importer.stats.skipped} invalid/missing URL skipped"
        )
        self._print_import_session(importer)

    def _cmd_import_readwise(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import ReadwiseReaderCSVImporter, import_into
        importer = ReadwiseReaderCSVImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"+{added} ({dupes} duplicates skipped)")
        self._print_import_session(importer)

    def _cmd_import_pinboard(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import PinboardJSONImporter, import_into
        importer = PinboardJSONImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"+{added} ({dupes} duplicates skipped)")
        self._print_import_session(importer)

    def _cmd_import_instapaper(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import InstapaperImporter, import_into
        importer = InstapaperImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"+{added} ({dupes} duplicates skipped)")
        self._print_import_session(importer)

    def _cmd_import_reddit(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import RedditSavedImporter, import_into
        importer = RedditSavedImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"+{added} ({dupes} duplicates skipped)")
        self._print_import_session(importer)

    def _cmd_zip_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.zip_export import ZipExporter
        ze = ZipExporter()
        target = ns.target
        if target == "all":
            ok, path = ze.export_collection(self.bookmark_manager.get_all_bookmarks())
            if not ok:
                return self._failure(f"ZIP export failed: {path}")
            print(f"wrote: {path}")
        else:
            try:
                bid = int(target)
            except ValueError:
                return self._usage_error("error: bookmark ID must be an integer")
            bm = self.bookmark_manager.get_bookmark(bid)
            if not bm:
                return self._failure("Bookmark not found")
            ok, path = ze.export_one(bm)
            if not ok:
                return self._failure(f"ZIP export failed: {path}")
            print(f"wrote: {path}")
        return 0

    def _cmd_encrypt(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.constants import MASTER_BOOKMARKS_FILE as _MBF
        from bookmark_organizer_pro.services.encryption import EncryptedStore, generate_recovery_key
        import getpass as _getpass
        passphrase = ns.passphrase
        src = Path(ns.src) if ns.src else _MBF
        dst = Path(ns.dst) if ns.dst else None
        use_recovery = getattr(ns, 'recovery', True)
        if not passphrase:
            passphrase = _getpass.getpass("Passphrase: ")
        if not passphrase:
            return self._usage_error("error: passphrase required")
        try:
            store = EncryptedStore(passphrase)
            if use_recovery:
                rk = generate_recovery_key()
                data = src.read_bytes()
                encrypted = store.encrypt_with_recovery(data, rk)
                import tempfile
                out_path = dst or src.with_suffix(src.suffix + ".enc")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=out_path.resolve().parent, suffix=".tmp")
                try:
                    import os as _os
                    _os.write(fd, encrypted)
                    _os.close(fd)
                    fd = -1
                    _os.replace(tmp, out_path)
                except Exception:
                    if fd >= 0:
                        try:
                            _os.close(fd)
                        except OSError:
                            pass
                    if _os.path.exists(tmp):
                        _os.remove(tmp)
                    raise
                print(f"encrypted -> {out_path}")
                print(f"\nRECOVERY KEY (save this — it can decrypt without the passphrase):\n  {rk}\n")
            else:
                out = store.encrypt_file(src, dst)
                print(f"encrypted -> {out}")
            store.close()
        except Exception as e:
            return self._failure(f"Encryption failed: {e}")
        return 0

    def _cmd_decrypt(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.encryption import EncryptedStore
        import getpass as _getpass
        passphrase = ns.passphrase
        src_val = ns.src
        dst = Path(ns.dst) if ns.dst else None
        recovery_key = getattr(ns, 'recovery_key', None)

        if recovery_key and passphrase:
            # Recovery mode has no passphrase, so its one or two positional
            # values are source and optional destination respectively.
            if src_val and dst is None:
                dst = Path(src_val)
            src_val = passphrase
            passphrase = None
        elif passphrase and not src_val:
            src_val = passphrase
            passphrase = None

        if not src_val:
            return self._usage_error("usage: decrypt [passphrase] <src> [dst]")

        src = Path(src_val)

        if recovery_key:
            try:
                out_path = dst or src.with_suffix("")
                EncryptedStore.decrypt_recovery_file(src, recovery_key, out_path)
                print(f"decrypted (recovery key) -> {out_path}")
            except Exception as e:
                return self._failure(f"Decryption failed: {e}")
            return 0

        if not passphrase:
            passphrase = _getpass.getpass("Passphrase: ")
        if not passphrase:
            return self._usage_error("error: passphrase required")
        try:
            store = EncryptedStore(passphrase)
            out = store.decrypt_file(src, dst)
            store.close()
            print(f"decrypted -> {out}")
        except Exception as e:
            return self._failure(f"Decryption failed: {e}")
        return 0

    def _cmd_read_later(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.read_later import ReadLaterQueue
        sub = ns.action
        if sub == "list":
            for bm in ReadLaterQueue.list_queue(self.bookmark_manager.get_all_bookmarks()):
                print(f"  {bm.read_later_position:3d}. [{bm.id}] {bm.title[:60]}")
            return
        if sub == "next":
            bm = ReadLaterQueue.peek_next(self.bookmark_manager.get_all_bookmarks())
            if bm:
                print(f"[{bm.id}] {bm.title}\n  {bm.url}")
            else:
                print("(empty)")
            return
        if sub in {"add", "done"}:
            bid = ns.bookmark_id
            if bid is None:
                return self._usage_error(
                    "usage: read-later {add|next|done|list} [id]"
                )
            bm = self.bookmark_manager.get_bookmark(bid)
            if not bm:
                return self._failure("Bookmark not found")
            if sub == "add":
                ReadLaterQueue.enqueue(bm)
            else:
                ReadLaterQueue.complete(bm)
            self.bookmark_manager.save_bookmarks()
            print("ok")
            return 0

    def _cmd_reader(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.reader_annotations import (
            HIGHLIGHT_COLORS,
            ReaderAnnotationStore,
            export_annotations,
            export_bookmark_highlights,
        )
        usage = (
            "usage: reader {list <bookmark-id>|add <bookmark-id> <start> <end> "
            "[--color yellow|green|blue|pink] [--note TEXT]|note <highlight-id> "
            "<text>|delete <highlight-id>|export <bookmark-id|all> [--format markdown|csv|json] "
            "[--template FILE] [--changed-since ISO] [--output PATH]}"
        )
        sub = ns.action
        reader_args = ns.reader_args or []

        if not sub:
            return self._usage_error(usage)

        store = ReaderAnnotationStore()

        if sub == "list" and reader_args:
            try:
                bid = int(reader_args[0])
            except ValueError:
                return self._usage_error("error: bookmark ID must be an integer")
            highlights = store.list_for_bookmark(bid)
            if not highlights:
                print("(no reader highlights)")
                return 0
            for item in highlights:
                preview = " ".join(item.text.split())[:80]
                note = f" note={item.note[:40]}" if item.note else ""
                print(f"{item.id} {item.char_start}-{item.char_end} "
                      f"{item.color}: {preview}{note}")
            return 0

        if sub == "add" and len(reader_args) >= 3:
            try:
                bid = int(reader_args[0])
                start = int(reader_args[1])
                end = int(reader_args[2])
            except ValueError:
                return self._usage_error(
                    "error: bookmark ID and range must be integers"
                )
            color = ns.color
            note = ns.note
            if color.lower() not in HIGHLIGHT_COLORS:
                return self._usage_error(
                    "error: color must be one of yellow, green, blue, pink"
                )
            bm = self.bookmark_manager.get_bookmark(bid)
            if not bm:
                return self._failure("Bookmark not found")
            try:
                highlight = store.add_for_bookmark(bm, start, end, color=color, note=note)
            except ValueError as exc:
                return self._usage_error(f"error: {exc}")
            print(f"highlight added: {highlight.id}")
            return 0

        if sub == "note" and len(reader_args) >= 2:
            if store.set_note(reader_args[0], " ".join(reader_args[1:])):
                print("ok")
                return 0
            return self._failure("Highlight not found")

        if sub == "delete" and reader_args:
            if not store.delete(reader_args[0]):
                return self._failure("Highlight not found")
            print("ok")
            return 0

        if sub == "due":
            due = store.due_for_review()
            if not due:
                print("No highlights due for review.")
                return 0
            print(f"{len(due)} highlight(s) due for review:")
            for item in due[:20]:
                preview = " ".join(item.text.split())[:60]
                next_r = item.sr_next_review or "new"
                print(f"  {item.id} [interval={item.sr_interval}d next={next_r}] {preview}")
            return 0

        if sub == "review" and len(reader_args) >= 2:
            hid = reader_args[0]
            try:
                quality = int(reader_args[1])
            except ValueError:
                return self._usage_error("error: quality must be 0-5")
            if store.record_review(hid, quality):
                h = store.get(hid)
                print(f"reviewed: interval={h.sr_interval}d ease={h.sr_ease:.2f} next={h.sr_next_review}")
            else:
                return self._failure("Highlight not found")
            return 0

        if sub == "export" and reader_args:
            export_all = reader_args[0].lower() == "all"
            if export_all:
                bookmarks = self.bookmark_manager.get_all_bookmarks()
                highlights = store.list_all()
            else:
                try:
                    bid = int(reader_args[0])
                except ValueError:
                    return self._usage_error(
                        "error: bookmark ID must be an integer or 'all'"
                    )
                bm = self.bookmark_manager.get_bookmark(bid)
                if not bm:
                    return self._failure("Bookmark not found")
                bookmarks = [bm]
                highlights = store.list_for_bookmark(bid)

            advanced = export_all or ns.format != "markdown" or ns.template or ns.changed_since
            if not advanced:
                path = export_bookmark_highlights(
                    bookmarks[0], highlights,
                    output_dir=Path(ns.output) if ns.output else None,
                )
            else:
                suffix = {"markdown": ".md", "csv": ".csv", "json": ".json"}[ns.format]
                output = Path(ns.output) if ns.output else (
                    Path.cwd() / f"reader-annotations{suffix}"
                )
                if output.exists() and output.is_dir():
                    output = output / f"reader-annotations{suffix}"
                elif not output.suffix:
                    output = output / f"reader-annotations{suffix}"
                try:
                    path = export_annotations(
                        bookmarks,
                        highlights,
                        output,
                        output_format=ns.format,
                        template_path=ns.template,
                        changed_since=ns.changed_since,
                    )
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    return self._failure(f"Reader export failed: {exc}")
            print(f"reader highlights exported: {path}")
            return 0

        return self._usage_error(usage)

    def _cmd_mcp_server(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.mcp_server import main as _mcp_main
        _mcp_main()

    def _cmd_mcp_http_server(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.mcp_server import serve_http
        host = ns.host
        port = ns.port
        path = ns.path
        if not host or port < 1 or port > 65535 or not path:
            return self._usage_error(
                "usage: mcp-http-server [--host HOST] [--port N] [--path /mcp]"
            )
        serve_http(host=host, port=port, path=path)

    def _cmd_sqlite_migrate(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.core import migrate_json_to_sqlite
        source = Path(ns.source).expanduser() if ns.source else MASTER_BOOKMARKS_FILE
        dest = Path(ns.dest).expanduser() if ns.dest else MASTER_BOOKMARKS_FILE.with_suffix(".sqlite")
        count = migrate_json_to_sqlite(source, dest)
        print(f"Migrated {count} bookmarks to {dest}")

    def _cmd_recovery_bundle(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.recovery_bundle import (
            create_recovery_bundle,
            restore_recovery_bundle,
            validate_recovery_bundle,
        )

        path = Path(ns.path).expanduser()
        if ns.action == "create":
            created = create_recovery_bundle(path)
            report = validate_recovery_bundle(created)
            print(f"Recovery bundle created: {created}")
            print(f"Verified: {report.file_count} files, {report.total_bytes} bytes")
            return 0
        if ns.action == "validate":
            report = validate_recovery_bundle(path)
            self._print_recovery_bundle_report(report)
            return 0 if report.valid else 1
        result = restore_recovery_bundle(path, dry_run=not ns.apply)
        self._print_recovery_bundle_report(result.report)
        if not result.report.valid:
            return 1
        if result.applied:
            print(
                f"Restore applied: {result.restored_count} bookmarks reopened "
                f"with the {result.storage_backend} backend."
            )
            print(f"Rollback bundle: {result.rollback_bundle}")
        else:
            print("Dry run only; no files were changed. Re-run with --apply to restore.")
        return 0

    @staticmethod
    def _print_recovery_bundle_report(report):
        state = "valid" if report.valid else "invalid"
        print(f"Recovery bundle: {state}")
        print(f"Files: {report.file_count}; uncompressed bytes: {report.total_bytes}")
        if report.storage_backend:
            print(f"Storage backend: {report.storage_backend}")
        for action in report.actions:
            suffix = f" — {action.detail}" if action.detail else ""
            print(f"Plan: {action.kind} {action.path}{suffix}")
        for warning in report.warnings:
            print(f"Warning: {warning}")
        for error in report.errors:
            BookmarkCLI._error(f"Error: {error}")
        for index_name, required in sorted(report.rebuild.items()):
            if required is True:
                print(f"Rebuild after restore: {index_name}")

    def _cmd_updates(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.updates import UpdateManager

        manager = UpdateManager()
        sub = ns.action
        if sub == "status":
            self._print_update_status(manager.status())
            return
        if sub == "check":
            result = manager.check_for_updates()
            if result.update_available:
                print(f"Update available: {result.latest_version}")
                print(f"Target: {result.target_name}")
            elif result.checked:
                print(f"No update available: {result.reason}")
            else:
                print(f"Update check not ready: {result.reason}")
            if result.error:
                self._error(f"Error: {result.error}")
            return 0 if result.checked and not result.error else 1
        if sub == "configure":
            return self._configure_updates_from_ns(manager, ns)
        if sub == "download":
            return self._print_update_download_result(manager.download_update())
        if sub == "staged":
            return self._print_staged_update(manager.staged_update())
        if sub == "clean-staged":
            return self._print_update_cleanup(manager.clear_staged_update())
        if sub == "plan":
            self._print_update_apply_plan(manager.build_apply_plan())
            return 0
        if sub == "apply":
            if ns.dry_run:
                result = manager.apply_preflight()
                self._print_update_apply_preflight(result)
                return 1 if result.blockers else 0
            self._print_update_apply_gate(manager)
            return 1
        return self._usage_error(
            "usage: updates [status|check|configure|download|staged|"
            "clean-staged|plan|apply [--dry-run]]"
        )

    def _print_update_status(self, status):
        policy = status.policy
        print(f"Updates: {'enabled' if policy.enabled else 'disabled'}")
        print(f"Repository: {'configured' if policy.configured else 'not configured'}")
        print(f"Channel: {policy.channel}")
        print(f"Current version: {status.current_version}")
        print(f"tufup: {'available' if status.tufup_installed else 'not installed'}")
        print(f"Trusted root: {'present' if status.trusted_root_exists else 'missing'}")
        print(f"Status: {status.reason}")

    def _print_update_download_result(self, result):
        if result.downloaded:
            print(f"Update staged: {result.latest_version}")
            if result.target_name:
                print(f"Target: {result.target_name}")
            for staged_path in result.staged_paths:
                print(f"Staged: {staged_path}")
            print("Run updates apply after install and rollback gates are available.")
            return 0
        if result.error:
            self._error(f"Update download failed: {result.reason}")
            self._error(f"Error: {result.error}")
            return 1
        if result.update_available:
            return self._failure(f"Update available but not staged: {result.reason}")
        if result.checked:
            print(f"No update available: {result.reason}")
            return 0
        return self._failure(f"Update download not ready: {result.reason}")

    def _print_staged_update(self, status):
        if not status.available:
            print(f"Staged update: {status.reason}")
            if status.error:
                self._error(f"Error: {status.error}")
                return 1
            return 0
        print(f"Staged update: {status.latest_version}")
        print(f"Current version: {status.current_version}")
        print(f"Channel: {status.channel}")
        print(f"Manifest: {status.manifest_path}")
        print(f"Status: {status.reason}")
        if status.target_name:
            print(f"Target: {status.target_name}")
        for staged_path in status.staged_paths:
            print(f"Staged: {staged_path}")
        if status.error:
            self._error(f"Error: {status.error}")
            return 1
        return 0

    def _print_update_apply_gate(self, manager):
        status = manager.status()
        print("Update apply is disabled in this release.")
        print("Run updates check to verify trusted metadata readiness first.")
        if not status.can_check:
            print(f"Readiness: {status.reason}")

    def _print_update_apply_preflight(self, result):
        print(f"Update apply preflight: {result.reason}")
        if result.latest_version:
            print(f"Target version: {result.latest_version}")
        if result.target_name:
            print(f"Target: {result.target_name}")
        for staged_path in result.staged_paths:
            print(f"Staged: {staged_path}")
        for blocker in result.blockers:
            print(f"Blocker: {blocker}")

    def _print_update_cleanup(self, result):
        print(f"Staged update cleanup: {result.reason}")
        print(f"Removed manifest: {'yes' if result.removed_manifest else 'no'}")
        for removed_target in result.removed_targets:
            print(f"Removed target: {removed_target}")
        for error in result.errors:
            self._error(f"Error: {error}")
        return 1 if result.errors else 0

    def _print_update_apply_plan(self, result):
        print(f"Update apply plan: {result.reason}")
        print(f"Install dir: {result.install_dir}")
        print(f"Rollback dir: {result.rollback_dir}")
        if result.latest_version:
            print(f"Target version: {result.latest_version}")
        if result.target_name:
            print(f"Target: {result.target_name}")
        for staged_path in result.staged_paths:
            print(f"Staged: {staged_path}")
        for action in result.actions:
            print(f"Plan: {action}")
        for blocker in result.blockers:
            print(f"Blocker: {blocker}")

    def _configure_updates_from_ns(self, manager, ns: argparse.Namespace):
        enabled = None
        if ns.updates_enable:
            enabled = True
        elif ns.updates_disable:
            enabled = False

        allow_prerelease = None
        if ns.allow_prerelease:
            allow_prerelease = True
        elif ns.no_prerelease:
            allow_prerelease = False

        try:
            policy = manager.configure(
                enabled=enabled,
                metadata_url=ns.metadata_url,
                targets_url=ns.targets_url,
                channel=ns.channel,
                allow_prerelease=allow_prerelease,
            )
        except ValueError as exc:
            return self._failure(f"Could not configure updates: {exc}")
        print(f"Updates configured: {'enabled' if policy.enabled else 'disabled'}")
        print(f"Repository: {'configured' if policy.configured else 'not configured'}")
        return 0

    def _cmd_api_server(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.api import BookmarkAPI
        port = ns.port
        if port < 1 or port > 65535:
            return self._usage_error("usage: api-server [--port N]")

        api = BookmarkAPI(self.bookmark_manager, port=port)
        try:
            api.start()
            print(f"Local API running at http://127.0.0.1:{api.port}")
            print("Press Ctrl+C to stop.")
            while True:
                import time
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\nStopping local API.")
            return 130
        finally:
            api.stop()

    def _cmd_smart_collections(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.smart_collections import (
            SmartCollectionFilter,
            SmartCollectionManager,
        )
        mgr = SmartCollectionManager()
        sub = ns.action
        if sub == "list":
            for sc in mgr.list_all():
                print(f"  [{sc.id[:8]}] {sc.name}")
                f = sc.filters
                parts = []
                if f.tags:
                    parts.append(f"tags={f.tags}")
                if f.categories:
                    parts.append(f"categories={f.categories}")
                if f.domains:
                    parts.append(f"domains={f.domains}")
                if f.keywords:
                    parts.append(f"keywords={f.keywords}")
                if parts:
                    print(f"    Filters: {', '.join(parts)}")
            for diagnostic in mgr.diagnostics:
                self._error(diagnostic.message)
            return 1 if mgr.diagnostics else 0
        elif sub == "eval":
            sc_id = ns.collection_id
            if not sc_id:
                return self._usage_error(
                    "usage: smart-collections eval <id>"
                )
            collection = mgr.resolve(sc_id)
            if collection is None:
                return self._failure("Smart collection not found or prefix is ambiguous")
            bms = self.bookmark_manager.get_all_bookmarks()
            matches = collection.evaluate(bms)
            print(f"Matches: {len(matches)}")
            for bm in matches[:20]:
                print(f"  {bm.title[:60]} — {bm.url[:60]}")
            return 0
        elif sub == "create":
            if not ns.collection_id:
                return self._usage_error("usage: smart-collections create <name> [filters]")
            try:
                collection = mgr.create(
                    ns.collection_id,
                    self._smart_collection_filter_from_ns(ns, SmartCollectionFilter()),
                    icon=ns.icon or "",
                )
            except ValueError as exc:
                return self._usage_error(str(exc))
            print(f"Created smart collection [{collection.id[:8]}] {collection.name}")
            return 0
        elif sub == "update":
            if not ns.collection_id:
                return self._usage_error("usage: smart-collections update <id> [changes]")
            collection = mgr.resolve(ns.collection_id)
            if collection is None:
                return self._failure("Smart collection not found or prefix is ambiguous")
            try:
                updated = mgr.update(
                    collection.id,
                    name=ns.name,
                    icon=ns.icon,
                    filters=self._smart_collection_filter_from_ns(ns, collection.filters),
                )
            except ValueError as exc:
                return self._usage_error(str(exc))
            print(f"Updated smart collection [{updated.id[:8]}] {updated.name}")
            return 0
        else:
            return self._usage_error(
                "usage: smart-collections [list|eval|create|update]"
            )

    @staticmethod
    def _smart_collection_filter_from_ns(ns, base):
        from dataclasses import asdict
        from bookmark_organizer_pro.services.smart_collections import SmartCollectionFilter

        values = asdict(base)
        for field_name in ("tags", "categories", "domains", "content_types", "keywords"):
            raw = getattr(ns, field_name, None)
            if raw is not None:
                values[field_name] = [item.strip() for item in raw.split(",") if item.strip()]
        for field_name in ("after", "before", "read_later_only", "has_snapshot"):
            value = getattr(ns, field_name, None)
            if value is not None:
                values[field_name] = value
        return SmartCollectionFilter(**values)

    def _cmd_nl_query(self, ns: argparse.Namespace):
        query = " ".join(ns.query) if ns.query else ""
        if not query:
            return self._usage_error("usage: nl-query <natural language query>")
        try:
            from bookmark_organizer_pro.services.nl_query import NLQueryService
            from bookmark_organizer_pro.ai import AIConfigManager
            config = AIConfigManager()
            service = NLQueryService(config)
            bms = self.bookmark_manager.get_all_bookmarks()
            results = service.query(query, bms)
            print(f"Results: {len(results)}")
            for bm in results[:20]:
                print(f"  {bm.title[:60]} — {bm.url[:60]}")
        except Exception as e:
            return self._failure(f"NL query failed: {e}")

    def _cmd_obsidian_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.obsidian_export import export_collection
        if not ns.vault_path:
            return self._usage_error(
                "usage: obsidian-export <vault_path> [--tag TAG] "
                "[--category CAT] [--since DATE]"
            )
        vault = Path(ns.vault_path).expanduser()
        bms = self.bookmark_manager.get_all_bookmarks()
        paths = export_collection(bms, vault, tag_filter=ns.tag,
                                  category_filter=ns.category, since=ns.since)
        print(f"Exported {len(paths)} bookmarks to {vault}")

    def _cmd_epub_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.epub_export import export_epub
        bms = self.bookmark_manager.get_all_bookmarks()
        if ns.tag:
            tag_l = ns.tag.lower()
            bms = [b for b in bms if any(t.lower() == tag_l for t in b.tags)]
        output = Path(ns.output) if ns.output else None
        path = export_epub(bms, output_path=output, title=ns.title)
        print(f"EPUB exported: {path} ({len(bms)} bookmarks)")

    def _cmd_atom_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.feed_export import export_atom
        bms = self.bookmark_manager.get_all_bookmarks()
        if ns.tag:
            tag_l = ns.tag.lower()
            bms = [b for b in bms if any(t.lower() == tag_l for t in b.tags)]
        output = Path(ns.output) if ns.output else None
        path = export_atom(bms, title=ns.title, output_path=output)
        print(f"Atom feed exported: {path} ({len(bms)} entries)")

    def _cmd_json_feed(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.feed_export import export_json_feed
        bms = self.bookmark_manager.get_all_bookmarks()
        if ns.tag:
            tag_l = ns.tag.lower()
            bms = [b for b in bms if any(t.lower() == tag_l for t in b.tags)]
        output = Path(ns.output) if ns.output else None
        path = export_json_feed(bms, title=ns.title, output_path=output)
        print(f"JSON Feed exported: {path} ({len(bms)} items)")

    def _cmd_opds_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.feed_export import export_opds
        bms = self.bookmark_manager.get_all_bookmarks()
        if ns.tag:
            tag_l = ns.tag.lower()
            bms = [b for b in bms if any(t.lower() == tag_l for t in b.tags)]
        output = Path(ns.output) if ns.output else None
        path = export_opds(bms, title=ns.title, output_path=output,
                           catalog_url=ns.catalog_url)
        print(f"OPDS feed exported: {path} ({len(bms)} entries)")

    def _cmd_opds2_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.feed_export import export_opds2
        bms = self.bookmark_manager.get_all_bookmarks()
        if ns.tag:
            tag_l = ns.tag.lower()
            bms = [b for b in bms if any(t.lower() == tag_l for t in b.tags)]
        output = Path(ns.output) if ns.output else None
        path = export_opds2(bms, title=ns.title, output_path=output,
                            catalog_url=ns.catalog_url)
        print(f"OPDS 2.0 feed exported: {path} ({len(bms)} entries)")

    def _cmd_graph_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.bookmark_graph import export_bookmark_graph_json
        output = Path(ns.output) if ns.output else None
        limit = ns.limit
        bookmarks = self.bookmark_manager.get_all_bookmarks()
        path = export_bookmark_graph_json(bookmarks, output_path=output, max_bookmarks=limit)
        print(f"Graph exported: {path} ({min(len(bookmarks), max(0, limit))} bookmarks)")

    def _cmd_import_matter(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import MatterImporter, import_into
        importer = MatterImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"Matter import: {added} added, {dupes} duplicates skipped")
        self._print_import_session(importer)

    def _cmd_import_zotero(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.services.zotero_interop import import_zotero_rdf
        bookmarks = import_zotero_rdf(ns.file)
        added = 0
        dupes = 0
        for bm in bookmarks:
            if self.bookmark_manager.url_exists(bm.url):
                dupes += 1
                continue
            self.bookmark_manager.add_bookmark(bm, save=False)
            added += 1
        if added:
            self.bookmark_manager.save_bookmarks()
        print(f"Zotero import: {added} bookmarks added ({dupes} duplicates skipped)")

    def _cmd_zotero_export(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.services.zotero_interop import export_zotero_rdf
        output = Path(ns.output) if ns.output else None
        bms = self.bookmark_manager.get_all_bookmarks()
        path = export_zotero_rdf(bms, output_path=output)
        print(f"Zotero RDF export: {path} ({len(bms)} items)")

    def _cmd_import_wallabag(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import WallabagJSONImporter, import_into
        importer = WallabagJSONImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"Wallabag import: {added} added, {dupes} duplicates skipped")
        self._print_import_session(importer)

    def _cmd_import_arc(self, ns: argparse.Namespace):
        if not ns.file:
            return self._usage_error(f"usage: {ns._usage_hint}")
        from bookmark_organizer_pro.importers_extra import ArcBrowserImporter, import_into
        importer = ArcBrowserImporter()
        added, dupes = import_into(self.bookmark_manager, importer, ns.file)
        print(f"Arc Browser import: {added} added, {dupes} duplicates skipped")
        self._print_import_session(importer)

    def _cmd_import_browser(self, ns: argparse.Namespace):
        from bookmark_organizer_pro.importers import BrowserProfileImporter
        importer = BrowserProfileImporter()

        browsers = [ns.browser] if ns.browser else importer.get_available_browsers()
        if not browsers:
            return self._failure("No browser profiles detected on this system.")

        total_added = 0
        total_dupes = 0
        matched_profiles = 0
        for browser in browsers:
            profiles = importer.get_profiles(browser)
            if not profiles:
                print(f"  {browser}: no profiles found")
                continue
            target_profiles = profiles
            if ns.profile:
                target_profiles = [(n, p) for n, p in profiles if n == ns.profile]
                if not target_profiles:
                    self._error(f"{browser}: profile '{ns.profile}' not found")
                    continue
            for profile_name, profile_path in target_profiles:
                matched_profiles += 1
                if browser == "firefox":
                    bookmarks = importer.import_from_firefox(profile_path)
                else:
                    bookmarks = importer.import_from_chrome(profile_path)
                added = 0
                dupes = 0
                for bm in bookmarks:
                    if self.bookmark_manager.url_exists(bm.url):
                        dupes += 1
                        continue
                    self.bookmark_manager.add_bookmark(bm, save=False)
                    added += 1
                if added:
                    self.bookmark_manager.save_bookmarks()
                total_added += added
                total_dupes += dupes
                print(f"  {browser}/{profile_name}: {added} added, {dupes} duplicates")

        if not matched_profiles:
            return 1
        print(f"Browser import complete: {total_added} added, {total_dupes} duplicates skipped")
        return 0


def main(argv=None) -> int:
    """Console-script and module entry point. Returns the command's exit code.

    Returning (rather than calling sys.exit) keeps main() callable/testable; the
    console_scripts wrapper and the __main__ block below turn it into an exit
    status.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    return BookmarkCLI().run(args) or 0


if __name__ == "__main__":
    sys.exit(main())
