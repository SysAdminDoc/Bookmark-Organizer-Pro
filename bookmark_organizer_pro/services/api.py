"""Small local HTTP API for bookmark access.

Security: requires a Bearer token for bookmark data reads and all mutating
requests. The root metadata endpoint remains public.
Token is auto-generated on first start and stored in the data directory.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import urllib.parse
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION, DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.feed_export import render_opds, render_opds2
from bookmark_organizer_pro.utils import validate_url

if TYPE_CHECKING:
    from bookmark_organizer_pro.managers import BookmarkManager

_TOKEN_FILE = DATA_DIR / "api_token.txt"
_EXTENSION_ORIGINS_FILE = DATA_DIR / "approved_extension_origins.json"
_KEYRING_SERVICE = "bookmark-organizer-pro"
_KEYRING_KEY = "api_token"
_MAX_BOOKMARK_BODY_BYTES = 65_536
_MAX_BROWSER_SNAPSHOT_BODY_BYTES = 5_500_000
_EXTENSION_ORIGIN_RE = re.compile(
    r"^(?:chrome-extension://[a-p]{32}|moz-extension://[0-9a-f-]{8,64})$",
    re.IGNORECASE,
)


def _write_private_file(path: Path, payload: bytes) -> None:
    """Atomically write a local credential-adjacent file with owner-only access."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if os.name == "nt":
            import subprocess

            username = os.environ.get("USERNAME", "")
            if username:
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:(F)"],
                    capture_output=True,
                    check=False,
                )
    finally:
        temporary.unlink(missing_ok=True)


class ExtensionOriginRegistry:
    """Persist the single browser-extension identity trusted by the local API."""

    VERSION = 1

    def __init__(self, path: Path = _EXTENSION_ORIGINS_FILE):
        self.path = Path(path)
        self.backup_path = self.path.with_suffix(f"{self.path.suffix}.bak")
        self._lock = threading.RLock()
        self._origins: set[str] = set()
        self._integrity_error = ""
        self._load()

    @staticmethod
    def _normalize(origin: str) -> str:
        value = str(origin or "").strip().lower()
        return value if _EXTENSION_ORIGIN_RE.fullmatch(value) else ""

    @classmethod
    def _decode(cls, payload: bytes) -> set[str]:
        document = json.loads(payload.decode("utf-8"))
        if not isinstance(document, dict) or document.get("version") != cls.VERSION:
            raise ValueError("Unsupported extension-origin registry")
        raw_origins = document.get("origins")
        if not isinstance(raw_origins, list) or len(raw_origins) > 8:
            raise ValueError("Invalid extension-origin registry")
        origins = {cls._normalize(item) for item in raw_origins}
        if "" in origins or len(origins) != len(raw_origins):
            raise ValueError("Invalid extension-origin registry")
        return origins

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._origins = self._decode(self.path.read_bytes())
            return
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            self._integrity_error = str(exc) or "Extension-origin registry is unreadable"
        try:
            self._origins = self._decode(self.backup_path.read_bytes())
            self._integrity_error = ""
            log.warning("Recovered approved extension origins from the verified backup")
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            self._origins = set()
            log.error("Approved extension-origin registry is corrupt; browser access is locked")

    def _save(self, origins: set[str]) -> None:
        payload = json.dumps(
            {"version": self.VERSION, "origins": sorted(origins)},
            ensure_ascii=True,
            indent=2,
        ).encode("utf-8") + b"\n"
        if self.path.exists():
            _write_private_file(self.backup_path, self.path.read_bytes())
        _write_private_file(self.path, payload)
        if self._decode(self.path.read_bytes()) != origins:
            raise OSError("Approved extension-origin registry verification failed")

    def is_approved(self, origin: str) -> bool:
        normalized = self._normalize(origin)
        with self._lock:
            return bool(normalized and normalized in self._origins and not self._integrity_error)

    def status(self, origin: str) -> dict[str, object]:
        normalized = self._normalize(origin)
        with self._lock:
            return {
                "paired": bool(normalized and normalized in self._origins and not self._integrity_error),
                "pairing_count": len(self._origins),
                "recovery_required": bool(self._integrity_error),
            }

    def pair(self, origin: str, *, replace: bool = False) -> bool:
        normalized = self._normalize(origin)
        if not normalized:
            raise ValueError("Pairing requires a valid browser extension Origin")
        with self._lock:
            if self._integrity_error and not replace:
                raise RuntimeError("Pairing registry recovery requires explicit replacement")
            if normalized in self._origins and not self._integrity_error:
                return False
            if self._origins and not replace:
                raise FileExistsError("The API is already paired with another extension identity")
            origins = {normalized}
            self._save(origins)
            self._origins = origins
            self._integrity_error = ""
            return True

    def clear(self) -> bool:
        with self._lock:
            if not self._origins and not self._integrity_error:
                return False
            self._save(set())
            self._origins = set()
            self._integrity_error = ""
            return True


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _clamp_int(value, default: int, *, minimum: int = 0, maximum: int = 100_000) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


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
    
    def __init__(
        self,
        bookmark_manager: BookmarkManager,
        port: int = 8765,
        *,
        extension_origins_file: Path | None = None,
    ):
        self.bookmark_manager = bookmark_manager
        self.port = port
        self._server = None
        self._thread = None
        self.extension_origins = ExtensionOriginRegistry(
            extension_origins_file or _EXTENSION_ORIGINS_FILE
        )
    
    def start(self):
        """Start the API server"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        bookmark_manager = self.bookmark_manager
        api_token = _load_or_create_token()
        extension_origins = self.extension_origins

        class APIHandler(BaseHTTPRequestHandler):
            def _is_pairing_path(self) -> bool:
                return urllib.parse.urlparse(self.path).path.rstrip('/') == '/extension/pair'

            def _cors_origin(self) -> str:
                origin = self.headers.get('Origin', '').strip()
                if not _EXTENSION_ORIGIN_RE.fullmatch(origin):
                    return 'null'
                if self._is_pairing_path() or extension_origins.is_approved(origin):
                    return origin
                return 'null'

            def _send_json(self, data, status=200):
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                self.send_header('Vary', 'Origin')
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

            def _check_auth(self, *, discard_body: bool = False) -> bool:
                auth = self.headers.get('Authorization', '')
                if hmac.compare_digest(auth, f'Bearer {api_token}'):
                    return True
                if discard_body:
                    self._discard_request_body()
                self._send_json({"error": "Unauthorized. Provide Authorization: Bearer <token>"}, 401)
                return False

            def _check_browser_origin(self, *, discard_body: bool = False) -> bool:
                origin = self.headers.get('Origin', '').strip()
                if not origin:
                    return True
                if extension_origins.is_approved(origin):
                    return True
                if discard_body:
                    self._discard_request_body()
                self._send_json({"error": "Browser extension Origin is not paired with this API"}, 403)
                return False

            def _discard_request_body(self) -> None:
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                except (TypeError, ValueError):
                    return
                if content_length <= 0:
                    return
                self.rfile.read(min(content_length, 65_536))
            
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
                            "GET /digest",
                            "GET /opds",
                            "GET /opds2",
                            "GET|POST|DELETE /extension/pair"
                        ]
                    })
                    return

                if not self._check_auth():
                    return

                if path_parts[0] == 'extension' and len(path_parts) > 1 and path_parts[1] == 'pair':
                    origin = self.headers.get('Origin', '').strip()
                    if not _EXTENSION_ORIGIN_RE.fullmatch(origin):
                        self._send_json({"error": "Pairing requires a valid browser extension Origin"}, 403)
                        return
                    self._send_json(extension_origins.status(origin))
                    return

                if not self._check_browser_origin():
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

                if path_parts[0] == 'opds2':
                    bookmarks = bookmark_manager.get_all_bookmarks()
                    tag = params.get('tag', [''])[0]
                    title = params.get('title', ['Bookmarks'])[0] or "Bookmarks"
                    try:
                        limit = max(1, min(1000, int(params.get('limit', [200])[0])))
                    except (TypeError, ValueError):
                        limit = 200
                    if tag:
                        tag_l = tag.lower()
                        bookmarks = [bm for bm in bookmarks if any(t.lower() == tag_l for t in bm.tags)]
                    catalog_url = f"http://127.0.0.1:{self.server.server_port}{self.path}"
                    body = render_opds2(bookmarks[:limit], title=title, catalog_url=catalog_url)
                    self._send_json(json.loads(body))
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
                        tag = params.get('tag', [None])[0]
                        limit = _clamp_int(params.get('limit', [100])[0], 100, minimum=1, maximum=500)
                        offset = _clamp_int(params.get('offset', [0])[0], 0, minimum=0, maximum=100_000)
                        read_later_only = _coerce_bool(params.get('read_later_only', [False])[0])
                        pinned_only = _coerce_bool(params.get('pinned_only', [False])[0])

                        if category:
                            bookmarks = [
                                bm for bm in bookmark_manager.get_all_bookmarks()
                                if bm.category == category or bm.parent_category == category
                            ]
                        else:
                            bookmarks = bookmark_manager.get_all_bookmarks()
                        if tag:
                            tag_l = tag.lower()
                            bookmarks = [bm for bm in bookmarks if any(t.lower() == tag_l for t in bm.tags)]
                        if read_later_only:
                            bookmarks = [bm for bm in bookmarks if bm.read_later]
                        if pinned_only:
                            bookmarks = [bm for bm in bookmarks if bm.is_pinned]
                        bookmarks.sort(key=lambda bm: (bm.created_at, bm.id or 0), reverse=True)
                        page = bookmarks[offset: offset + limit]
                        next_offset = offset + len(page)

                        self._send_json({
                            "count": len(bookmarks),
                            "returned": len(page),
                            "next_offset": next_offset if next_offset < len(bookmarks) else None,
                            "has_more": next_offset < len(bookmarks),
                            "bookmarks": [asdict(bm) for bm in page]
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
                
                elif path_parts[0] == 'digest':
                    from bookmark_organizer_pro.services.digest import DailyDigestService
                    svc = DailyDigestService()
                    all_bm = bookmark_manager.get_all_bookmarks()
                    try:
                        count = max(1, min(20, int(params.get('count', [5])[0])))
                    except (TypeError, ValueError):
                        count = 5
                    digest = svc.build(all_bm, rediscover_count=count, read_later_count=count)
                    self._send_json({
                        "generated_at": digest.generated_at,
                        "sections": [
                            {
                                "title": sec.title,
                                "description": sec.description,
                                "bookmarks": [asdict(bm) for bm in sec.bookmarks],
                            }
                            for sec in digest.sections
                        ],
                    })

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
                if not self._check_auth(discard_body=True):
                    return
                path_parts, _ = self._parse_path()

                if path_parts[:2] == ['extension', 'pair']:
                    origin = self.headers.get('Origin', '').strip()
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                    except (TypeError, ValueError):
                        self._send_json({"error": "Invalid Content-Length"}, 400)
                        return
                    if content_length <= 0 or content_length > 4096:
                        self._send_json({"error": "Pairing request body is empty or too large"}, 413)
                        return
                    try:
                        data = json.loads(self.rfile.read(content_length))
                        if not isinstance(data, dict):
                            raise ValueError("Pairing request must be a JSON object")
                        changed = extension_origins.pair(
                            origin,
                            replace=_coerce_bool(data.get('replace')),
                        )
                    except json.JSONDecodeError:
                        self._send_json({"error": "Invalid JSON"}, 400)
                        return
                    except FileExistsError as exc:
                        self._send_json({"error": str(exc), "replace_required": True}, 409)
                        return
                    except (ValueError, RuntimeError, OSError) as exc:
                        self._send_json({"error": str(exc)}, 422)
                        return
                    self._send_json({**extension_origins.status(origin), "changed": changed})
                    return

                if not self._check_browser_origin(discard_body=True):
                    return

                if path_parts and path_parts[0] == 'bookmarks':
                    try:
                        content_length = int(self.headers.get('Content-Length', 0))
                    except (TypeError, ValueError):
                        self._send_json({"error": "Invalid Content-Length"}, 400)
                        return
                    if content_length <= 0 or content_length > _MAX_BROWSER_SNAPSHOT_BODY_BYTES:
                        self._send_json({"error": "Request body is empty or too large"}, 413)
                        return
                    body = self.rfile.read(content_length)
                    
                    try:
                        data = json.loads(body)
                        if not isinstance(data, dict):
                            self._send_json({"error": "JSON body must be an object"}, 400)
                            return

                        capture = data.get('browser_snapshot')
                        if capture is not None:
                            if not isinstance(capture, dict):
                                self._send_json({"error": "browser_snapshot must be an object"}, 400)
                                return
                            if self.headers.get('X-BOP-Capture-Version') != '1':
                                self._send_json({"error": "Unsupported browser snapshot contract"}, 400)
                                return
                            origin = self.headers.get('Origin', '').strip()
                            if not extension_origins.is_approved(origin):
                                self._send_json({"error": "Browser snapshots require a paired extension Origin"}, 403)
                                return
                        elif content_length > _MAX_BOOKMARK_BODY_BYTES:
                            self._send_json({"error": "Request body is too large"}, 413)
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
                        if capture is not None and str(capture.get('source_url') or '') != raw_url:
                            self._send_json({"error": "Snapshot source URL does not match the request URL"}, 400)
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
                            read_later=_coerce_bool(data.get('read_later', False)),
                        )
                        if bookmark is None:
                            status = 409 if bookmark_manager.url_exists(raw_url) else 400
                            self._send_json({"error": "Could not add bookmark"}, status)
                            return
                        response = asdict(bookmark)
                        if capture is not None:
                            from pathlib import Path

                            from bookmark_organizer_pro.services.snapshot import SnapshotArchiver

                            try:
                                snapshots_dir = Path(bookmark_manager.filepath).parent / "snapshots"
                                report = SnapshotArchiver(snapshots_dir=snapshots_dir).import_browser_snapshot(
                                    bookmark,
                                    str(capture.get('html') or ''),
                                    source_url=str(capture.get('source_url') or ''),
                                    selection=str(capture.get('selection') or '')[:500],
                                    resource_summary=capture.get('resources'),
                                )
                                bookmark_manager.save_bookmarks()
                            except (ValueError, RuntimeError, OSError) as exc:
                                snapshot_path = getattr(bookmark, 'snapshot_path', '')
                                if snapshot_path:
                                    Path(snapshot_path).unlink(missing_ok=True)
                                bookmark_manager.delete_bookmark(bookmark.id)
                                message = (
                                    str(exc)
                                    if isinstance(exc, ValueError)
                                    else "Browser snapshot could not be stored"
                                )
                                self._send_json({"error": message}, 422)
                                return
                            response = asdict(bookmark)
                            response['browser_snapshot'] = report
                        self._send_json(response, 201)
                    
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

                if path_parts[:2] == ['extension', 'pair']:
                    if not self._check_browser_origin():
                        return
                    changed = extension_origins.clear()
                    self._send_json({"paired": False, "pairing_count": 0, "changed": changed})
                    return

                if not self._check_browser_origin():
                    return
                
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
                origin = self.headers.get('Origin', '').strip()
                pairing = self._is_pairing_path()
                approved = extension_origins.is_approved(origin)
                if origin and not ((pairing and _EXTENSION_ORIGIN_RE.fullmatch(origin)) or approved):
                    self.send_response(403)
                    self.send_header('Access-Control-Allow-Origin', 'null')
                    self.send_header('Vary', 'Origin')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    return
                self.send_response(204)
                self.send_header('Access-Control-Allow-Origin', self._cors_origin())
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
                self.send_header(
                    'Access-Control-Allow-Headers',
                    'Authorization, Content-Type, X-BOP-Capture-Version',
                )
                self.send_header('Access-Control-Max-Age', '86400')
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
