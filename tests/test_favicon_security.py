"""Security contracts for untrusted favicon payloads."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bookmark_organizer_pro.services.favicons import (
    FAVICON_PROXY_NONE,
    FaviconPrivacyPolicy,
    HighSpeedFaviconManager,
    load_favicon_policy,
    save_favicon_policy,
)
from bookmark_organizer_pro.services.settings_store import load_settings


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
        self.manager = HighSpeedFaviconManager(max_workers=1, enabled=True)
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

    def test_fresh_profile_neither_queues_nor_displays_favicons(self):
        settings_file = Path(self.temp_dir.name) / "fresh-settings.json"
        policy = load_favicon_policy(settings_file)
        self.assertEqual(
            policy,
            FaviconPrivacyPolicy(enabled=False, proxy_provider=FAVICON_PROXY_NONE),
        )

        manager = HighSpeedFaviconManager(max_workers=1)
        self.addCleanup(manager.shutdown)
        with patch.object(manager._executor, "submit") as submit:
            manager.queue_bookmarks(
                [SimpleNamespace(domain="private-example.test", id=7)]
            )
            manager.fetch_favicon("https://private-example.test/path")

        submit.assert_not_called()
        self.assertFalse(manager.enabled)
        self.assertIsNone(manager.get_cached("private-example.test"))

    @patch("bookmark_organizer_pro.services.favicons.URLUtilities._is_safe_url", return_value=True)
    @patch("bookmark_organizer_pro.services.favicons.requests.get")
    def test_same_origin_is_the_only_default_network_source(self, mock_get, _safe):
        mock_get.side_effect = lambda *_args, **_kwargs: _Response(b"invalid" * 32)

        self.manager._download_favicon(
            "saved-domain.example",
            1,
            threading.Event(),
        )

        requested_urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertEqual(
            requested_urls,
            [
                "https://saved-domain.example/favicon.ico",
                "https://saved-domain.example/favicon.png",
            ],
        )
        self.assertTrue(
            all("google.com" not in url and "duckduckgo.com" not in url
                for url in requested_urls)
        )

    @patch("bookmark_organizer_pro.services.favicons.URLUtilities._is_safe_url", return_value=True)
    @patch("bookmark_organizer_pro.services.favicons.requests.get")
    def test_named_proxy_runs_only_after_explicit_policy_opt_in(self, mock_get, _safe):
        mock_get.side_effect = lambda *_args, **_kwargs: _Response(b"invalid" * 32)
        self.manager.set_policy(
            FaviconPrivacyPolicy(enabled=True, proxy_provider="google")
        )

        self.manager._download_favicon(
            "saved-domain.example",
            1,
            threading.Event(),
        )

        requested_urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertEqual(
            requested_urls[:2],
            [
                "https://saved-domain.example/favicon.ico",
                "https://saved-domain.example/favicon.png",
            ],
        )
        self.assertEqual(
            requested_urls[2],
            "https://www.google.com/s2/favicons?domain=saved-domain.example&sz=32",
        )

    def test_disabling_policy_cancels_queued_work(self):
        manager = HighSpeedFaviconManager(max_workers=1, enabled=True)
        self.addCleanup(manager.shutdown)
        pending = MagicMock()
        pending.add_done_callback = MagicMock()
        with patch.object(manager._executor, "submit", return_value=pending):
            manager.download_async("queued.example", 9)

        self.assertTrue(manager.is_downloading)
        manager.set_policy(FaviconPrivacyPolicy(enabled=False))

        pending.cancel.assert_called_once_with()
        self.assertFalse(manager.enabled)
        self.assertFalse(manager.is_downloading)

    def test_policy_persistence_preserves_unrelated_settings_and_fails_closed(self):
        settings_file = Path(self.temp_dir.name) / "settings.json"
        settings_file.write_text(
            json.dumps({"theme": "github_dark", "favicon_proxy_provider": "unknown"}),
            encoding="utf-8",
        )
        self.assertEqual(
            load_favicon_policy(settings_file),
            FaviconPrivacyPolicy(),
        )

        saved = save_favicon_policy(
            FaviconPrivacyPolicy(enabled=True, proxy_provider="duckduckgo"),
            settings_file,
        )
        data = load_settings(settings_file)

        self.assertEqual(
            saved,
            FaviconPrivacyPolicy(enabled=True, proxy_provider="duckduckgo"),
        )
        self.assertEqual(data["theme"], "github_dark")
        self.assertTrue(data["favicon_display_enabled"])
        self.assertEqual(data["favicon_proxy_provider"], "duckduckgo")


if __name__ == "__main__":
    unittest.main()
