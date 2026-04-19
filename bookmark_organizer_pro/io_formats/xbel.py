"""XBEL (XML Bookmark Exchange Language) import/export.

XBEL is a standard XML-based interchange format supported by KDE Konqueror,
GNOME Epiphany, Buku, and other tools.

Spec: https://pyxml.sourceforge.net/topics/xbel/
Inspired by Buku's 7-format support.
"""

import html as html_module
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ..constants import APP_VERSION
from ..logging_config import log
from ..models import Bookmark


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (text.replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;')
            .replace("'", '&apos;'))


class XBELHandler:
    """Import and export bookmarks in XBEL format.

    Round-trip preserves: titles, URLs, categories, tags, descriptions,
    created/visited dates.
    """

    @staticmethod
    def export(bookmarks: List[Bookmark], filepath: str):
        """Export bookmarks to XBEL format with atomic write."""
        # Group by category
        by_category: Dict[str, List[Bookmark]] = {}
        for bm in bookmarks or []:
            category = str(getattr(bm, "category", "") or "Uncategorized / Needs Review").strip()
            by_category.setdefault(category or "Uncategorized / Needs Review", []).append(bm)

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE xbel PUBLIC "+//IDN python.org//DTD XML Bookmark Exchange '
            'Language 1.0//EN//XML"',
            '    "http://pyxml.sourceforge.net/topics/dtds/xbel.dtd">',
            '<xbel version="1.0">',
            f'  <title>Bookmarks (Exported by Bookmark Organizer Pro v{APP_VERSION})</title>',
        ]

        for cat_name in sorted(by_category.keys()):
            bms = by_category[cat_name]
            lines.append('  <folder>')
            lines.append(f'    <title>{_escape_xml(cat_name)}</title>')

            for bm in bms:
                added = ''
                if getattr(bm, "created_at", ""):
                    try:
                        dt = datetime.fromisoformat(bm.created_at.replace('Z', '+00:00'))
                        added = f' added="{dt.strftime("%Y-%m-%dT%H:%M:%S")}"'
                    except Exception:
                        pass
                visited = ''
                if getattr(bm, "last_visited", ""):
                    try:
                        dt = datetime.fromisoformat(bm.last_visited.replace('Z', '+00:00'))
                        visited = f' visited="{dt.strftime("%Y-%m-%dT%H:%M:%S")}"'
                    except Exception:
                        pass

                url = str(getattr(bm, "url", "") or "").strip()
                if not url:
                    continue
                title = str(getattr(bm, "title", "") or url)
                lines.append(f'    <bookmark href="{_escape_xml(url)}"{added}{visited}>')
                lines.append(f'      <title>{_escape_xml(title)}</title>')

                desc_parts = []
                description = str(getattr(bm, "description", "") or "").strip()
                tags = [
                    str(tag).strip()
                    for tag in (getattr(bm, "tags", None) or [])
                    if str(tag).strip()
                ]
                if description:
                    desc_parts.append(description)
                if tags:
                    desc_parts.append(f'Tags: {", ".join(tags)}')
                if desc_parts:
                    lines.append(f'      <desc>{_escape_xml("; ".join(desc_parts))}</desc>')
                lines.append('    </bookmark>')

            lines.append('  </folder>')

        lines.append('</xbel>')

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=filepath.parent, suffix='.tmp', text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            os.replace(temp_path, filepath)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    @staticmethod
    def import_from_xbel(filepath: str) -> List[Bookmark]:
        """Parse an XBEL file and return a list of Bookmark objects."""
        bookmarks = []

        try:
            filepath = Path(filepath)
            if filepath.stat().st_size > 50_000_000:
                log.error(f"XBEL file too large: {filepath}")
                return []

            xml_bytes = filepath.read_bytes()
            if b"<!ENTITY" in xml_bytes.upper():
                log.error(f"XBEL file contains XML entities and was rejected: {filepath}")
                return []
            root = ET.fromstring(xml_bytes)

            # Strip namespace if present
            ns = ''
            if root.tag.startswith('{'):
                ns = root.tag[:root.tag.index('}') + 1]

            def parse_folder(element, category="Imported from XBEL", is_root=False):
                """Recursively parse folders and bookmarks."""
                title_el = element.find(f'{ns}title')
                if not is_root and title_el is not None and title_el.text:
                    folder_title = title_el.text.strip()
                    if folder_title:
                        if category and category != "Imported from XBEL":
                            category = f"{category} / {folder_title}"
                        else:
                            category = folder_title

                for bm_el in element.findall(f'{ns}bookmark'):
                    href = str(bm_el.get('href', '') or '').strip()
                    if not href or not href.startswith(('http://', 'https://')):
                        continue

                    bm_title_el = bm_el.find(f'{ns}title')
                    bm_title = (
                        bm_title_el.text.strip()
                        if bm_title_el is not None and bm_title_el.text
                        else href
                    )

                    try:
                        bm = Bookmark(
                            id=None,
                            url=href,
                            title=html_module.unescape(bm_title),
                            category=category,
                        )
                    except ValueError:
                        continue

                    added = bm_el.get('added', '')
                    if added:
                        try:
                            bm.created_at = datetime.fromisoformat(added).isoformat()
                        except Exception:
                            pass
                    visited = bm_el.get('visited', '')
                    if visited:
                        try:
                            bm.last_visited = datetime.fromisoformat(visited).isoformat()
                        except Exception:
                            pass

                    desc_el = bm_el.find(f'{ns}desc')
                    if desc_el is not None and desc_el.text:
                        desc = desc_el.text.strip()
                        if 'Tags:' in desc:
                            parts = desc.split('Tags:', 1)
                            bm.description = parts[0].rstrip('; ').strip()
                            bm.tags = [t.strip() for t in parts[1].split(',') if t.strip()]
                        else:
                            bm.description = desc

                    bookmarks.append(bm)

                for folder_el in element.findall(f'{ns}folder'):
                    parse_folder(folder_el, category)

            parse_folder(root, is_root=True)

        except Exception as e:
            log.error(f"Error importing XBEL: {e}")

        return bookmarks
