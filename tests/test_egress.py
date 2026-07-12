"""Tests for bounded and DNS-pinned public HTTP egress."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from bookmark_organizer_pro.services.egress import (
    BoundedEgressClient,
    EgressPolicy,
    EgressPolicyError,
    EgressResponseTooLarge,
    _PinnedDNSAdapter,
)


class _Response:
    def __init__(self, status=200, body=b"ok", headers=None):
        self.status_code = status
        self.headers = headers or {"content-length": str(len(body))}
        self._body = body
        self.closed = False
        self.url = ""

    def iter_content(self, chunk_size=65_536):
        yield self._body

    def close(self):
        self.closed = True


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.trust_env = True

    def mount(self, *_args):
        return None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class TestBoundedEgress(unittest.TestCase):
    @patch(
        "bookmark_organizer_pro.services.egress.URLUtilities.resolve_public_addresses",
        return_value=(["203.0.113.10"], "allowed"),
    )
    def test_adapter_pins_validated_address_and_preserves_host(self, _resolve):
        ip, hostname, port, host = _PinnedDNSAdapter._target("https://example.com:8443/a")
        self.assertEqual((ip, hostname, port), ("203.0.113.10", "example.com", 8443))
        self.assertEqual(host, "example.com:8443")

    @patch(
        "bookmark_organizer_pro.services.egress.URLUtilities.check_safe_url",
        return_value=(True, "allowed"),
    )
    def test_validates_redirects_and_strips_cross_host_authorization(self, _safe):
        session = _Session([
            _Response(302, headers={"Location": "https://other.example/final"}),
            _Response(200, body=b"done"),
        ])
        client = BoundedEgressClient(EgressPolicy(max_redirects=2), session=session)
        response = client.get(
            "https://example.com/start",
            headers={"Authorization": "Bearer secret"},
        )
        self.assertEqual(response._content, b"done")
        self.assertNotIn("Authorization", session.calls[1][2]["headers"])
        self.assertTrue(all(call[2]["allow_redirects"] is False for call in session.calls))

    @patch(
        "bookmark_organizer_pro.services.egress.URLUtilities.check_safe_url",
        return_value=(True, "allowed"),
    )
    def test_rejects_declared_and_streamed_oversized_responses(self, _safe):
        declared = BoundedEgressClient(
            EgressPolicy(max_bytes=4),
            session=_Session([_Response(headers={"content-length": "5"})]),
        )
        with self.assertRaises(EgressResponseTooLarge):
            declared.get("https://example.com")

        streamed = BoundedEgressClient(
            EgressPolicy(max_bytes=4),
            session=_Session([_Response(body=b"12345", headers={})]),
        )
        with self.assertRaises(EgressResponseTooLarge):
            streamed.get("https://example.com")

    @patch(
        "bookmark_organizer_pro.services.egress.URLUtilities.check_safe_url",
        return_value=(False, "blocked network address"),
    )
    def test_blocks_before_transport(self, _safe):
        session = _Session([])
        client = BoundedEgressClient(session=session)
        with self.assertRaises(EgressPolicyError):
            client.get("http://127.0.0.1")
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
