"""Page metadata and Wayback Machine integration.

- fetch_page_metadata(): auto-fetches title, description, favicon from live URLs
- wayback_check(): checks for existing archive.org snapshot
- wayback_save(): submits URL to Wayback Machine for archival

Inspired by Linkding, Shiori, Hoarder, Linkwarden, ArchiveBox.
"""

import html as html_module
import importlib
import re
import urllib.parse
from typing import Dict, Optional
from urllib.parse import urlparse


_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)


def fetch_page_metadata(url: str, timeout: int = 10) -> Dict[str, str]:
    """Fetch page title, description, and favicon URL from a live URL.

    Returns dict with keys: title, description, favicon_url.
    All values default to empty string on failure.
    """
    result = {'title': '', 'description': '', 'favicon_url': ''}

    try:
        requests = importlib.import_module('requests')
    except ImportError:
        return result

    try:
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': _USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        }, allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return result

    content_type = resp.headers.get('content-type', '')
    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
        return result

    html_text = resp.text[:100_000]  # Cap to avoid memory issues

    # Extract <title>
    m = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
    if m:
        result['title'] = html_module.unescape(m.group(1).strip())[:500]

    # Extract meta description (tries both attribute orders)
    m = re.search(
        r'<meta\s+(?:[^>]*?\s+)?(?:name|property)\s*=\s*["\'](?:description|og:description)["\']'
        r'\s+(?:[^>]*?\s+)?content\s*=\s*["\']([^"\']*)["\']',
        html_text, re.IGNORECASE
    )
    if not m:
        m = re.search(
            r'<meta\s+(?:[^>]*?\s+)?content\s*=\s*["\']([^"\']*)["\']'
            r'\s+(?:[^>]*?\s+)?(?:name|property)\s*=\s*["\'](?:description|og:description)["\']',
            html_text, re.IGNORECASE
        )
    if m:
        result['description'] = html_module.unescape(m.group(1).strip())[:1000]

    # Extract favicon
    m = re.search(
        r'<link\s+[^>]*?rel\s*=\s*["\'](?:icon|shortcut icon|apple-touch-icon)["\']'
        r'[^>]*?href\s*=\s*["\']([^"\']+)["\']',
        html_text, re.IGNORECASE
    )
    if not m:
        m = re.search(
            r'<link\s+[^>]*?href\s*=\s*["\']([^"\']+)["\']'
            r'[^>]*?rel\s*=\s*["\'](?:icon|shortcut icon|apple-touch-icon)["\']',
            html_text, re.IGNORECASE
        )
    if m:
        favicon_href = m.group(1)
        if favicon_href.startswith('//'):
            favicon_href = 'https:' + favicon_href
        elif favicon_href.startswith('/'):
            parsed = urlparse(url)
            favicon_href = f"{parsed.scheme}://{parsed.netloc}{favicon_href}"
        result['favicon_url'] = favicon_href

    return result


def wayback_check(url: str, timeout: int = 10) -> Optional[str]:
    """Check if a URL has a Wayback Machine snapshot.

    Returns the latest snapshot URL, or None if not archived.
    """
    try:
        requests = importlib.import_module('requests')
    except ImportError:
        return None

    try:
        api_url = f"https://archive.org/wayback/available?url={urllib.parse.quote(url, safe='')}"
        resp = requests.get(api_url, timeout=timeout)
        data = resp.json()
        snapshot = data.get('archived_snapshots', {}).get('closest', {})
        if snapshot.get('available'):
            return snapshot.get('url', '')
    except Exception:
        pass
    return None


def wayback_save(url: str, timeout: int = 30) -> Optional[str]:
    """Submit a URL to the Wayback Machine for archival.

    Returns the archive URL on success, or None on failure.
    """
    try:
        requests = importlib.import_module('requests')
    except ImportError:
        return None

    try:
        save_url = f"https://web.archive.org/save/{url}"
        resp = requests.get(save_url, timeout=timeout, headers={
            'User-Agent': 'BookmarkOrganizerPro (bookmark archival)',
        }, allow_redirects=True)
        if resp.status_code in (200, 301, 302):
            location = resp.headers.get('Content-Location') or resp.headers.get('Location', '')
            if location:
                return f"https://web.archive.org{location}"
            return resp.url
    except Exception:
        pass
    return None
