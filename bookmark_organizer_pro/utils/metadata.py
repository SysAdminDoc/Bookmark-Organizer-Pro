"""Page metadata and Wayback Machine integration.

- fetch_page_metadata(): auto-fetches title, description, favicon from live URLs
- wayback_check(): checks for existing archive.org snapshot
- wayback_save(): submits URL to Wayback Machine for archival

Inspired by Linkding, Shiori, Hoarder, Linkwarden, ArchiveBox.
"""

import html as html_module
import re
import urllib.parse
from typing import Dict, Optional

from bookmark_organizer_pro.url_utils import URLUtilities

_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)


def _is_safe_url(url: str) -> bool:
    """Block requests to private/internal networks (SSRF protection)."""
    return URLUtilities._is_safe_url(url)


def fetch_page_metadata(url: str, timeout: int = 10) -> Dict[str, str]:
    from bookmark_organizer_pro.services.job_ledger import JobLedger

    job = JobLedger().start("metadata", url_or_domain=url, backend="requests")
    try:
        result = _fetch_page_metadata(url, timeout)
    except Exception as exc:
        job.fail(exc, retryable=True)
        raise
    if any(result.values()):
        job.succeed(bytes_processed=sum(len(value.encode("utf-8")) for value in result.values()))
    else:
        job.fail("Metadata unavailable", retryable=True)
    return result


def _fetch_page_metadata(url: str, timeout: int = 10) -> Dict[str, str]:
    """Fetch page title, description, and favicon URL from a live URL.

    Returns dict with keys: title, description, favicon_url.
    All values default to empty string on failure.
    """
    result = {'title': '', 'description': '', 'favicon_url': ''}
    from bookmark_organizer_pro.services.egress import public_egress as requests

    if not _is_safe_url(url):
        return result

    resp = None
    try:
        resp = requests.get(url, timeout=timeout, headers={
            'User-Agent': _USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        }, allow_redirects=False, stream=True)
        resp.raise_for_status()
    except Exception:
        if resp is not None:
            resp.close()
        return result

    content_type = resp.headers.get('content-type', '')
    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
        resp.close()
        return result

    # Cap download size before reading body (defense against huge responses)
    try:
        content_length = int(resp.headers.get('content-length', 0))
    except (TypeError, ValueError):
        content_length = 0
    if content_length > 2_000_000:
        resp.close()
        return result

    chunks = bytearray()
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            chunks.extend(chunk)
            if len(chunks) >= 100_000:
                break
    finally:
        resp.close()

    encoding = resp.encoding or 'utf-8'
    html_text = bytes(chunks[:100_000]).decode(encoding, errors='replace')

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

    # Extract favicon — only accept safe schemes
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
        favicon_href = urllib.parse.urljoin(url, favicon_href)
        # Only store http/https favicon URLs (block javascript:, data:, etc.)
        if favicon_href.startswith(('http://', 'https://')):
            result['favicon_url'] = favicon_href

    return result


def wayback_check(url: str, timeout: int = 10) -> Optional[str]:
    """Check if a URL has a Wayback Machine snapshot.

    Returns the latest snapshot URL, or None if not archived.
    """
    from bookmark_organizer_pro.services.egress import public_egress as requests

    if not _is_safe_url(url):
        return None

    resp = None
    try:
        api_url = f"https://archive.org/wayback/available?url={urllib.parse.quote(url, safe='')}"
        resp = requests.get(api_url, timeout=timeout)
        data = resp.json()
        snapshot = data.get('archived_snapshots', {}).get('closest', {})
        if snapshot.get('available'):
            return snapshot.get('url', '')
    except Exception:
        pass
    finally:
        if resp is not None:
            resp.close()
    return None


def wayback_save(url: str, timeout: int = 30) -> Optional[str]:
    """Submit a URL to the Wayback Machine for archival.

    Returns the archive URL on success, or None on failure.
    """
    from bookmark_organizer_pro.services.egress import public_egress as requests

    if not _is_safe_url(url):
        return None

    resp = None
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
    finally:
        if resp is not None:
            resp.close()
    return None
