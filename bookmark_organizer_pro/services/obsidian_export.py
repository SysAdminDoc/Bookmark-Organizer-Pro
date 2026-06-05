"""Export bookmarks to Obsidian vault as Markdown files with YAML frontmatter.

Each bookmark becomes one .md file:
    ---
    url: https://example.com
    title: Example Site
    category: Development
    tags: [python, tutorial]
    created: 2026-01-15T10:30:00
    ---

    # Example Site

    > https://example.com

    [extracted text or notes here]

CLI: bop obsidian-export --vault ~/Notes --since 2026-06-01
MCP: export_to_obsidian(vault_path, tag_filter, since)
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


def _safe_filename(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title or "bookmark")
    name = re.sub(r'_+', '_', name).strip('_. ')
    return (name[:120] or "bookmark") + ".md"


def _yaml_list(items: List[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(f'"{t}"' for t in items) + "]"


def export_bookmark(bookmark: Bookmark, vault_dir: Path,
                    include_text: bool = True) -> Path:
    """Write a single bookmark as a Markdown file in the vault directory."""
    vault_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(bookmark.title)
    out_path = vault_dir / filename

    counter = 1
    while out_path.exists():
        stem = filename[:-3]
        out_path = vault_dir / f"{stem}_{counter}.md"
        counter += 1

    tags = list(bookmark.tags) + list(bookmark.ai_tags)
    tags = list(dict.fromkeys(t.lower() for t in tags if t.strip()))

    lines = [
        "---",
        f"url: {bookmark.url}",
        f"title: \"{bookmark.title}\"",
        f"category: {bookmark.full_category_path}",
        f"tags: {_yaml_list(tags)}",
        f"created: {bookmark.created_at}",
    ]
    if bookmark.language:
        lines.append(f"language: {bookmark.language}")
    if bookmark.content_type:
        lines.append(f"content_type: {bookmark.content_type}")
    if bookmark.reading_time:
        lines.append(f"reading_time: {bookmark.reading_time}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {bookmark.title}")
    lines.append("")
    lines.append(f"> {bookmark.url}")
    lines.append("")

    if bookmark.description:
        lines.append(bookmark.description)
        lines.append("")

    if bookmark.notes:
        lines.append("## Notes")
        lines.append("")
        lines.append(bookmark.notes)
        lines.append("")

    if include_text and bookmark.extracted_text_path:
        try:
            text = Path(bookmark.extracted_text_path).read_text(encoding="utf-8")
            if text.strip():
                lines.append("## Content")
                lines.append("")
                lines.append(text[:10000])
                lines.append("")
        except OSError:
            pass

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def export_collection(bookmarks: List[Bookmark], vault_dir: Path,
                      tag_filter: Optional[str] = None,
                      category_filter: Optional[str] = None,
                      since: Optional[str] = None,
                      include_text: bool = True) -> List[Path]:
    """Export matching bookmarks to an Obsidian vault."""
    filtered = bookmarks

    if tag_filter:
        tag_l = tag_filter.lower()
        filtered = [b for b in filtered
                    if any(t.lower() == tag_l for t in b.tags)]

    if category_filter:
        cat_l = category_filter.lower()
        filtered = [b for b in filtered
                    if cat_l in b.category.lower() or cat_l in b.parent_category.lower()]

    if since:
        try:
            cutoff = datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None)
            filtered = [b for b in filtered
                        if b.created_at and
                        datetime.fromisoformat(b.created_at.replace("Z", "+00:00")).replace(tzinfo=None) >= cutoff]
        except (ValueError, TypeError):
            log.warning(f"Invalid 'since' date: {since}")

    paths = []
    for bm in filtered:
        try:
            p = export_bookmark(bm, vault_dir, include_text=include_text)
            paths.append(p)
        except Exception as exc:
            log.warning(f"Failed to export bookmark {bm.id}: {exc}")

    log.info(f"Exported {len(paths)} bookmarks to {vault_dir}")
    return paths
