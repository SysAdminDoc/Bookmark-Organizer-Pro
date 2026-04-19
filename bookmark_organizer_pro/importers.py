"""Importers for various bookmark formats and services.

Supports: Chrome/Edge/Brave, Firefox, Pocket, Raindrop.io, OPML, OneTab,
Netscape/Mozilla HTML, plain text URLs.
"""

import csv
import html as html_module
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .constants import DATA_DIR, IS_WINDOWS, IS_MAC
from .logging_config import log
from .models import Bookmark


def _decode(text: str) -> str:
    """Decode HTML entities in text. Safe for None/empty."""
    if not text:
        return text or ""
    return html_module.unescape(text)


class BrowserProfileImporter:
    """Import bookmarks directly from browser profiles"""

    BROWSER_PATHS = {
        "chrome": {
            "windows": Path(__import__('os').environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data",
            "darwin": Path.home() / "Library/Application Support/Google/Chrome",
            "linux": Path.home() / ".config/google-chrome",
        },
        "firefox": {
            "windows": Path(__import__('os').environ.get("APPDATA", "")) / "Mozilla/Firefox/Profiles",
            "darwin": Path.home() / "Library/Application Support/Firefox/Profiles",
            "linux": Path.home() / ".mozilla/firefox",
        },
        "edge": {
            "windows": Path(__import__('os').environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/User Data",
            "darwin": Path.home() / "Library/Application Support/Microsoft Edge",
            "linux": Path.home() / ".config/microsoft-edge",
        },
        "brave": {
            "windows": Path(__import__('os').environ.get("LOCALAPPDATA", "")) / "BraveSoftware/Brave-Browser/User Data",
            "darwin": Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser",
            "linux": Path.home() / ".config/BraveSoftware/Brave-Browser",
        }
    }

    def __init__(self):
        self.os_name = "windows" if IS_WINDOWS else ("darwin" if IS_MAC else "linux")

    def get_available_browsers(self) -> List[str]:
        """Get list of browsers with detected profiles"""
        available = []
        for browser, paths in self.BROWSER_PATHS.items():
            browser_path = paths.get(self.os_name)
            if browser_path and browser_path.exists():
                available.append(browser)
        return available

    def get_profiles(self, browser: str) -> List[Tuple[str, Path]]:
        """Get available profiles for a browser"""
        browser_path = self.BROWSER_PATHS.get(browser, {}).get(self.os_name)
        if not browser_path or not browser_path.exists():
            return []

        profiles = []

        if browser == "firefox":
            for profile_dir in browser_path.iterdir():
                if profile_dir.is_dir():
                    places_db = profile_dir / "places.sqlite"
                    if places_db.exists():
                        profiles.append((profile_dir.name, profile_dir))
        else:
            default = browser_path / "Default"
            if default.exists():
                profiles.append(("Default", default))
            for item in browser_path.iterdir():
                if item.is_dir() and item.name.startswith("Profile "):
                    profiles.append((item.name, item))

        return profiles

    def import_from_chrome(self, profile_path: Path) -> List[Bookmark]:
        """Import bookmarks from Chrome/Edge/Brave"""
        bookmarks_file = profile_path / "Bookmarks"
        if not bookmarks_file.exists():
            return []

        try:
            with open(bookmarks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            bookmarks = []

            def process_node(node, path=""):
                if node.get("type") == "url":
                    bm = Bookmark(
                        id=None,
                        url=node.get("url", ""),
                        title=node.get("name", ""),
                        category=path or "Imported"
                    )
                    date_added = node.get("date_added", "0")
                    try:
                        timestamp = (int(date_added) - 11644473600000000) / 1000000
                        bm.created_at = datetime.fromtimestamp(timestamp).isoformat()
                    except Exception:
                        pass
                    bookmarks.append(bm)
                elif node.get("type") == "folder":
                    folder_name = node.get("name", "")
                    new_path = f"{path}/{folder_name}" if path else folder_name
                    for child in node.get("children", []):
                        process_node(child, new_path)

            roots = data.get("roots", {})
            for root_name, root_node in roots.items():
                if isinstance(root_node, dict):
                    process_node(root_node, "")

            return bookmarks
        except Exception as e:
            log.error(f"Error importing Chrome bookmarks: {e}")
            return []

    def import_from_firefox(self, profile_path: Path) -> List[Bookmark]:
        """Import bookmarks from Firefox"""
        places_db = profile_path / "places.sqlite"
        if not places_db.exists():
            return []

        # Guard against oversized or corrupt files
        try:
            if places_db.stat().st_size > 500_000_000:  # 500MB limit
                log.error(f"Firefox places.sqlite too large: {places_db.stat().st_size} bytes")
                return []
        except OSError:
            return []

        import sqlite3

        temp_db = DATA_DIR / "temp_places.sqlite"
        shutil.copy2(places_db, temp_db)

        bookmarks = []

        try:
            conn = sqlite3.connect(str(temp_db))
            cursor = conn.cursor()

            query = """
            SELECT
                b.title,
                p.url,
                b.dateAdded,
                (SELECT GROUP_CONCAT(parent_b.title, '/')
                 FROM moz_bookmarks parent_b
                 WHERE parent_b.id IN (
                     WITH RECURSIVE ancestors(id, parent) AS (
                         SELECT id, parent FROM moz_bookmarks WHERE id = b.parent
                         UNION ALL
                         SELECT mb.id, mb.parent FROM moz_bookmarks mb
                         JOIN ancestors a ON mb.id = a.parent
                     )
                     SELECT id FROM ancestors
                 ) AND parent_b.type = 2
                ) as folder_path
            FROM moz_bookmarks b
            JOIN moz_places p ON b.fk = p.id
            WHERE b.type = 1 AND p.url NOT LIKE 'place:%'
            """

            cursor.execute(query)

            for row in cursor.fetchall():
                title, url, date_added, folder_path = row
                cat = "Imported"
                if folder_path and isinstance(folder_path, str):
                    parts = folder_path.split('/')
                    cat = parts[-1] if parts[-1] else "Imported"
                bm = Bookmark(
                    id=None,
                    url=url or "",
                    title=title or url or "",
                    category=cat
                )
                if date_added:
                    try:
                        bm.created_at = datetime.fromtimestamp(date_added / 1000000).isoformat()
                    except Exception:
                        pass
                bookmarks.append(bm)

            conn.close()
        except Exception as e:
            log.error(f"Error importing Firefox bookmarks: {e}")
        finally:
            if temp_db.exists():
                temp_db.unlink()

        return bookmarks


class PocketImporter:
    """Import bookmarks from Pocket export"""

    @staticmethod
    def import_from_html(filepath: str) -> List[Bookmark]:
        """Import from Pocket HTML export file"""
        bookmarks = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            pattern = r'<a\s+href="([^"]+)"[^>]*time_added="(\d+)"[^>]*(?:tags="([^"]*)")?[^>]*>([^<]*)</a>'
            matches = re.findall(pattern, content, re.IGNORECASE)

            for match in matches:
                url, timestamp, tags, title = match
                bm = Bookmark(
                    id=None,
                    url=_decode(url),
                    title=_decode(title).strip() or _decode(url),
                    category="Imported from Pocket"
                )
                try:
                    bm.created_at = datetime.fromtimestamp(int(timestamp)).isoformat()
                except Exception:
                    pass
                if tags:
                    bm.tags = [_decode(t).strip() for t in tags.split(',') if t.strip()]
                bookmarks.append(bm)

            if not bookmarks:
                simple_pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]*)</a>'
                matches = re.findall(simple_pattern, content, re.IGNORECASE)
                for url, title in matches:
                    if url.startswith(('http://', 'https://')):
                        bm = Bookmark(
                            id=None,
                            url=_decode(url),
                            title=_decode(title).strip() or _decode(url),
                            category="Imported from Pocket"
                        )
                        bookmarks.append(bm)

        except Exception as e:
            log.error(f"Error importing Pocket: {e}")

        return bookmarks


class RaindropImporter:
    """Import bookmarks from Raindrop.io export"""

    @staticmethod
    def import_from_csv(filepath: str) -> List[Bookmark]:
        """Import from Raindrop CSV export"""
        bookmarks = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bm = Bookmark(
                        id=None,
                        url=row.get('url', row.get('link', '')),
                        title=row.get('title', ''),
                        category=row.get('folder', row.get('collection', 'Imported from Raindrop'))
                    )
                    if row.get('note') or row.get('excerpt'):
                        bm.notes = row.get('note', '') or row.get('excerpt', '')
                    tags = row.get('tags', '')
                    if tags:
                        bm.tags = [t.strip() for t in tags.split(',') if t.strip()]
                    created = row.get('created', row.get('created_at', ''))
                    if created:
                        try:
                            bm.created_at = datetime.fromisoformat(created.replace('Z', '+00:00')).isoformat()
                        except Exception:
                            pass
                    if bm.url:
                        bookmarks.append(bm)

        except Exception as e:
            log.error(f"Error importing Raindrop: {e}")

        return bookmarks

    @staticmethod
    def import_from_html(filepath: str) -> List[Bookmark]:
        """Import from Raindrop HTML export"""
        bookmarks = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            folder_pattern = r'<h3[^>]*>([^<]+)</h3>\s*<dl>(.*?)</dl>'
            folder_matches = re.findall(folder_pattern, content, re.DOTALL | re.IGNORECASE)

            for folder_name, folder_content in folder_matches:
                bm_pattern = r'<a\s+href="([^"]+)"[^>]*>([^<]*)</a>'
                bm_matches = re.findall(bm_pattern, folder_content, re.IGNORECASE)
                for url, title in bm_matches:
                    bm = Bookmark(
                        id=None,
                        url=_decode(url),
                        title=_decode(title).strip() or _decode(url),
                        category=_decode(folder_name).strip()
                    )
                    bookmarks.append(bm)

        except Exception as e:
            log.error(f"Error importing Raindrop HTML: {e}")

        return bookmarks


class OPMLExporter:
    """Export bookmarks in OPML format"""

    @staticmethod
    def export(bookmarks: List[Bookmark], filepath: str,
               title: str = "Bookmark Export"):
        """Export bookmarks to OPML file"""
        by_category: Dict[str, List[Bookmark]] = {}
        for bm in bookmarks:
            cat = bm.category or "Uncategorized"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(bm)

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<opml version="2.0">',
            '  <head>',
            f'    <title>{title}</title>',
            f'    <dateCreated>{datetime.now().isoformat()}</dateCreated>',
            '  </head>',
            '  <body>',
        ]

        for category, cat_bookmarks in sorted(by_category.items()):
            cat_escaped = category.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            lines.append(f'    <outline text="{cat_escaped}" title="{cat_escaped}">')
            for bm in cat_bookmarks:
                title_escaped = bm.title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                url_escaped = bm.url.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                lines.append(f'      <outline type="link" text="{title_escaped}" title="{title_escaped}" xmlUrl="{url_escaped}" htmlUrl="{url_escaped}"/>')
            lines.append('    </outline>')

        lines.extend([
            '  </body>',
            '</opml>'
        ])

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


class TextURLImporter:
    """Import URLs from plain text files (one URL per line)"""

    URL_PATTERN = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*',
        re.IGNORECASE
    )

    @staticmethod
    def import_from_text(filepath: str) -> List[Bookmark]:
        """Import URLs from text file"""
        bookmarks = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            urls = TextURLImporter.URL_PATTERN.findall(content)

            for url in urls:
                url = url.strip().rstrip('.,;:!?')
                if url:
                    bm = Bookmark(
                        id=None,
                        url=url,
                        title=url,
                        category="Imported from Text"
                    )
                    bookmarks.append(bm)

        except Exception as e:
            log.error(f"Error importing text file: {e}")

        return bookmarks


class OPMLImporter:
    """Import bookmarks from OPML files"""

    @staticmethod
    def import_from_opml(filepath: str) -> List[Bookmark]:
        """Import from OPML file"""
        bookmarks = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            outline_pattern = r'<outline[^>]*(?:xmlUrl|htmlUrl)="([^"]*)"[^>]*(?:text|title)="([^"]*)"[^>]*/?\s*>'
            matches = re.findall(outline_pattern, content, re.IGNORECASE)

            for url, title in matches:
                if url:
                    bm = Bookmark(
                        id=None,
                        url=_decode(url),
                        title=_decode(title) or _decode(url),
                        category="Imported from OPML"
                    )
                    bookmarks.append(bm)

            if not bookmarks:
                alt_pattern = r'<outline[^>]*text="([^"]*)"[^>]*(?:xmlUrl|htmlUrl)="([^"]*)"[^>]*/?\s*>'
                matches = re.findall(alt_pattern, content, re.IGNORECASE)
                for title, url in matches:
                    if url:
                        bm = Bookmark(
                            id=None,
                            url=_decode(url),
                            title=_decode(title) or _decode(url),
                            category="Imported from OPML"
                        )
                        bookmarks.append(bm)

        except Exception as e:
            log.error(f"Error importing OPML: {e}")

        return bookmarks


class OneTabImporter:
    """Import from OneTab export format"""

    @staticmethod
    def import_from_onetab(filepath: str) -> List[Bookmark]:
        """Import from OneTab export (pipe-separated format)"""
        bookmarks = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    if ' | ' in line:
                        parts = line.split(' | ', 1)
                        url = parts[0].strip()
                        title = parts[1].strip() if len(parts) > 1 else url
                    else:
                        url = line
                        title = line

                    if url.startswith(('http://', 'https://')):
                        bm = Bookmark(
                            id=None,
                            url=url,
                            title=title,
                            category="Imported from OneTab"
                        )
                        bookmarks.append(bm)

        except Exception as e:
            log.error(f"Error importing OneTab: {e}")

        return bookmarks


class NetscapeBookmarkImporter:
    """Enhanced Netscape bookmark format parser (used by most browsers)"""

    @staticmethod
    def import_from_netscape(filepath: str) -> List[Bookmark]:
        """Import from Netscape/Mozilla bookmark format"""
        bookmarks = []
        current_folder = "Imported"
        folder_stack = []

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            lines = content.split('\n')

            for line in lines:
                line = line.strip()

                folder_match = re.search(r'<H3[^>]*>([^<]+)</H3>', line, re.IGNORECASE)
                if folder_match:
                    folder_name = _decode(folder_match.group(1)).strip()
                    folder_stack.append(current_folder)
                    current_folder = folder_name
                    continue

                if '</DL>' in line.upper():
                    if folder_stack:
                        current_folder = folder_stack.pop()
                    continue

                bm_match = re.search(
                    r'<A[^>]*HREF="([^"]*)"[^>]*>([^<]*)</A>',
                    line, re.IGNORECASE
                )
                if bm_match:
                    url = _decode(bm_match.group(1))
                    title = _decode(bm_match.group(2)).strip()

                    if url and url.startswith(('http://', 'https://')):
                        add_date_match = re.search(r'ADD_DATE="(\d+)"', line, re.IGNORECASE)

                        bm = Bookmark(
                            id=None,
                            url=url,
                            title=title or url,
                            category=current_folder
                        )

                        if add_date_match:
                            try:
                                timestamp = int(add_date_match.group(1))
                                bm.created_at = datetime.fromtimestamp(timestamp).isoformat()
                            except Exception:
                                pass

                        tags_match = re.search(r'TAGS="([^"]*)"', line, re.IGNORECASE)
                        if tags_match:
                            tags = _decode(tags_match.group(1))
                            bm.tags = [t.strip() for t in tags.split(',') if t.strip()]

                        bookmarks.append(bm)

        except Exception as e:
            log.error(f"Error importing Netscape bookmarks: {e}")

        return bookmarks
