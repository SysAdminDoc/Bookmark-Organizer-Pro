"""Small local HTTP API for bookmark access.

Security: requires Bearer token for all mutating requests (POST/DELETE).
Reads are unauthenticated but CORS-restricted to same-origin.
Token is auto-generated on first start and stored in the data directory.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import urllib.parse
from dataclasses import asdict
from typing import TYPE_CHECKING

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION, DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.feed_export import render_opds
from bookmark_organizer_pro.utils import validate_url

if TYPE_CHECKING:
    from bookmark_organizer_pro.managers import BookmarkManager

_TOKEN_FILE = DATA_DIR / "api_token.txt"
_KEYRING_SERVICE = "bookmark-organizer-pro"
_KEYRING_KEY = "api_token"


def _load_or_create_token() -> str:
    # 1. Try keyring first
    try:
        import keyring
        stored = keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY)
        if stored:
            # Migrate: remove legacy plaintext file if keyring holds the token
            if _TOKEN_FILE.exists():
                _TOKEN_FILE.unlink(missing_ok=True)
                log.info("Migrated API token from plaintext file to OS keyring")
            return stored
    except Exception:
        pass

    # 2. Fall back to legacy file (auto-migrate to keyring if possible)
    if _TOKEN_FILE.exists():
        token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            try:
                import keyring
                keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, token)
                _TOKEN_FILE.unlink(missing_ok=True)
                log.info("Migrated API token from plaintext file to OS keyring")
                return token
            except Exception:
                return token

    # 3. Generate new token — store in keyring, fall back to file
    token = secrets.token_urlsafe(32)
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, token)
        log.info("API token stored in OS keyring")
        return token
    except Exception:
        pass

    _TOKEN_FILE.write_text(token, encoding="utf-8")
    if os.name == "nt":
        import subprocess
        username = os.environ.get("USERNAME", "")
        if username:
            subprocess.run(
                ["icacls", str(_TOKEN_FILE), "/inheritance:r",
                 "/grant:r", f"{username}:(F)"],
                capture_output=True, check=False,
            )
    else:
        os.chmod(_TOKEN_FILE, 0o600)
    log.info(f"API token written to {_TOKEN_FILE} (keyring unavailable)")
    return token


# =============================================================================
# REST API (Simple Flask-like API using built-in http.server)
# =============================================================================
class BookmarkAPI:
    """Local HTTP API server for bookmark CRUD operations."""
    
    def __init__(self, bookmark_manager: BookmarkManager, port: int = 8765):
        self.bookmark_manager = bookmark_manager
        self.port = port
        self._server = None
        self._thread = None
    
    def start(self):
        """Start the API server"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        bookmark_manager = self.bookmark_manager
        api_token = _load_or_create_token()

        class APIHandler(BaseHTTPRequestHandler):
            def _send_json(self, data, status=200):
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', 'null')
                self.end_headers()
                self.wfile.write(body)

            def _send_xml(self, xml: str, status=200):
                body = xml.encode("utf-8")
                self.send_response(status)
                self.send_header(
                    'Content-Type',
                    'application/atom+xml;profile=opds-catalog;kind=acquisition; charset=utf-8',
                )
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', 'null')
                self.end_headers()
                self.wfile.write(body)

            def _check_auth(self) -> bool:
                auth = self.headers.get('Authorization', '')
                if hmac.compare_digest(auth, f'Bearer {api_token}'):
                    return True
                self._send_json({"error": "Unauthorized. Provide Authorization: Bearer <token>"}, 401)
                return False
            
            def _parse_path(self):
                """Parse URL path and query params"""
                parsed = urllib.parse.urlparse(self.path)
                path_parts = parsed.path.strip('/').split('/')
                query_params = urllib.parse.parse_qs(parsed.query)
                return path_parts, query_params
            
            def do_GET(self):
                path_parts, params = self._parse_path()

                if not path_parts or path_parts[0] == '':
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
                            "GET /search?q=query",
                            "GET /opds"
                        ]
                    })
                    return

                if path_parts[0] == 'opds':
                    bookmarks = bookmark_manager.get_all_bookmarks()
                    category = params.get('category', [''])[0]
                    tag = params.get('tag', [''])[0]
                    title = params.get('title', ['Bookmarks'])[0] or "Bookmarks"
                    try:
                        limit = max(1, min(1000, int(params.get('limit', [200])[0])))
                    except (TypeError, ValueError):
                        limit = 200
                    if category:
                        bookmarks = [bm for bm in bookmarks if bm.category == category]
                    if tag:
                        tag_l = tag.lower()
                        bookmarks = [bm for bm in bookmarks if any(t.lower() == tag_l for t in bm.tags)]
                    catalog_url = f"http://127.0.0.1:{self.server.server_port}{self.path}"
                    self._send_xml(render_opds(bookmarks[:limit], title=title, catalog_url=catalog_url))
                    return

                if not self._check_auth():
                    return

                if path_parts[0] == 'bookmarks':
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
                if not self._check_auth():
                    return
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
                if not self._check_auth():
                    return
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
