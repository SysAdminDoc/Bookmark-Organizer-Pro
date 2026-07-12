"""Security contracts for untrusted favicon payloads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bookmark_organizer_pro.services.favicons import HighSpeedFaviconManager


class _Response:
    def __init__(self, content: bytes, *, content_length: int | None = None):
        self.status_code = 200
        self.headers = {
            "content-type": "image/png",
            "content-length": str(len(content) if content_length is None else content_length),
        }
        self._content = content
        self.closed = False

    def iter_content(self, chunk_size: int = 8192):
        for offset in range(0, len(self._content), chunk_size):
            yield self._content[offset:offset + chunk_size]

    def close(self):
        self.closed = True


class TestFaviconSecurity(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_dir = Path(self.temp_dir.name) / "favicons"
        self.failed_file = Path(self.temp_dir.name) / "failed.json"
        self.cache_patch = patch.object(HighSpeedFaviconManager, "CACHE_DIR", self.cache_dir)
        self.failed_patch = patch.object(HighSpeedFaviconManager, "FAILED_FILE", self.failed_file)
        self.cache_patch.start()
        self.failed_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.addCleanup(self.failed_patch.stop)
        self.manager = HighSpeedFaviconManager(max_workers=1)
        self.addCleanup(self.manager.shutdown)

    @patch("bookmark_organizer_pro.services.favicons.URLUtilities._is_safe_url", return_value=True)
    @patch("bookmark_organizer_pro.services.favicons.requests.get")
    def test_rejects_declared_oversized_payload_before_reading(self, mock_get, _safe):
        responses = []

        def response_factory(*_args, **_kwargs):
            response = _Response(b"x" * 256, content_length=self.manager.MAX_FAVICON_BYTES + 1)
            responses.append(response)
            return response

        mock_get.side_effect = response_factory

        self.assertIsNone(self.manager._download_favicon("example.com", 1))
        self.assertFalse(list(self.cache_dir.glob("*.*")))
        self.assertTrue(responses)
        self.assertTrue(all(response.closed for response in responses))

    @patch("bookmark_organizer_pro.services.favicons.URLUtilities._is_safe_url", return_value=True)
    @patch("bookmark_organizer_pro.services.favicons.requests.get")
    def test_rejects_invalid_image_even_with_image_content_type(self, mock_get, _safe):
        mock_get.side_effect = lambda *_args, **_kwargs: _Response(b"not-an-image" * 32)

        self.assertIsNone(self.manager._download_favicon("example.com", 1))
        self.assertFalse(list(self.cache_dir.glob("*.*")))


if __name__ == "__main__":
    unittest.main()
