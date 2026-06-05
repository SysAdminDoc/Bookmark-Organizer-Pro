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


def export_atom(bookmarks: List[Bookmark], title: str = "Bookmarks",
                output_path: Optional[Path] = None) -> Path:
    """Export bookmarks as an Atom 1.0 XML feed."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60]
        output_path = EXPORTS_DIR / f"{safe.strip() or 'feed'}.atom.xml"

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
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60]
        output_path = EXPORTS_DIR / f"{safe.strip() or 'feed'}.json"

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
