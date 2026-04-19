"""Favicon download, cache, and wrapper-page services."""

from __future__ import annotations

import base64
import html as html_module
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

from bookmark_organizer_pro.constants import APP_DIR, DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.url_utils import URLUtilities
from bookmark_organizer_pro.utils import sanitize_filename
from bookmark_organizer_pro.utils.runtime import atomic_json_write as _atomic_json_write

try:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 20_000_000
except Exception as exc:
    Image = None
    log.debug(f"Pillow unavailable for favicon normalization: {exc}")


class HighSpeedFaviconManager:
    """
    Ultra-fast favicon manager with:
    - Concurrent downloads (multiple at once)
    - Completely non-blocking
    - Memory efficient
    - Lazy loading from web until cached
    - Persistent failed domain tracking
    """
    
    CACHE_DIR = DATA_DIR / "favicons"
    FAILED_FILE = DATA_DIR / "failed_favicons.json"
    
    # Fast favicon sources (ordered by speed/reliability)
    FAVICON_SOURCES = [
        "https://www.google.com/s2/favicons?domain={domain}&sz=32",
        "https://icons.duckduckgo.com/ip3/{domain}.ico",
        "https://api.faviconkit.com/{domain}/64",
        "https://favicone.com/{domain}?s=64",
        "https://icon.horse/icon/{domain}",
        "https://{domain}/favicon.ico",
        "https://{domain}/favicon.png",
    ]
    
    def __init__(self, max_workers: int = 10):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Optional[str]] = {}
        self._pending: Set[str] = set()
        try:
            max_workers = max(1, min(32, int(max_workers)))
        except (TypeError, ValueError):
            max_workers = 10
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: Dict[str, Any] = {}
        self._progress_callback: Optional[Callable] = None
        self._on_favicon_ready: Optional[Callable] = None
        self._callbacks: Dict[str, List[Callable]] = {}
        self._total_queued = 0
        self._completed = 0
        self._lock = threading.Lock()
        self._failed_domains: Set[str] = set()
        
        self._max_cache_mb = 500  # Evict oldest when exceeded

        # Load existing cache and failed domains
        self._load_cache_index()
        self._load_failed_domains()
        self._evict_if_needed()

    def _load_cache_index(self):
        """Load index of cached favicons"""
        for filepath in self.CACHE_DIR.glob("*.*"):
            if not filepath.is_file() or filepath.suffix.lower() not in ['.png', '.ico', '.jpg', '.jpeg']:
                continue
            domain = self._normalize_domain(filepath.stem)
            if domain:
                self._cache[domain] = str(filepath)

    def _evict_if_needed(self):
        """Evict oldest cached favicons if disk usage exceeds limit."""
        try:
            file_stats = []
            total_bytes = 0
            for file in self.CACHE_DIR.glob("*.*"):
                if not file.is_file():
                    continue
                try:
                    stat = file.stat()
                except OSError:
                    continue
                file_stats.append((file, stat.st_size, stat.st_mtime))
                total_bytes += stat.st_size
            if total_bytes <= self._max_cache_mb * 1024 * 1024:
                return
            # Sort by modification time, oldest first
            file_stats.sort(key=lambda item: item[2])
            target = int(self._max_cache_mb * 1024 * 1024 * 0.8)
            while total_bytes > target and file_stats:
                f, size, _ = file_stats.pop(0)
                total_bytes -= size
                self._cache.pop(f.stem, None)
                f.unlink(missing_ok=True)
            log.info(f"Favicon cache evicted to {total_bytes // (1024*1024)}MB")
        except Exception as e:
            log.warning(f"Favicon cache eviction failed: {e}")
    
    def _load_failed_domains(self):
        """Load failed domains from file"""
        try:
            if self.FAILED_FILE.exists():
                with open(self.FAILED_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        data = {"failed_domains": data if isinstance(data, list) else []}
                    self._failed_domains = {
                        d for d in (self._normalize_domain(x) for x in data.get('failed_domains', []))
                        if d
                    }
                    log.debug(f"Loaded {len(self._failed_domains)} failed favicon domains")
        except Exception as e:
            log.warning(f"Error loading failed domains: {e}")
    
    def _save_failed_domains(self):
        """Save failed domains to file"""
        try:
            _atomic_json_write(
                self.FAILED_FILE,
                {'failed_domains': sorted(self._failed_domains)}
            )
        except Exception as e:
            log.warning(f"Error saving failed domains: {e}")
    
    def get_failed_domains(self) -> Set[str]:
        """Get set of failed domains"""
        return self._failed_domains.copy()
    
    def clear_failed_domains(self):
        """Clear failed domains to allow retry"""
        self._failed_domains.clear()
        self._save_failed_domains()
    
    def get_cached_path(self, url: str) -> Optional[str]:
        """Get cached favicon path for a URL"""
        try:
            domain = self._normalize_domain(urlparse(url).netloc)
            return self.get_cached(domain)
        except Exception:
            return None

    def _normalize_domain(self, domain: str) -> str:
        """Normalize a user/bookmark domain for cache keys and requests."""
        raw = (domain or "").strip().lower()
        if not raw:
            return ""
        parsed = urlparse(raw if "://" in raw else f"//{raw}")
        hostname = (parsed.hostname or raw).strip(".").lower()
        if not hostname or len(hostname) > 253:
            return ""
        if not re.match(r"^[a-z0-9.-]+$", hostname):
            return ""
        return hostname
    
    def get_cached(self, domain: str) -> Optional[str]:
        """Get cached favicon path (instant, non-blocking). Returns None for failed domains."""
        domain = self._normalize_domain(domain)
        if not domain:
            return None
        cached = self._cache.get(domain)
        if cached == "FAILED":
            return None  # Don't return the placeholder marker
        return cached

    def fetch_favicon(self, url: str, callback: Callable = None):
        """Compatibility wrapper for older card widgets.

        callback receives (domain, filepath) when a favicon is available.
        """
        domain = self._normalize_domain(urlparse(url).netloc)
        if not domain:
            return
        cached = self.get_cached(domain)
        if cached:
            if callback:
                callback(domain, cached)
            return
        if callback:
            with self._lock:
                self._callbacks.setdefault(domain, []).append(callback)
        self.download_async(domain)
    
    def is_cached(self, domain: str) -> bool:
        """Check if favicon is cached"""
        domain = self._normalize_domain(domain)
        return domain in self._cache
    
    def download_async(self, domain: str, bookmark_id: int = 0):
        """
        Download favicon asynchronously.
        Returns immediately, calls callback when ready.
        """
        domain = self._normalize_domain(domain)
        if not domain:
            return

        # Skip if already cached or pending
        with self._lock:
            if domain in self._pending:
                cached = None
                should_notify = False
                should_submit = False
            elif domain in self._cache:
                # Already cached - notify immediately
                cached = self._cache.get(domain)
                should_notify = bool(cached and cached != "FAILED" and self._on_favicon_ready)
                should_submit = False
            else:
                cached = None
                should_notify = False
                should_submit = True
                self._pending.add(domain)
                self._total_queued += 1

        if should_notify:
            self._on_favicon_ready(domain, cached, bookmark_id)
            return
        if not should_submit:
            return
        
        # Submit to thread pool
        future = self._executor.submit(self._download_favicon, domain, bookmark_id)
        with self._lock:
            self._futures[domain] = future
        future.add_done_callback(lambda _future, favicon_domain=domain: self._forget_future(favicon_domain))

    def _forget_future(self, domain: str):
        """Drop completed future bookkeeping without touching cache state."""
        with self._lock:
            self._futures.pop(domain, None)
    
    def _download_favicon(self, domain: str, bookmark_id: int) -> Optional[str]:
        """Download favicon (runs in thread pool) with multiple fallback sources"""
        filepath = None
        if not URLUtilities._is_safe_url(f"https://{domain}"):
            with self._lock:
                self._pending.discard(domain)
                self._completed += 1
                self._cache[domain] = "FAILED"
                self._failed_domains.add(domain)
                self._save_failed_domains()
                completed = self._completed
                total = self._total_queued
            if self._progress_callback:
                try:
                    self._progress_callback(completed, total, domain)
                except Exception:
                    pass
            return None
        
        for source_template in self.FAVICON_SOURCES:
            try:
                url = source_template.format(domain=domain)
                if not URLUtilities._is_safe_url(url):
                    continue
                
                response = requests.get(
                    url,
                    timeout=5,  # Slightly longer timeout for reliability
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                    allow_redirects=False,
                    stream=True
                )
                
                content = bytearray()
                try:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        content.extend(chunk)
                        if len(content) > 1_000_000:
                            break
                finally:
                    response.close()

                if response.status_code == 200 and 100 < len(content) <= 1_000_000:
                    # Try to open as image to validate
                    try:
                        img_data = BytesIO(bytes(content))
                        img = Image.open(img_data)
                        
                        # Convert and save as PNG
                        if img.mode != 'RGBA':
                            img = img.convert('RGBA')
                        
                        # Resize if needed
                        if img.size[0] != 32 or img.size[1] != 32:
                            img = img.resize((32, 32), Image.Resampling.LANCZOS)
                        
                        safe_domain = sanitize_filename(domain)
                        filepath = self.CACHE_DIR / f"{safe_domain}.png"
                        img.save(filepath, "PNG")
                        filepath = str(filepath)
                        break
                    except Exception as img_error:
                        # If can't open as image, save raw content
                        content_type = response.headers.get('content-type', '')
                        if not content_type.lower().startswith('image/'):
                            continue
                        ext = 'png' if 'png' in content_type else 'ico'
                        
                        safe_domain = sanitize_filename(domain)
                        filepath = self.CACHE_DIR / f"{safe_domain}.{ext}"
                        with open(filepath, 'wb') as f:
                            f.write(content)
                        filepath = str(filepath)
                        break
            except Exception as e:
                continue
        
        # Update state
        with self._lock:
            self._pending.discard(domain)
            self._completed += 1
            
            if filepath:
                self._cache[domain] = filepath
                # Remove from failed if it was there
                self._failed_domains.discard(domain)
            else:
                # Mark as failed and persist
                self._cache[domain] = "FAILED"
                self._failed_domains.add(domain)
                self._save_failed_domains()
        
        # Notify callbacks (on main thread via after())
        if filepath and self._on_favicon_ready:
            try:
                self._on_favicon_ready(domain, filepath, bookmark_id)
            except Exception:
                pass

        with self._lock:
            callbacks = self._callbacks.pop(domain, [])
        if filepath:
            for callback in callbacks:
                try:
                    callback(domain, filepath)
                except Exception:
                    pass
        
        if self._progress_callback:
            try:
                self._progress_callback(self._completed, self._total_queued, domain)
            except Exception:
                pass
        
        return filepath
    
    def queue_bookmarks(self, bookmarks: List[Bookmark]):
        """Queue all bookmarks for favicon download - skips failed domains"""
        domains_seen = set()
        
        for bm in bookmarks:
            domain = self._normalize_domain(getattr(bm, "domain", ""))
            if not domain:
                continue
            # Skip if already cached, pending, or previously failed
            if domain not in domains_seen and domain not in self._cache:
                # Skip failed domains on startup
                if domain in self._failed_domains:
                    continue
                domains_seen.add(domain)
                self.download_async(domain, bm.id)
    
    def redownload_all_favicons(self, bookmarks: List, callback: Callable = None,
                                progress_callback: Callable = None):
        """Redownload all favicons - clears cache first"""
        # Clear cache
        for f in self.CACHE_DIR.glob("*.*"):
            try:
                if f.is_file():
                    f.unlink()
            except OSError as e:
                log.warning(f"Could not delete favicon cache file {f}: {e}")
        self._cache.clear()
        self._failed_domains.clear()
        self._save_failed_domains()
        self._total_queued = 0
        self._completed = 0
        
        # Queue all
        domains_seen = set()
        for bm in bookmarks:
            domain = bm.domain if hasattr(bm, 'domain') else urlparse(bm.get('url', '')).netloc
            domain = self._normalize_domain(domain)
            if domain and domain not in domains_seen:
                domains_seen.add(domain)
                bm_id = bm.id if hasattr(bm, 'id') else 0
                self.download_async(domain, bm_id)
    
    def redownload_missing_favicons(self, bookmarks: List, callback: Callable = None,
                                    progress_callback: Callable = None):
        """Redownload only missing favicons - clears failed list first"""
        # Clear failed domains to retry
        self._failed_domains.clear()
        self._save_failed_domains()
        
        # Remove FAILED markers from cache
        self._cache = {k: v for k, v in self._cache.items() if v != "FAILED"}
        
        self._total_queued = 0
        self._completed = 0
        
        # Queue missing
        domains_seen = set()
        for bm in bookmarks:
            domain = bm.domain if hasattr(bm, 'domain') else urlparse(bm.get('url', '')).netloc
            domain = self._normalize_domain(domain)
            if domain and domain not in domains_seen and domain not in self._cache:
                domains_seen.add(domain)
                bm_id = bm.id if hasattr(bm, 'id') else 0
                self.download_async(domain, bm_id)
    
    def set_progress_callback(self, callback: Callable):
        """Set progress callback: callback(completed, total, current_domain)"""
        self._progress_callback = callback
    
    def set_favicon_ready_callback(self, callback: Callable):
        """Set callback when favicon ready: callback(domain, filepath, bookmark_id)"""
        self._on_favicon_ready = callback
    
    @property
    def progress(self) -> Tuple[int, int]:
        """Get progress: (completed, total)"""
        return self._completed, self._total_queued
    
    @property
    def is_downloading(self) -> bool:
        """Check if downloads are in progress"""
        return len(self._pending) > 0
    
    def shutdown(self):
        """Shutdown the executor"""
        self._executor.shutdown(wait=False)
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        total_size = 0
        for f in self.CACHE_DIR.glob("*.*"):
            if not f.is_file():
                continue
            try:
                total_size += f.stat().st_size
            except OSError:
                continue
        
        return {
            "cached_count": len(self._cache),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }
    
    def clear_cache(self):
        """Clear all cached favicons"""
        for f in self.CACHE_DIR.glob("*.*"):
            try:
                if f.is_file():
                    f.unlink()
            except OSError as e:
                log.warning(f"Could not delete favicon cache file {f}: {e}")
        self._cache.clear()


class FaviconWrapperGenerator:
    """Generate HTML wrapper pages with custom favicons for bookmarks"""
    
    WRAPPER_DIR = APP_DIR / "favicon_wrappers"
    
    @classmethod
    def ensure_dir(cls):
        cls.WRAPPER_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def generate_wrapper(cls, bookmark: Bookmark, favicon_path: str) -> Optional[str]:
        """
        Generate an HTML wrapper page with custom favicon.
        Returns the path to the wrapper file.
        """
        cls.ensure_dir()
        
        # Read and encode favicon
        favicon_data = ""
        try:
            with open(favicon_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
                # Detect image type
                if favicon_path.lower().endswith('.png'):
                    mime = "image/png"
                elif favicon_path.lower().endswith('.ico'):
                    mime = "image/x-icon"
                else:
                    mime = "image/png"
                favicon_data = f"data:{mime};base64,{data}"
        except Exception as e:
            log.warning(f"Error reading favicon {favicon_path}: {e}")
            return None
        
        # Sanitize title for filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in bookmark.title).strip()[:50]
        safe_title = safe_title or "bookmark"
        filename = f"{safe_title}_{bookmark.id}.html"
        filepath = cls.WRAPPER_DIR / filename
        
        # Generate HTML
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{html_module.escape(bookmark.title)}</title>
    <link rel="icon" href="{favicon_data}">
    <meta http-equiv="refresh" content="0; url={html_module.escape(bookmark.url)}">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: #1a1a2e;
            color: #eee;
        }}
        .loader {{
            text-align: center;
        }}
        .spinner {{
            width: 40px;
            height: 40px;
            border: 3px solid #333;
            border-top-color: #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="loader">
        <div class="spinner"></div>
        <p>Redirecting to {html_module.escape(bookmark.domain or bookmark.url)}...</p>
    </div>
</body>
</html>'''
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            return str(filepath)
        except Exception as e:
            log.warning(f"Error writing favicon wrapper {filepath}: {e}")
            return None
    
    @classmethod
    def update_bookmark_with_wrapper(cls, bookmark: Bookmark, favicon_path: str) -> bool:
        """
        Update a bookmark to use a wrapper page with custom favicon.
        Stores original URL and creates wrapper.
        """
        wrapper_path = cls.generate_wrapper(bookmark, favicon_path)
        if wrapper_path:
            # Store original URL
            if not bookmark.notes:
                bookmark.notes = ""
            if "Original URL:" not in bookmark.notes:
                bookmark.notes = f"Original URL: {bookmark.url}\n{bookmark.notes}"
            
            # Update to wrapper URL
            bookmark.url = f"file:///{wrapper_path.replace(chr(92), '/')}"
            bookmark.custom_favicon = favicon_path
            return True
        return False
