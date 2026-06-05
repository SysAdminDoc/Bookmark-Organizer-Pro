"""Zotero RDF import and export for academic reference bridging.

Import: parses Zotero RDF/XML export files (rdf:Description with dc:identifier,
dc:title, dc:subject tags). Export: writes bookmarks as RDF/XML that Zotero can
import via its translators.
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from bookmark_organizer_pro.constants import EXPORTS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


def _esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def import_zotero_rdf(path: str) -> List[Bookmark]:
    """Import bookmarks from a Zotero RDF/XML export file."""
    try:
        try:
            from defusedxml.ElementTree import parse as _parse
        except ImportError:
            from xml.etree.ElementTree import parse as _parse
        tree = _parse(path)
        root = tree.getroot()
    except Exception as exc:
        log.error(f"Zotero RDF import failed: {exc}")
        return []

    ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dcterms": "http://purl.org/dc/terms/",
        "bib": "http://purl.org/net/biblio#",
        "z": "http://www.zotero.org/namespaces/export#",
        "link": "http://purl.org/rss/1.0/modules/link/",
    }

    bookmarks = []
    for item in root.iter():
        url = item.get(f"{{{ns['rdf']}}}about", "") or ""
        if not url.startswith(("http://", "https://")):
            id_el = item.find("dc:identifier", ns)
            if id_el is not None and id_el.text:
                url = id_el.text.strip()
        if not url.startswith(("http://", "https://")):
            continue

        title = ""
        title_el = item.find("dc:title", ns)
        if title_el is not None and title_el.text:
            title = title_el.text.strip()

        tags = []
        for subj in item.findall("dc:subject", ns):
            if subj.text and subj.text.strip():
                tags.append(subj.text.strip())

        desc = ""
        desc_el = item.find("dcterms:abstract", ns) or item.find("dc:description", ns)
        if desc_el is not None and desc_el.text:
            desc = desc_el.text.strip()

        date = ""
        date_el = item.find("dc:date", ns) or item.find("dcterms:dateSubmitted", ns)
        if date_el is not None and date_el.text:
            date = date_el.text.strip()

        bm = Bookmark(
            id=None,
            url=url,
            title=title or url,
            tags=tags,
            description=desc,
            created_at=date,
            source_file=str(path),
        )
        bookmarks.append(bm)

    log.info(f"Zotero RDF import: {len(bookmarks)} items from {path}")
    return bookmarks


def export_zotero_rdf(bookmarks: List[Bookmark],
                      output_path: Optional[Path] = None) -> Path:
    """Export bookmarks as Zotero-compatible RDF/XML."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORTS_DIR / f"bookmarks_zotero_{datetime.now().strftime('%Y%m%d')}.rdf"

    items = []
    for bm in bookmarks:
        tags_xml = ""
        for tag in bm.tags:
            tags_xml += f"\n    <dc:subject>{_esc(tag)}</dc:subject>"

        desc_xml = ""
        if bm.description:
            desc_xml = f"\n    <dcterms:abstract>{_esc(bm.description)}</dcterms:abstract>"

        items.append(f"""  <bib:Document rdf:about="{_esc(bm.url)}">
    <dc:title>{_esc(bm.title)}</dc:title>
    <dc:identifier>{_esc(bm.url)}</dc:identifier>
    <dc:date>{_esc(bm.created_at)}</dc:date>{tags_xml}{desc_xml}
    <z:itemType>webpage</z:itemType>
  </bib:Document>""")

    rdf_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF
  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:bib="http://purl.org/net/biblio#"
  xmlns:z="http://www.zotero.org/namespaces/export#">
{chr(10).join(items)}
</rdf:RDF>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rdf_xml, encoding="utf-8")
    log.info(f"Zotero RDF export: {len(bookmarks)} items to {output_path}")
    return output_path
