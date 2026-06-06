"""ATOM and JSON Feed export for bookmark collections.

Generates standard Atom 1.0 (RFC 4287) and JSON Feed 1.1 feeds from
a list of bookmarks so collections can be shared as RSS/feed subscriptions.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import List, Optional
from pathlib import Path
from urllib.parse import urlparse

from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION, EXPORTS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


def _iso(ts: str) -> str:
    """Normalize an ISO timestamp or return current time."""
    if ts:
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return ts
        except (ValueError, TypeError):
            pass
    return datetime.now().isoformat()


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _safe_feed_filename(title: str, suffix: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60]
    return f"{safe.strip() or 'feed'}{suffix}"


def _media_type(bookmark: Bookmark) -> str:
    content_type = str(getattr(bookmark, "content_type", "") or "").split(";", 1)[0].strip().lower()
    if content_type:
        return content_type
    path = urlparse(bookmark.url).path.lower()
    if path.endswith(".epub"):
        return "application/epub+zip"
    if path.endswith(".pdf"):
        return "application/pdf"
    return "text/html"


def export_atom(bookmarks: List[Bookmark], title: str = "Bookmarks",
                output_path: Optional[Path] = None) -> Path:
    """Export bookmarks as an Atom 1.0 XML feed."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORTS_DIR / _safe_feed_filename(title, ".atom.xml")

    updated = _iso(bookmarks[0].modified_at if bookmarks else "")

    entries = []
    for bm in bookmarks:
        entry = f"""  <entry>
    <title>{_esc(bm.title)}</title>
    <link href="{_esc(bm.url)}" rel="alternate"/>
    <id>urn:bop:bookmark:{bm.id}</id>
    <updated>{_iso(bm.modified_at)}</updated>
    <published>{_iso(bm.created_at)}</published>
    <summary>{_esc(bm.description or bm.notes or '')}</summary>
    <category term="{_esc(bm.category)}"/>"""
        for tag in bm.tags:
            entry += f'\n    <category term="{_esc(tag)}"/>'
        entry += "\n  </entry>"
        entries.append(entry)

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{_esc(title)}</title>
  <subtitle>Exported from {APP_NAME} v{APP_VERSION}</subtitle>
  <id>urn:bop:feed:{_esc(title)}</id>
  <updated>{updated}</updated>
  <generator uri="https://github.com/SysAdminDoc/Bookmark-Organizer-Pro" version="{APP_VERSION}">{APP_NAME}</generator>
{chr(10).join(entries)}
</feed>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(feed_xml, encoding="utf-8")
    log.info(f"Atom feed exported: {output_path} ({len(bookmarks)} entries)")
    return output_path


def export_json_feed(bookmarks: List[Bookmark], title: str = "Bookmarks",
                     output_path: Optional[Path] = None) -> Path:
    """Export bookmarks as a JSON Feed 1.1 file."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORTS_DIR / _safe_feed_filename(title, ".json")

    items = []
    for bm in bookmarks:
        item = {
            "id": str(bm.id),
            "url": bm.url,
            "title": bm.title,
            "date_published": _iso(bm.created_at),
            "date_modified": _iso(bm.modified_at),
            "tags": list(bm.tags),
        }
        if bm.description or bm.notes:
            item["summary"] = bm.description or bm.notes
        if bm.language:
            item["language"] = bm.language
        items.append(item)

    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": title,
        "description": f"Exported from {APP_NAME} v{APP_VERSION}",
        "items": items,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"JSON Feed exported: {output_path} ({len(bookmarks)} items)")
    return output_path


def render_opds(bookmarks: List[Bookmark], title: str = "Bookmarks",
                catalog_url: str = "") -> str:
    """Render bookmarks as an OPDS 1.2 acquisition feed XML string."""
    updated = _iso(bookmarks[0].modified_at if bookmarks else "")
    self_link = ""
    if catalog_url:
        self_link = (
            f'  <link rel="self" href="{_esc(catalog_url)}" '
            'type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>\n'
        )

    entries = []
    for bm in bookmarks:
        summary = bm.description or bm.notes or bm.url
        author = bm.domain or APP_NAME
        entry = f"""  <entry>
    <title>{_esc(bm.title)}</title>
    <id>urn:bop:bookmark:{_esc(bm.id)}</id>
    <updated>{_iso(bm.modified_at)}</updated>
    <published>{_iso(bm.created_at)}</published>
    <author><name>{_esc(author)}</name></author>
    <summary>{_esc(summary)}</summary>
    <category term="{_esc(bm.category)}"/>"""
        for tag in bm.tags:
            entry += f'\n    <category term="{_esc(tag)}"/>'
        if bm.language:
            entry += f"\n    <dc:language>{_esc(bm.language)}</dc:language>"
        entry += (
            f'\n    <link rel="http://opds-spec.org/acquisition/open-access" '
            f'href="{_esc(bm.url)}" type="{_esc(_media_type(bm))}"/>'
        )
        entry += "\n  </entry>"
        entries.append(entry)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:dc="http://purl.org/dc/terms/"
      xmlns:opds="http://opds-spec.org/2010/catalog">
  <title>{_esc(title)}</title>
  <id>urn:bop:opds:{_esc(title)}</id>
  <updated>{updated}</updated>
  <author><name>{APP_NAME}</name></author>
  <generator uri="https://github.com/SysAdminDoc/Bookmark-Organizer-Pro" version="{APP_VERSION}">{APP_NAME}</generator>
{self_link}{chr(10).join(entries)}
</feed>
"""


def export_opds(bookmarks: List[Bookmark], title: str = "Bookmarks",
                output_path: Optional[Path] = None,
                catalog_url: str = "") -> Path:
    """Export bookmarks as an OPDS 1.2 acquisition feed."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORTS_DIR / _safe_feed_filename(title, ".opds.xml")

    feed_xml = render_opds(bookmarks, title=title, catalog_url=catalog_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(feed_xml, encoding="utf-8")
    log.info(f"OPDS feed exported: {output_path} ({len(bookmarks)} entries)")
    return output_path
