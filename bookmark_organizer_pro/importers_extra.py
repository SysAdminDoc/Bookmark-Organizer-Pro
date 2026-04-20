"""Importers added in v6.0: Pocket export, Readwise Reader CSV,
Pinboard JSON, Instapaper CSV/HTML, Reddit Saved JSON.

Each importer takes a path and yields Bookmark objects (without IDs); the
caller is responsible for dedupe and persistence via BookmarkManager.
"""

from __future__ import annotations

import csv
import html as html_module
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.utils import normalize_url


def _ts(value) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(int(value)).isoformat()
        return str(value)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
class PocketExportImporter:
    """Mozilla Pocket export (HTML or JSON)."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        if p.suffix.lower() == ".json":
            return self._from_json(p)
        return self._from_html(p)

    def _from_html(self, p: Path) -> Iterator[Bookmark]:
        try:
            from bs4 import BeautifulSoup
        except Exception:
            log.error("Pocket HTML import requires beautifulsoup4")
            return iter(())
        soup = BeautifulSoup(p.read_text(encoding="utf-8", errors="ignore"),
                             "html.parser")
        out: List[Bookmark] = []
        for a in soup.find_all("a"):
            url = (a.get("href") or "").strip()
            if not url:
                continue
            tags_attr = (a.get("tags") or "").strip()
            tags = [t.strip() for t in tags_attr.split(",") if t.strip()]
            try:
                bm = Bookmark(
                    id=None,
                    url=url,
                    title=html_module.unescape(a.get_text(strip=True) or url),
                    add_date=_ts(a.get("time_added") or a.get("add_date")),
                    tags=tags,
                    source_file="pocket-export",
                )
                out.append(bm)
            except ValueError:
                continue
        return iter(out)

    def _from_json(self, p: Path) -> Iterator[Bookmark]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error(f"Pocket JSON parse failed: {exc}")
            return iter(())
        items = data.get("list", data) if isinstance(data, dict) else data
        out: List[Bookmark] = []
        if isinstance(items, dict):
            items = items.values()
        for item in items if isinstance(items, Iterable) else []:
            if not isinstance(item, dict):
                continue
            url = item.get("resolved_url") or item.get("given_url") or ""
            if not url:
                continue
            tags = []
            t = item.get("tags")
            if isinstance(t, dict):
                tags = list(t.keys())
            elif isinstance(t, list):
                tags = [str(x) for x in t]
            try:
                out.append(Bookmark(
                    id=None, url=str(url),
                    title=str(item.get("resolved_title") or
                              item.get("given_title") or url),
                    add_date=_ts(item.get("time_added")),
                    tags=tags,
                    source_file="pocket-export-json",
                ))
            except ValueError:
                continue
        return iter(out)


# ---------------------------------------------------------------------------
class ReadwiseReaderCSVImporter:
    """Readwise Reader CSV export."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        out: List[Bookmark] = []
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = (row.get("URL") or row.get("url") or "").strip()
                if not url:
                    continue
                tags_field = row.get("Tags") or row.get("tags") or ""
                tags = [t.strip() for t in re.split(r"[,;]", tags_field) if t.strip()]
                try:
                    out.append(Bookmark(
                        id=None, url=url,
                        title=row.get("Title") or row.get("title") or url,
                        description=row.get("Document note") or row.get("Note") or "",
                        category=row.get("Category") or "",
                        tags=tags,
                        add_date=row.get("Saved date") or row.get("created_at") or "",
                        source_file="readwise-reader-csv",
                    ))
                except ValueError:
                    continue
        return iter(out)


# ---------------------------------------------------------------------------
class PinboardJSONImporter:
    """Pinboard `format=json` export."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return iter(())
        if not isinstance(data, list):
            return iter(())
        out: List[Bookmark] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            url = (item.get("href") or "").strip()
            if not url:
                continue
            tags_str = item.get("tags") or ""
            tags = [t.strip() for t in tags_str.split(" ") if t.strip()]
            try:
                out.append(Bookmark(
                    id=None, url=url,
                    title=item.get("description") or url,
                    description=item.get("extended") or "",
                    tags=tags,
                    add_date=item.get("time") or "",
                    source_file="pinboard-json",
                ))
            except ValueError:
                continue
        return iter(out)


# ---------------------------------------------------------------------------
class InstapaperImporter:
    """Instapaper CSV export (folder, URL, title, selection, timestamp)."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        out: List[Bookmark] = []
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 2:
                    continue
                # Header detection
                if row[0].lower() == "url" or row[0].lower() == "folder":
                    continue
                # Layout: URL,Title,Selection,Folder,Timestamp
                if "://" in row[0]:
                    url = row[0]
                    title = row[1] if len(row) > 1 else url
                    folder = row[3] if len(row) > 3 else ""
                else:
                    folder = row[0]
                    url = row[1]
                    title = row[2] if len(row) > 2 else url
                if not url:
                    continue
                try:
                    out.append(Bookmark(
                        id=None, url=url, title=title or url,
                        category=folder or "",
                        source_file="instapaper-csv",
                    ))
                except ValueError:
                    continue
        return iter(out)


# ---------------------------------------------------------------------------
class RedditSavedImporter:
    """Reddit `saved.json` from Reddit data export."""

    def from_path(self, path: str) -> Iterator[Bookmark]:
        p = Path(path)
        if not p.exists():
            return iter(())
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return iter(())
        children = []
        if isinstance(data, dict):
            children = data.get("data", {}).get("children", []) or []
        elif isinstance(data, list):
            children = data
        out: List[Bookmark] = []
        for child in children:
            if not isinstance(child, dict):
                continue
            d = child.get("data") if "data" in child else child
            if not isinstance(d, dict):
                continue
            url = d.get("url") or d.get("link") or ""
            permalink = d.get("permalink") or ""
            if permalink and not url:
                url = "https://www.reddit.com" + permalink
            if not url:
                continue
            title = d.get("title") or d.get("link_title") or url
            subreddit = d.get("subreddit") or ""
            tags = ["reddit"]
            if subreddit:
                tags.append(f"r/{subreddit}")
            try:
                out.append(Bookmark(
                    id=None, url=url, title=title,
                    category=f"Reddit / {subreddit}" if subreddit else "Reddit",
                    tags=tags,
                    add_date=_ts(d.get("created_utc") or d.get("created")),
                    source_file="reddit-saved",
                ))
            except ValueError:
                continue
        return iter(out)


def import_into(manager, importer, path: str) -> Tuple[int, int]:
    """Helper: run any importer above through a BookmarkManager.

    Returns (added, duplicates).
    """
    added = duplicates = 0
    existing = {normalize_url(bm.url) for bm in manager.bookmarks.values()}
    for bm in importer.from_path(path):
        canonical = normalize_url(bm.url)
        if canonical in existing:
            duplicates += 1
            continue
        manager.add_bookmark(bm, save=False)
        existing.add(canonical)
        added += 1
    if added:
        manager.save_bookmarks()
    return added, duplicates
