"""Single-file HTML snapshot archiver.

Produces a self-contained HTML snapshot per bookmark. Prefers the `monolith`
Rust binary when available (best fidelity, embeds all assets); falls back to
SingleFile-CLI (Node), then to a built-in BeautifulSoup-based bundler that
inlines stylesheets, images, and fonts as data URIs.

Stored under SNAPSHOTS_DIR/{id}.html. Records snapshot metadata back onto
the Bookmark.
"""

from __future__ import annotations

import base64
import importlib
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

from bookmark_organizer_pro.constants import SNAPSHOTS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.url_utils import URLUtilities


def _has_binary(name: str) -> bool:
    return shutil.which(name) is not None


def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


class SnapshotArchiver:
    """Capture a self-contained HTML snapshot of a page."""

    MAX_BYTES = 25_000_000  # 25MB hard ceiling per snapshot

    def __init__(self, snapshots_dir: Path = SNAPSHOTS_DIR):
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    # --- public API ---------------------------------------------------------

    def snapshot(self, bookmark: Bookmark) -> Tuple[bool, str]:
        """Capture and persist a snapshot. Returns (success, path_or_error)."""
        if not URLUtilities._is_safe_url(bookmark.url):
            return False, "Private or unsupported URL"
        out_path = self.snapshots_dir / f"{bookmark.id}.html"
        for backend in (self._snapshot_monolith, self._snapshot_singlefile,
                        self._snapshot_playwright, self._snapshot_python):
            try:
                ok, msg = backend(bookmark.url, out_path)
            except Exception as exc:
                log.debug(f"Snapshot backend {backend.__name__} crashed: {exc}")
                continue
            if ok:
                size = out_path.stat().st_size if out_path.exists() else 0
                bookmark.snapshot_path = str(out_path)
                bookmark.snapshot_size = size
                bookmark.snapshot_at = datetime.now().isoformat()
                bookmark.modified_at = bookmark.snapshot_at
                return True, str(out_path)
        return False, "All snapshot backends failed"

    def archive(self, bookmark: Bookmark) -> Tuple[bool, str]:
        """Compatibility alias for snapshot()."""
        return self.snapshot(bookmark)

    def delete_snapshot(self, bookmark: Bookmark) -> bool:
        path = self.snapshots_dir / f"{bookmark.id}.html"
        try:
            if path.exists():
                path.unlink()
            bookmark.snapshot_path = ""
            bookmark.snapshot_size = 0
            bookmark.snapshot_at = ""
            return True
        except OSError as exc:
            log.warning(f"Could not delete snapshot: {exc}")
            return False

    def has_snapshot(self, bookmark: Bookmark) -> bool:
        if not bookmark.snapshot_path:
            return False
        return Path(bookmark.snapshot_path).exists()

    # --- backends -----------------------------------------------------------

    def _snapshot_monolith(self, url: str, out_path: Path) -> Tuple[bool, str]:
        if not _has_binary("monolith"):
            return False, "monolith not installed"
        try:
            subprocess.run(
                ["monolith", "--isolate", "--silent",
                 "--no-audio", "--no-video",
                 "-o", str(out_path), "--", url],
                check=True, timeout=120,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return False, f"monolith failed: {exc}"
        if not out_path.exists() or out_path.stat().st_size == 0:
            return False, "monolith produced no output"
        if out_path.stat().st_size > self.MAX_BYTES:
            out_path.unlink(missing_ok=True)
            return False, "snapshot too large"
        return True, str(out_path)

    def _snapshot_singlefile(self, url: str, out_path: Path) -> Tuple[bool, str]:
        cli = None
        for cand in ("single-file", "single-file.exe"):
            if _has_binary(cand):
                cli = cand
                break
        if cli is None:
            return False, "single-file CLI not installed"
        try:
            subprocess.run(
                [cli, "--", url, str(out_path)],
                check=True, timeout=180,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return False, f"single-file failed: {exc}"
        if not out_path.exists() or out_path.stat().st_size == 0:
            return False, "single-file produced no output"
        if out_path.stat().st_size > self.MAX_BYTES:
            out_path.unlink(missing_ok=True)
            return False, "snapshot too large"
        return True, str(out_path)

    def _snapshot_playwright(self, url: str, out_path: Path) -> Tuple[bool, str]:
        """Headless Chromium via playwright — captures JS-rendered SPAs."""
        pw_sync = _try_import("playwright.sync_api")
        if pw_sync is None:
            return False, "playwright not installed"
        try:
            with pw_sync.sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(url, wait_until="networkidle", timeout=60_000)
                    content = page.content()
                finally:
                    browser.close()
            if not content or len(content) < 100:
                return False, "playwright produced empty page"
            data = content.encode("utf-8")
            if len(data) > self.MAX_BYTES:
                return False, "snapshot too large"
            out_path.write_bytes(data)
            return True, str(out_path)
        except Exception as exc:
            return False, f"playwright failed: {exc}"

    def _snapshot_python(self, url: str, out_path: Path) -> Tuple[bool, str]:
        """Pure-Python fallback: inline CSS, images, and basic fonts."""
        requests = _try_import("requests")
        bs4 = _try_import("bs4")
        if requests is None or bs4 is None:
            return False, "requests/bs4 not available"
        try:
            current_url = url
            for _ in range(5):
                resp = requests.get(
                    current_url,
                    headers={"User-Agent": "Mozilla/5.0 (BookmarkOrganizerPro/6.0)"},
                    timeout=30, allow_redirects=False,
                )
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    if not location:
                        return False, "redirect with no Location header"
                    # Resolve relative redirect against current URL
                    location = urljoin(current_url, location)
                    if not URLUtilities._is_safe_url(location):
                        return False, "redirect to unsafe URL"
                    current_url = location
                    continue
                resp.raise_for_status()
                break
            else:
                return False, "too many redirects"
            html = resp.text
        except Exception as exc:
            return False, f"fetch failed: {exc}"

        soup = bs4.BeautifulSoup(html, "html.parser")
        base = url

        # Inline external stylesheets
        for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
            href = link.get("href")
            if not href:
                continue
            css_url = urljoin(base, href)
            css = self._fetch_text(requests, css_url)
            if css is None:
                continue
            style = soup.new_tag("style")
            style.string = css
            link.replace_with(style)

        # Inline images
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src or src.startswith("data:"):
                continue
            data_url = self._fetch_data_url(requests, urljoin(base, src))
            if data_url:
                img["src"] = data_url

        # Strip scripts (snapshot is a static record)
        for tag in soup.find_all("script"):
            tag.decompose()

        import html as _html
        safe_url = _html.escape(url, quote=True)
        banner_html = (
            f'<div style="background:#1a1a2e;color:#eee;padding:8px 16px;'
            f'font:12px/1.4 system-ui;position:sticky;top:0;z-index:99999;">'
            f'Snapshot of <a style="color:#58a6ff" href="{safe_url}">{safe_url}</a> '
            f'on {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>'
        )
        if soup.body:
            soup.body.insert(0, bs4.BeautifulSoup(banner_html, "html.parser"))

        try:
            data = str(soup).encode("utf-8")
            if len(data) > self.MAX_BYTES:
                return False, "snapshot too large"
            out_path.write_bytes(data)
        except OSError as exc:
            return False, f"write failed: {exc}"
        return True, str(out_path)

    _MAX_TEXT_BYTES = 2_000_000

    def _fetch_text(self, requests, url: str) -> Optional[str]:
        if not URLUtilities._is_safe_url(url):
            return None
        try:
            r = requests.get(url, timeout=15, stream=True, allow_redirects=False)
            for _ in range(5):
                if r.status_code not in (301, 302, 303, 307, 308):
                    break
                location = r.headers.get("Location", "")
                r.close()
                if not location:
                    return None
                location = urljoin(url, location)
                if not URLUtilities._is_safe_url(location):
                    return None
                r = requests.get(location, timeout=15, stream=True, allow_redirects=False)
            if r.status_code != 200:
                r.close()
                return None
            try:
                content_len = int(r.headers.get("content-length", 0) or 0)
            except (TypeError, ValueError):
                content_len = 0
            if content_len > self._MAX_TEXT_BYTES:
                r.close()
                return None
            chunks = bytearray()
            for chunk in r.iter_content(chunk_size=8192):
                chunks.extend(chunk)
                if len(chunks) >= self._MAX_TEXT_BYTES:
                    break
            r.close()
            encoding = r.encoding or "utf-8"
            return bytes(chunks[:self._MAX_TEXT_BYTES]).decode(encoding, errors="replace")
        except Exception:
            return None

    def _fetch_data_url(self, requests, url: str) -> Optional[str]:
        if not URLUtilities._is_safe_url(url):
            return None
        try:
            r = requests.get(url, timeout=15, stream=True, allow_redirects=False)
            # Follow redirects manually with SSRF check on each hop
            for _ in range(5):
                if r.status_code not in (301, 302, 303, 307, 308):
                    break
                location = r.headers.get("Location", "")
                r.close()
                if not location:
                    return None
                location = urljoin(url, location)
                if not URLUtilities._is_safe_url(location):
                    return None
                r = requests.get(location, timeout=15, stream=True, allow_redirects=False)
            if r.status_code != 200:
                return None
            # Read up to limit via streaming to avoid loading unbounded response
            chunks = bytearray()
            for chunk in r.iter_content(chunk_size=65536):
                chunks.extend(chunk)
                if len(chunks) > 2_000_000:
                    return None
            data = bytes(chunks)
            mime = r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return None
