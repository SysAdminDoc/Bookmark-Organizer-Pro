"""Adversarial RFC 2557 coverage for the offline archive contract."""

from __future__ import annotations

import email
from unittest.mock import patch

from bookmark_organizer_pro.services.web_tools import LocalArchiver


class _Response:
    status_code = 200

    def __init__(self, payload: bytes, content_type: str):
        self.payload = payload
        self.headers = {
            "content-type": content_type,
            "content-length": str(len(payload)),
        }

    def iter_content(self, chunk_size=16384):
        yield self.payload

    def close(self):
        return None


def test_mhtml_rewrites_srcset_nested_imports_and_navigation_markup(tmp_path):
    responses = {
        "https://example.com/one.png": _Response(b"ONE", "image/png"),
        "https://example.com/two.png": _Response(b"TWO", "image/png"),
        "https://example.com/nested.css": _Response(
            b"body{background:url('/pixel.png')}", "text/css"
        ),
        "https://example.com/pixel.png": _Response(b"PIXEL", "image/png"),
    }

    def get(url, **_kwargs):
        return responses[url]

    archiver = LocalArchiver.__new__(LocalArchiver)
    archiver.ARCHIVE_DIR = tmp_path
    markup = (
        '<base href="https://attacker.example/">'
        '<meta http-equiv="refresh" content="0; url=https://attacker.example/">'
        '<style>@import "/nested.css";</style>'
        '<img srcset="/one.png 1x, /two.png 2x">'
    )
    with patch("bookmark_organizer_pro.services.web_tools.URLUtilities._is_safe_url", return_value=True), \
            patch("bookmark_organizer_pro.services.web_tools.requests.get", side_effect=get):
        payload = archiver._build_mhtml(markup, "https://example.com/page")

    message = email.message_from_bytes(payload)
    assert message.get_content_type() == "multipart/related"
    html_part = next(part for part in message.walk() if part.get_content_type() == "text/html")
    html = html_part.get_payload(decode=True).decode("utf-8")
    assert "<base" not in html
    assert "http-equiv=\"refresh\"" not in html
    assert "srcset=\"cid:resource-" in html
    assert "@import url('cid:resource-" in html
    css = [
        part.get_payload(decode=True).decode("utf-8")
        for part in message.walk()
        if part.get_content_type() == "text/css"
    ]
    assert len(css) == 1
    assert "url('cid:resource-" in css[0]
    assert sum(part.get_content_type() == "image/png" for part in message.walk()) == 3
