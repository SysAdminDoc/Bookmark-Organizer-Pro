"""Small local HTTP API for bookmark access."""

from __future__ import annotations

import json
import threading
import urllib.parse
from dataclasses import asdict
from typing import TYPE_CHECKING

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.utils import validate_url

if TYPE_CHECKING:
    from bookmark_organizer_pro.managers import BookmarkManager


# =============================================================================
# REST API (Simple Flask-like API using built-in http.server)
# =============================================================================
class BookmarkAPI:
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
    
    def __init__(self, bookmark_manager: BookmarkManager, port: int = 8765):
        self.bookmark_manager = bookmark_manager
        self.port = port
        self._server = None
        self._thread = None
    
    def start(self):
        """Start the API server"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        bookmark_manager = self.bookmark_manager
        
        class APIHandler(BaseHTTPRequestHandler):
            def _send_json(self, data, status=200):
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            
            def _parse_path(self):
                """Parse URL path and query params"""
                parsed = urllib.parse.urlparse(self.path)
                path_parts = parsed.path.strip('/').split('/')
                query_params = urllib.parse.parse_qs(parsed.query)
                return path_parts, query_params
            
            def do_GET(self):
                path_parts, params = self._parse_path()
                
                if not path_parts or path_parts[0] == '':
                    # API info
                    self._send_json({
                        "name": APP_NAME,
                        "version": APP_VERSION,
                        "endpoints": [
                            "GET /bookmarks",
                            "GET /bookmarks/:id",
                            "POST /bookmarks",
                            "DELETE /bookmarks/:id",
                            "GET /categories",
                            "GET /tags",
                            "GET /stats",
                            "GET /search?q=query"
                        ]
                    })
                
                elif path_parts[0] == 'bookmarks':
                    if len(path_parts) > 1:
                        # Get single bookmark
                        try:
                            bm_id = int(path_parts[1])
                            bm = bookmark_manager.get_bookmark(bm_id)
                            if bm:
                                self._send_json(asdict(bm))
                            else:
                                self._send_json({"error": "Not found"}, 404)
                        except Exception:
                            self._send_json({"error": "Invalid ID"}, 400)
                    else:
                        # List bookmarks
                        category = params.get('category', [None])[0]
                        try:
                            limit = max(1, min(500, int(params.get('limit', [100])[0])))
                        except (TypeError, ValueError):
                            limit = 100
                        
                        if category:
                            bookmarks = bookmark_manager.get_bookmarks_by_category(category)
                        else:
                            bookmarks = bookmark_manager.get_all_bookmarks()
                        
                        self._send_json({
                            "count": len(bookmarks),
                            "bookmarks": [asdict(bm) for bm in bookmarks[:limit]]
                        })
                
                elif path_parts[0] == 'categories':
                    counts = bookmark_manager.get_category_counts()
                    self._send_json({
                        "count": len(counts),
                        "categories": [
                            {"name": name, "count": count}
                            for name, count in sorted(counts.items())
                        ]
                    })
                
                elif path_parts[0] == 'tags':
                    counts = bookmark_manager.get_tag_counts()
                    self._send_json({
                        "count": len(counts),
                        "tags": [
                            {"name": name, "count": count}
                            for name, count in sorted(counts.items(), key=lambda x: -x[1])
                        ]
                    })
                
                elif path_parts[0] == 'stats':
                    stats = bookmark_manager.get_statistics()
                    self._send_json(stats)
                
                elif path_parts[0] == 'search':
                    query = params.get('q', [''])[0]
                    if query:
                        results = bookmark_manager.search_bookmarks(query)
                        self._send_json({
                            "query": query,
                            "count": len(results),
                            "results": [asdict(bm) for bm in results[:50]]
                        })
                    else:
                        self._send_json({"error": "Query parameter 'q' required"}, 400)
                
                else:
                    self._send_json({"error": "Not found"}, 404)
            
            def do_POST(self):
                path_parts, _ = self._parse_path()
                
                if path_parts and path_parts[0] == 'bookmarks':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                    except (TypeError, ValueError):
                        self._send_json({"error": "Invalid Content-Length"}, 400)
                        return
                    if content_length <= 0 or content_length > 65_536:
                        self._send_json({"error": "Request body is empty or too large"}, 413)
                        return
                    body = self.rfile.read(content_length)
                    
                    try:
                        data = json.loads(body)
                        if not isinstance(data, dict):
                            self._send_json({"error": "JSON body must be an object"}, 400)
                            return

                        raw_url = str(data.get('url') or '').strip()
                        if not raw_url:
                            self._send_json({"error": "URL required"}, 400)
                            return
                        is_valid_url, error = validate_url(raw_url)
                        if not is_valid_url or not raw_url.startswith(('http://', 'https://')):
                            if not error:
                                error = "URL must start with http:// or https://"
                            self._send_json({"error": error}, 400)
                            return
                        if bookmark_manager.url_exists(raw_url):
                            self._send_json({"error": "Bookmark already exists"}, 409)
                            return

                        tags = data.get('tags', [])
                        if isinstance(tags, str):
                            tags = [t.strip() for t in tags.split(',') if t.strip()]
                        elif not isinstance(tags, list):
                            tags = []
                        
                        bookmark = bookmark_manager.add_bookmark_clean(
                            url=raw_url,
                            title=str(data.get('title') or raw_url).strip()[:500],
                            category=str(data.get('category') or 'Uncategorized / Needs Review').strip(),
                            tags=[str(t).strip() for t in tags if str(t).strip()],
                            notes=str(data.get('notes') or '')[:5000],
                        )
                        if bookmark is None:
                            status = 409 if bookmark_manager.url_exists(raw_url) else 400
                            self._send_json({"error": "Could not add bookmark"}, status)
                            return
                        self._send_json(asdict(bookmark), 201)
                    
                    except json.JSONDecodeError:
                        self._send_json({"error": "Invalid JSON"}, 400)
                    except Exception:
                        self._send_json({"error": "Could not add bookmark"}, 400)
                else:
                    self._send_json({"error": "Not found"}, 404)
            
            def do_DELETE(self):
                path_parts, _ = self._parse_path()
                
                if path_parts and path_parts[0] == 'bookmarks' and len(path_parts) > 1:
                    try:
                        bm_id = int(path_parts[1])
                        if bookmark_manager.delete_bookmark(bm_id):
                            self._send_json({"success": True, "deleted": bm_id})
                        else:
                            self._send_json({"error": "Not found"}, 404)
                    except Exception:
                        self._send_json({"error": "Invalid ID"}, 400)
                else:
                    self._send_json({"error": "Not found"}, 404)
            
            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
            
            def log_message(self, format, *args):
                pass  # Suppress logging
        
        if self._server:
            return

        self._server = HTTPServer(('127.0.0.1', self.port), APIHandler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        
        log.info(f"API server started at http://127.0.0.1:{self.port}")
    
    def stop(self):
        """Stop the API server"""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
