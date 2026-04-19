"""URL manipulation and analysis utilities.

Redirect resolution, HTTPS upgrade, affiliate detection, canonical URL lookup.
"""

import importlib
import html as html_module
import ipaddress
import re
import socket
import urllib.parse
from typing import List, Optional, Tuple


class URLUtilities:
    """Various URL manipulation and analysis utilities"""

    SHORTENERS = [
        'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'ow.ly', 'is.gd',
        'buff.ly', 'j.mp', 'amzn.to', 'youtu.be', 'rb.gy', 'cutt.ly',
        'short.io', 'rebrand.ly', 'bl.ink', 'snip.ly'
    ]

    AFFILIATE_PARAMS = [
        'ref', 'affiliate', 'aff', 'partner', 'tag', 'camp', 'src',
        'via', 'referral', 'ref_', 'aff_', 'associate', 'linkId'
    ]

    AFFILIATE_DOMAINS = [
        'amzn.to', 'amazon.com/gp/product', 'amazon.com/dp',
        'shareasale.com', 'commission-junction.com', 'rakuten.com',
        'awin1.com', 'pepperjam.com', 'jdoqocy.com', 'tkqlhce.com'
    ]

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """Block requests to private/internal networks (SSRF protection)."""
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False
            hostname = (parsed.hostname or '').strip().rstrip('.').lower()
            if not hostname or hostname in ('localhost', '0.0.0.0', '::'):
                return False
            ascii_host = hostname.encode("idna").decode("ascii")
            for info in socket.getaddrinfo(ascii_host, None, socket.AF_UNSPEC):
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_multicast or ip.is_unspecified or not ip.is_global:
                    return False
            return True
        except Exception:
            return False

    @staticmethod
    def resolve_redirect(url: str, max_redirects: int = 5) -> Tuple[str, int]:
        """Resolve URL redirects and return (final_url, redirect_count)."""
        try:
            requests = importlib.import_module('requests')
        except ImportError:
            return url, 0

        redirect_count = 0
        current_url = url

        for _ in range(max_redirects):
            try:
                if not URLUtilities._is_safe_url(current_url):
                    break

                response = requests.head(
                    current_url,
                    allow_redirects=False,
                    timeout=5,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )

                if response.status_code in (301, 302, 303, 307, 308):
                    next_url = response.headers.get('Location', '')
                    response.close()
                    if next_url:
                        next_url = urllib.parse.urljoin(current_url, next_url)
                        # Block non-http redirects (javascript:, data:, etc.)
                        if not URLUtilities._is_safe_url(next_url):
                            break
                        current_url = next_url
                        redirect_count += 1
                        continue
                response.close()
                break
            except Exception:
                break

        return current_url, redirect_count

    @staticmethod
    def is_shortened_url(url: str) -> bool:
        """Check if URL is from a known shortener"""
        try:
            domain = (urllib.parse.urlparse(url).hostname or '').lower()
            return any(domain == shortener or domain.endswith("." + shortener)
                       for shortener in URLUtilities.SHORTENERS)
        except Exception:
            return False

    @staticmethod
    def upgrade_to_https(url: str) -> str:
        """Upgrade HTTP URL to HTTPS"""
        if url.startswith('http://'):
            return 'https://' + url[7:]
        return url

    @staticmethod
    def check_https_available(url: str) -> bool:
        """Check if HTTPS version of URL is available"""
        if url.startswith('https://'):
            return True

        try:
            requests = importlib.import_module('requests')
        except ImportError:
            return False

        https_url = URLUtilities.upgrade_to_https(url)
        if not URLUtilities._is_safe_url(https_url):
            return False
        try:
            response = requests.head(https_url, timeout=5, allow_redirects=False)
            try:
                return response.status_code < 400
            finally:
                response.close()
        except Exception:
            return False

    @staticmethod
    def detect_affiliate_link(url: str) -> Tuple[bool, List[str]]:
        """Detect if URL is an affiliate link. Returns (is_affiliate, reasons)."""
        reasons = []

        try:
            parsed = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed.query)

            for param in URLUtilities.AFFILIATE_PARAMS:
                if param in query_params or param.lower() in [p.lower() for p in query_params]:
                    reasons.append(f"Contains '{param}' parameter")

            domain = parsed.netloc.lower()
            for aff_domain in URLUtilities.AFFILIATE_DOMAINS:
                if aff_domain in url.lower():
                    reasons.append(f"Uses affiliate domain: {aff_domain}")

            if 'amazon' in domain and 'tag' in query_params:
                reasons.append("Amazon Associate link")

        except Exception:
            pass

        return len(reasons) > 0, reasons

    @staticmethod
    def clean_affiliate_link(url: str) -> str:
        """Remove affiliate parameters from URL"""
        try:
            parsed = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed.query)

            clean_params = {
                k: v for k, v in query_params.items()
                if k.lower() not in [p.lower() for p in URLUtilities.AFFILIATE_PARAMS]
            }

            clean_query = urllib.parse.urlencode(clean_params, doseq=True)
            return urllib.parse.urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, clean_query, ''
            ))
        except Exception:
            return url

    @staticmethod
    def get_canonical_url(url: str) -> Optional[str]:
        """Try to get canonical URL from page"""
        try:
            requests = importlib.import_module('requests')
            if not URLUtilities._is_safe_url(url):
                return None
            response = requests.get(
                url, timeout=10,
                headers={'User-Agent': 'Mozilla/5.0'},
                allow_redirects=False,
                stream=True,
            )

            try:
                if response.status_code != 200:
                    return None
                content_type = response.headers.get('content-type', '')
                if content_type and 'text/html' not in content_type and 'application/xhtml' not in content_type:
                    return None
                try:
                    content_length = int(response.headers.get('content-length', 0))
                except (TypeError, ValueError):
                    content_length = 0
                if content_length > 2_000_000:
                    return None
                chunks = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    chunks.extend(chunk)
                    if len(chunks) >= 100_000:
                        break
                html_text = bytes(chunks[:100_000]).decode(
                    response.encoding or 'utf-8',
                    errors='replace',
                )
                match = re.search(
                    r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
                    html_text, re.IGNORECASE
                )
                if match:
                    canonical = urllib.parse.urljoin(url, html_module.unescape(match.group(1)))
                    return canonical if URLUtilities._is_safe_url(canonical) else None

                match = re.search(
                    r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']',
                    html_text, re.IGNORECASE
                )
                if match:
                    canonical = urllib.parse.urljoin(url, html_module.unescape(match.group(1)))
                    return canonical if URLUtilities._is_safe_url(canonical) else None
            finally:
                response.close()
        except Exception:
            pass

        return None
