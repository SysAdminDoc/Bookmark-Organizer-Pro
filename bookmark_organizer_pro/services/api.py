"""Small local HTTP API for bookmark access.

Security: requires a Bearer token for bookmark data reads and all mutating
requests. The root metadata endpoint remains public.
Token is auto-generated on first start and stored in the data directory.
"""

from __future__ import annotations

import hmac
import json
import re
import secrets
import socket
import socketserver
import threading
import time
import urllib.parse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION, DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.services.feed_export import render_opds, render_opds2
from bookmark_organizer_pro.services.private_files import (
    atomic_write_private_bytes,
    atomic_write_private_text,
    restrict_private_file,
)
from bookmark_organizer_pro.utils import validate_url

if TYPE_CHECKING:
    from bookmark_organizer_pro.managers import BookmarkManager

_TOKEN_FILE = DATA_DIR / "api_token.txt"
_EXTENSION_ORIGINS_FILE = DATA_DIR / "approved_extension_origins.json"
_KEYRING_SERVICE = "bookmark-organizer-pro"
_KEYRING_KEY = "api_token"
_MAX_BOOKMARK_BODY_BYTES = 65_536
_MAX_BROWSER_SNAPSHOT_BODY_BYTES = 5_500_000
_DEFAULT_API_WORKERS = 8
_DEFAULT_HEADER_DEADLINE_SECONDS = 5.0
_DEFAULT_REQUEST_DEADLINE_SECONDS = 30.0
_DEFAULT_IO_TIMEOUT_SECONDS = 5.0
_EXTENSION_ORIGIN_RE = re.compile(
    r"^(?:chrome-extension://[a-p]{32}|moz-extension://[0-9a-f-]{8,64})$",
    re.IGNORECASE,
)


def _write_private_file(path: Path, payload: bytes) -> None:
    """Atomically write a local credential-adjacent file with owner-only access."""
    atomic_write_private_bytes(path, payload)


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
        restrict_private_file(_TOKEN_FILE)
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

    atomic_write_private_text(_TOKEN_FILE, token)
    log.info(f"API token written to {_TOKEN_FILE} (keyring unavailable)")
    return token


class _BoundedThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Thread-per-request HTTP server with a hard admission ceiling."""

    daemon_threads = True
    block_on_close = False
    request_queue_size = 32

    def __init__(self, server_address, handler_class, *, max_workers: int):
        self.max_workers = max(1, int(max_workers))
        self._worker_slots = threading.BoundedSemaphore(self.max_workers)
        super().__init__(server_address, handler_class)

    def process_request(self, request, client_address):
        if not self._worker_slots.acquire(blocking=False):
            self._reject_busy(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()

    @property
    def at_capacity(self) -> bool:
        """Return whether a new request would be rejected at this instant."""
        acquired = self._worker_slots.acquire(blocking=False)
        if acquired:
            self._worker_slots.release()
            return False
        return True

    def _reject_busy(self, request) -> None:
        body = b'{"error":"Local API is busy; retry shortly"}'
        response = (
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            b"X-Content-Type-Options: nosniff\r\n"
            b"Connection: close\r\n"
            b"Retry-After: 1\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        try:
            # Winsock can reset a connection closed with unread request bytes,
            # discarding the already-sent 503 before urllib receives it. Drain
            # the bounded request headers (and any small body already in the
            # socket) before replying so overload is a deterministic HTTP
            # response rather than a platform-dependent connection abort.
            request.settimeout(0.01)
            received = bytearray()
            deadline = time.monotonic() + 0.05
            expected = None
            while len(received) < 65_536 and time.monotonic() < deadline:
                try:
                    chunk = request.recv(min(4096, 65_536 - len(received)))
                except (socket.timeout, BlockingIOError):
                    continue
                if not chunk:
                    break
                received.extend(chunk)
                header_end = received.find(b"\r\n\r\n")
                if header_end >= 0 and expected is None:
                    header_bytes = bytes(received[:header_end]).lower()
                    content_length = 0
                    for line in header_bytes.split(b"\r\n"):
                        if line.startswith(b"content-length:"):
                            try:
                                content_length = max(0, int(line.split(b":", 1)[1].strip()))
                            except ValueError:
                                content_length = 0
                            break
                    expected = min(65_536, header_end + 4 + content_length)
                if expected is not None and len(received) >= expected:
                    break
            request.settimeout(0.25)
            request.sendall(response)
            try:
                request.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        except OSError:
            pass
        finally:
            self.shutdown_request(request)

    def handle_error(self, request, client_address) -> None:
        _ = request, client_address
        log.debug("Local API client disconnected before the request completed")


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
        max_workers: int = _DEFAULT_API_WORKERS,
        header_deadline_seconds: float = _DEFAULT_HEADER_DEADLINE_SECONDS,
        request_deadline_seconds: float = _DEFAULT_REQUEST_DEADLINE_SECONDS,
        io_timeout_seconds: float = _DEFAULT_IO_TIMEOUT_SECONDS,
    ):
        self.bookmark_manager = bookmark_manager
        self.port = port
        self._server = None
        self._thread = None
        self.max_workers = max(1, int(max_workers))
        self.header_deadline_seconds = max(0.1, float(header_deadline_seconds))
        self.request_deadline_seconds = max(0.1, float(request_deadline_seconds))
        self.io_timeout_seconds = max(0.1, float(io_timeout_seconds))
        self.extension_origins = ExtensionOriginRegistry(
            extension_origins_file or _EXTENSION_ORIGINS_FILE
        )
    
    def start(self):
        """Start the API server"""
        bookmark_manager = self.bookmark_manager
        api_token = _load_or_create_token()
        extension_origins = self.extension_origins
        header_deadline_seconds = self.header_deadline_seconds
        request_deadline_seconds = self.request_deadline_seconds
        io_timeout_seconds = self.io_timeout_seconds

        class APIHandler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self._deadline_lock = threading.Lock()
                self._deadline_generation = 0
                self._deadline_timer: threading.Timer | None = None
                self._request_deadline = time.monotonic() + header_deadline_seconds
                self.connection.settimeout(io_timeout_seconds)
                self._arm_deadline(header_deadline_seconds)

            def finish(self) -> None:
                self._cancel_deadline()
                try:
                    super().finish()
                except OSError:
                    pass

            def parse_request(self) -> bool:
                parsed = super().parse_request()
                if parsed:
                    self._request_deadline = time.monotonic() + request_deadline_seconds
                    self._arm_deadline(request_deadline_seconds)
                return parsed

            def _arm_deadline(self, seconds: float) -> None:
                with self._deadline_lock:
                    self._deadline_generation += 1
                    generation = self._deadline_generation
                    previous = self._deadline_timer
                    timer = threading.Timer(seconds, self._expire_deadline, args=(generation,))
                    timer.daemon = True
                    self._deadline_timer = timer
                if previous is not None:
                    previous.cancel()
                timer.start()

            def _cancel_deadline(self) -> None:
                with self._deadline_lock:
                    self._deadline_generation += 1
                    timer = self._deadline_timer
                    self._deadline_timer = None
                if timer is not None:
                    timer.cancel()

            def _expire_deadline(self, generation: int) -> None:
                with self._deadline_lock:
                    if generation != self._deadline_generation:
                        return
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            def _read_request_body(self, maximum: int, *, label: str) -> bytes | None:
                if self.headers.get("Transfer-Encoding"):
                    self._send_json({"error": "Transfer-Encoding is not supported"}, 400)
                    return None
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                except (TypeError, ValueError):
                    self._send_json({"error": "Invalid Content-Length"}, 400)
                    return None
                if content_length <= 0 or content_length > maximum:
                    self.close_connection = True
                    self._send_json({"error": f"{label} is empty or too large"}, 413)
                    return None

                body = bytearray()
                remaining = content_length
                try:
                    while remaining:
                        deadline_remaining = self._request_deadline - time.monotonic()
                        if deadline_remaining <= 0:
                            raise TimeoutError
                        self.connection.settimeout(min(io_timeout_seconds, deadline_remaining))
                        chunk = self.rfile.read(min(remaining, 65_536))
                        if not chunk:
                            self.close_connection = True
                            self._send_json({"error": "Request body ended before Content-Length"}, 400)
                            return None
                        body.extend(chunk)
                        remaining -= len(chunk)
                except (socket.timeout, TimeoutError):
                    self.close_connection = True
                    try:
                        self._send_json({"error": "Request body deadline exceeded"}, 408)
                    except OSError:
                        pass
                    return None
                finally:
                    try:
                        self.connection.settimeout(io_timeout_seconds)
                    except OSError:
                        pass
                return bytes(body)

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
                try:
                    self.wfile.write(body)
                except OSError:
                    self.close_connection = True

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
                try:
                    self.wfile.write(body)
                except OSError:
                    self.close_connection = True

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
                            "GET /imports",
                            "GET /imports/:id",
                            "POST /imports/:id/retry|cancel|rollback",
                            "GET /opds",
                            "GET /opds2",
                            "GET|POST|DELETE /extension/pair"
                        ]
                    })
                    return

                if path_parts[0] == 'health':
                    self._send_json({"status": "ok", "version": APP_VERSION})
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

                if path_parts[0] == 'imports':
                    from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

                    sessions = ImportSessionManager()
                    if len(path_parts) == 1:
                        limit = _clamp_int(params.get('limit', [50])[0], 50, minimum=1, maximum=200)
                        reports = [report.to_dict() for report in sessions.list(limit)]
                        self._send_json({"count": len(reports), "sessions": reports})
                        return
                    session = sessions.get(path_parts[1])
                    report = sessions.report(path_parts[1])
                    if not session or not report:
                        self._send_json({"error": "Import session not found or prefix is ambiguous"}, 404)
                        return
                    self._send_json({
                        **report.to_dict(),
                        "rows": [
                            {
                                "index": row.get("index"),
                                "key": row.get("key"),
                                "state": row.get("state"),
                                "cause": row.get("cause", ""),
                            }
                            for row in session.get("rows", [])
                        ],
                    })
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
                    body = self._read_request_body(4096, label="Pairing request body")
                    if body is None:
                        return
                    try:
                        data = json.loads(body)
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

                if path_parts and path_parts[0] == 'imports' and len(path_parts) == 3:
                    from bookmark_organizer_pro.services.import_sessions import ImportSessionManager

                    sessions = ImportSessionManager()
                    session_id, action = path_parts[1], path_parts[2]
                    try:
                        if action == 'retry':
                            report = sessions.retry(bookmark_manager, session_id)
                        elif action == 'cancel':
                            if not sessions.request_cancel(session_id):
                                self._send_json({"error": "Import session not found"}, 404)
                                return
                            report = sessions.report(session_id)
                        elif action == 'rollback':
                            report = sessions.rollback(bookmark_manager, session_id)
                        else:
                            self._send_json({"error": "Unsupported import session action"}, 404)
                            return
                    except RuntimeError as exc:
                        self._send_json({"error": str(exc)}, 409)
                        return
                    self._send_json(report.to_dict() if report else {"error": "Import session not found"},
                                    200 if report else 404)
                    return

                if path_parts and path_parts[0] == 'bookmarks':
                    body = self._read_request_body(
                        _MAX_BROWSER_SNAPSHOT_BODY_BYTES,
                        label="Request body",
                    )
                    if body is None:
                        return
                    content_length = len(body)
                    
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

        self._server = _BoundedThreadingHTTPServer(
            ('127.0.0.1', self.port),
            APIHandler,
            max_workers=self.max_workers,
        )
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
