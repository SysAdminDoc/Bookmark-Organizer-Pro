"""Feed redirect, base-URL, and registry mutation contract tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from bookmark_organizer_pro.services.rss_feeds import FeedIngestor, FeedRegistry, parse_feed


class _Response:
    def __init__(self, text: str, url: str, headers: dict[str, str] | None = None):
        self.text = text
        self.url = url
        self.headers = headers or {}

    @staticmethod
    def raise_for_status() -> None:
        return None


def _registry(path: Path) -> tuple[FeedRegistry, str]:
    with patch(
        "bookmark_organizer_pro.services.rss_feeds.URLUtilities._is_safe_url",
        return_value=True,
    ):
        registry = FeedRegistry(path)
        feed = registry.add("https://origin.example/feed.xml", name="Example")
    return registry, feed.id


def test_xml_base_cascades_over_content_location_and_final_response_url(tmp_path: Path) -> None:
    registry, feed_id = _registry(tmp_path / "feeds.json")
    captured = []
    xml = """<rss version="2.0" xml:base="../site/">
      <channel><item xml:base="posts/"><title>Entry</title><link xml:base="2026/">one</link></item></channel>
    </rss>"""
    response = _Response(
        xml,
        "https://cdn.example/redirected/feed.xml",
        {"Content-Location": "/canonical/feed.xml"},
    )

    with (
        patch(
            "bookmark_organizer_pro.services.rss_feeds.URLUtilities._is_safe_url",
            return_value=True,
        ),
        patch(
            "bookmark_organizer_pro.services.egress.public_egress.get",
            return_value=response,
        ) as get,
    ):
        added = FeedIngestor(registry, lambda bookmark: captured.append(bookmark) or bookmark)._fetch_one(
            feed_id
        )

    assert added == 1
    assert captured[0].url == "https://cdn.example/site/posts/2026/one"
    get.assert_called_once_with(
        "https://origin.example/feed.xml",
        timeout=20,
        headers={"User-Agent": "BookmarkOrganizerPro/6.0"},
        allow_redirects=True,
    )


def test_relative_links_fall_back_to_final_response_url() -> None:
    items = parse_feed(
        "<rss><channel><item><link>posts/one</link></item></channel></rss>",
        base_url="https://final.example/feeds/current.xml",
    )

    assert items[0].link == "https://final.example/feeds/posts/one"


def test_feed_redirect_limit_failure_is_not_silenced(tmp_path: Path) -> None:
    registry, feed_id = _registry(tmp_path / "feeds.json")

    with (
        patch(
            "bookmark_organizer_pro.services.rss_feeds.URLUtilities._is_safe_url",
            return_value=True,
        ),
        patch(
            "bookmark_organizer_pro.services.egress.public_egress.get",
            side_effect=requests.TooManyRedirects("redirect cap"),
        ),
        pytest.raises(requests.TooManyRedirects, match="redirect cap"),
    ):
        FeedIngestor(registry, lambda bookmark: bookmark)._fetch_one(feed_id)


def test_registry_rejects_unsafe_or_identity_changing_updates(tmp_path: Path) -> None:
    registry, feed_id = _registry(tmp_path / "feeds.json")
    original = registry.get(feed_id)

    with pytest.raises(ValueError, match="immutable"):
        registry.update(feed_id, id="replacement")
    with patch(
        "bookmark_organizer_pro.services.rss_feeds.URLUtilities._is_safe_url",
        return_value=False,
    ), pytest.raises(ValueError, match="Unsafe"):
        registry.update(feed_id, url="http://127.0.0.1/private")
    with patch(
        "bookmark_organizer_pro.services.rss_feeds.URLUtilities._is_safe_url",
        return_value=True,
    ), pytest.raises(ValueError, match="Invalid feed AI mode"):
        registry.update(feed_id, ai_mode="SURPRISE")

    assert registry.get(feed_id) == original


def test_registry_rolls_back_a_validated_update_when_save_fails(tmp_path: Path) -> None:
    registry, feed_id = _registry(tmp_path / "feeds.json")
    with (
        patch(
            "bookmark_organizer_pro.services.rss_feeds.URLUtilities._is_safe_url",
            return_value=True,
        ),
        patch.object(registry._store, "save", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        registry.update(feed_id, name="Changed")

    assert registry.get(feed_id).name == "Example"
