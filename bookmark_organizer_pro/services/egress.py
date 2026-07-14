"""Bounded, DNS-pinned HTTP egress for public internet resources."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests as _requests
from requests.adapters import HTTPAdapter

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.url_utils import URLUtilities


class EgressPolicyError(_requests.RequestException):
    """Raised when a request violates the local outbound-network policy."""


class EgressResponseTooLarge(EgressPolicyError):
    """Raised when response headers or body exceed the configured ceiling."""


class _PinnedDNSAdapter(HTTPAdapter):
    """Connect to a prevalidated IP while preserving HTTP Host and TLS SNI."""

    @staticmethod
    def _target(url: str) -> tuple[str, str, int | None, str]:
        parsed = urlsplit(url)
        addresses, reason = URLUtilities.resolve_public_addresses(url)
        if not addresses:
            raise EgressPolicyError(f"Blocked outbound request to {url}: {reason}")
        hostname = parsed.hostname or ""
        host_header = hostname
        if ":" in hostname and not hostname.startswith("["):
            host_header = f"[{hostname}]"
        default_port = 443 if parsed.scheme == "https" else 80
        if parsed.port and parsed.port != default_port:
            host_header = f"{host_header}:{parsed.port}"
        return addresses[0], hostname, parsed.port, host_header

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        if proxies:
            raise EgressPolicyError("Outbound proxy settings are disabled for protected requests")
        ip, hostname, port, host_header = self._target(request.url)
        request.headers["Host"] = host_header
        host_params, pool_kwargs = self.build_connection_pool_key_attributes(
            request, verify, cert,
        )
        host_params["host"] = ip
        host_params["port"] = port
        if host_params["scheme"] == "https":
            pool_kwargs["assert_hostname"] = hostname
            pool_kwargs["server_hostname"] = hostname
        return self.poolmanager.connection_from_host(
            **host_params, pool_kwargs=pool_kwargs,
        )


@dataclass(frozen=True)
class EgressPolicy:
    max_redirects: int = 5
    max_bytes: int = 25_000_000
    request_timeout_seconds: float = 15.0
    total_timeout_seconds: float = 120.0


class BoundedEgressClient:
    """Requests-compatible client enforcing one public-network policy."""

    exceptions = _requests.exceptions
    _SENSITIVE_REDIRECT_HEADERS = frozenset(
        {"authorization", "proxy-authorization", "cookie"}
    )

    def __init__(self, policy: EgressPolicy | None = None, *, session=None):
        self.policy = policy or EgressPolicy()
        self.session = session or _requests.Session()
        self.session.trust_env = False
        adapter = _PinnedDNSAdapter(pool_connections=10, pool_maxsize=20, max_retries=0)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    @staticmethod
    def _bounded_timeout(value, remaining: float, policy_limit: float):
        limit = max(0.1, min(float(remaining), float(policy_limit)))
        if isinstance(value, tuple):
            return tuple(max(0.1, min(float(part), limit)) for part in value)
        if value is None:
            return limit
        return max(0.1, min(float(value), limit))

    @staticmethod
    def _read_bounded(response, max_bytes: int) -> bytes:
        chunks = bytearray()
        for chunk in response.iter_content(chunk_size=65_536):
            if not chunk:
                continue
            chunks.extend(chunk)
            if len(chunks) > max_bytes:
                raise EgressResponseTooLarge(
                    f"Response exceeded the {max_bytes}-byte egress ceiling"
                )
        return bytes(chunks)

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int | None]:
        """Return the RFC 9110 protection-space origin for a URL."""
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
        return scheme, (parsed.hostname or "").lower(), parsed.port or default_port

    @classmethod
    def _strip_cross_origin_credentials(cls, headers: dict, source: str, target: str) -> None:
        """Remove caller credentials whenever a redirect leaves its origin."""
        if cls._origin(source) == cls._origin(target):
            return
        for name in list(headers):
            if str(name).lower() in cls._SENSITIVE_REDIRECT_HEADERS:
                headers.pop(name, None)

    def request(self, method: str, url: str, **kwargs):
        allow_redirects = bool(kwargs.pop("allow_redirects", method.upper() != "HEAD"))
        caller_stream = bool(kwargs.pop("stream", False))
        max_bytes = int(kwargs.pop("max_bytes", self.policy.max_bytes))
        timeout = kwargs.pop("timeout", None)
        deadline = time.monotonic() + self.policy.total_timeout_seconds
        current_url = str(url)
        current_method = method.upper()
        headers = dict(kwargs.pop("headers", {}) or {})

        for redirect_count in range(self.policy.max_redirects + 1):
            allowed, reason = URLUtilities.check_safe_url(current_url)
            if not allowed:
                log.warning("Blocked outbound request to %s: %s", current_url, reason)
                raise EgressPolicyError(f"Blocked outbound request to {current_url}: {reason}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _requests.Timeout("Outbound request exceeded its total deadline")
            response = self.session.request(
                current_method,
                current_url,
                headers=headers,
                timeout=self._bounded_timeout(
                    timeout, remaining, self.policy.request_timeout_seconds,
                ),
                allow_redirects=False,
                stream=True,
                **kwargs,
            )
            try:
                declared = int(response.headers.get("content-length", 0) or 0)
            except (TypeError, ValueError):
                declared = 0
            if declared > max_bytes:
                response.close()
                raise EgressResponseTooLarge(
                    f"Response declared {declared} bytes; limit is {max_bytes}"
                )

            if response.status_code not in (301, 302, 303, 307, 308) or not allow_redirects:
                response.url = current_url
                if not caller_stream and current_method != "HEAD":
                    try:
                        response._content = self._read_bounded(response, max_bytes)
                        response._content_consumed = True
                    except Exception:
                        response.close()
                        raise
                    response.close()
                return response

            location = response.headers.get("Location", "")
            response.close()
            if not location:
                raise EgressPolicyError("Redirect response omitted the Location header")
            if redirect_count >= self.policy.max_redirects:
                raise _requests.TooManyRedirects(
                    f"Exceeded {self.policy.max_redirects} validated redirects"
                )
            next_url = urljoin(current_url, location)
            self._strip_cross_origin_credentials(headers, current_url, next_url)
            if response.status_code == 303 or (
                response.status_code in (301, 302) and current_method == "POST"
            ):
                current_method = "GET"
                kwargs.pop("data", None)
                kwargs.pop("json", None)
            current_url = next_url

        raise _requests.TooManyRedirects("Validated redirect limit exceeded")

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs):
        return self.request("HEAD", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


public_egress = BoundedEgressClient()
