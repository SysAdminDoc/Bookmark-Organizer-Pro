"""URL manipulation and analysis utilities.

Redirect resolution, HTTPS upgrade, affiliate detection, canonical URL lookup.
"""

import html as html_module
import ipaddress
import re
import socket
import urllib.parse
from typing import List, Optional, Tuple


class URLUtilities:
    """Various URL manipulation and analysis utilities"""

    SSRF_ALLOW_LIST: list = []

    @classmethod
    def set_ssrf_allow_list(cls, patterns: list):
        """Set regex patterns for domains allowed to bypass SSRF private-IP checks.

        Example: [".*\\.internal\\.corp\\.com$", "wiki\\.local$"]
        """
        cls.SSRF_ALLOW_LIST = [re.compile(p, re.IGNORECASE) for p in patterns if p]

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

    # NAT64 well-known prefix (RFC 6052) — embeds an IPv4 address in the low bits.
    _NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")

    @classmethod
    def _ip_is_blocked(cls, ip) -> bool:
        """True if an IP must not be fetched (SSRF protection).

        Unwraps IPv4-mapped (``::ffff:a.b.c.d``) and NAT64-embedded addresses so
        an attacker cannot smuggle a private/loopback/metadata target past the
        filter inside an IPv6 wrapper. ``not is_global`` already covers private
        ranges on modern Python, but the explicit flags below make the intent
        clear and stay correct across versions where mapped-address properties
        behave differently.
        """
        if isinstance(ip, ipaddress.IPv6Address):
            if ip.ipv4_mapped is not None:
                ip = ip.ipv4_mapped
            elif ip in cls._NAT64_PREFIX:
                ip = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
        return (
            ip.is_multicast or ip.is_unspecified or ip.is_loopback
            or ip.is_link_local or ip.is_private or ip.is_reserved
            or not ip.is_global
        )

    @classmethod
    def resolve_public_addresses(cls, url: str) -> Tuple[list[str], str]:
        """Resolve an outbound URL once and return validated connection targets."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return [], "unsupported URL scheme"
        if parsed.username or parsed.password:
            return [], "URL credentials are not allowed"
        hostname = (parsed.hostname or '').strip().rstrip('.').lower()
        if not hostname or hostname in ('localhost', '0.0.0.0', '::'):
            return [], "local or missing hostname"
        try:
            ascii_host = hostname.encode("idna").decode("ascii")
            addresses: list[str] = []
            for info in socket.getaddrinfo(ascii_host, parsed.port, socket.AF_UNSPEC):
                address = str(ipaddress.ip_address(info[4][0]))
                ip = ipaddress.ip_address(address)
                if cls._ip_is_blocked(ip):
                    if cls.SSRF_ALLOW_LIST and any(
                        pattern.search(hostname) for pattern in cls.SSRF_ALLOW_LIST
                    ):
                        addresses.append(address)
                        continue
                    return [], f"blocked network address: {ip}"
                if address not in addresses:
                    addresses.append(address)
            if not addresses:
                return [], "hostname did not resolve"
            return addresses, "allowed public HTTP URL"
        except Exception as exc:
            return [], f"URL validation failed: {exc}"

    @classmethod
    def check_safe_url(cls, url: str) -> Tuple[bool, str]:
        """Validate an outbound HTTP URL and return ``(allowed, reason)``.

        Domains matching SSRF_ALLOW_LIST regex patterns bypass the private-IP check.

        This validates the hostname's currently resolved addresses. Public network
        callers use ``services.egress`` to connect to one of those exact addresses,
        preserving Host and TLS SNI without a second DNS lookup.
        """
        addresses, reason = cls.resolve_public_addresses(url)
        return bool(addresses), reason

    @classmethod
    def _is_safe_url(cls, url: str) -> bool:
        """Block requests to private/internal networks (SSRF protection)."""
        return cls.check_safe_url(url)[0]

    @staticmethod
    def resolve_redirect(url: str, max_redirects: int = 5) -> Tuple[str, int]:
        """Resolve URL redirects and return (final_url, redirect_count)."""
        from bookmark_organizer_pro.services.egress import public_egress as requests

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

        from bookmark_organizer_pro.services.egress import public_egress as requests

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
            from bookmark_organizer_pro.services.egress import public_egress as requests
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
