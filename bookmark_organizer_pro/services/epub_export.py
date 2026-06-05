"""Export bookmark collections as EPUB e-books.

Each bookmark becomes a chapter with its extracted text. Table of contents
generated from bookmark titles. Built with manual ZIP construction following
the EPUB 3.0 spec — no external dependency.
"""

from __future__ import annotations

import html
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from bookmark_organizer_pro.constants import EXPORTS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


def _safe_xhtml(text: str) -> str:
    return html.escape(text or "", quote=True)


def _chapter_xhtml(bookmark: Bookmark, text: str) -> str:
    safe_title = _safe_xhtml(bookmark.title)
    safe_url = _safe_xhtml(bookmark.url)
    body = ""
    if bookmark.description:
        body += f"<p><em>{_safe_xhtml(bookmark.description)}</em></p>\n"
    if text:
        for para in text.split("\n\n"):
            para = para.strip()
            if para:
                body += f"<p>{_safe_xhtml(para)}</p>\n"
    if not body:
        body = f"<p>No extracted text available for this bookmark.</p>\n"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head><title>{safe_title}</title></head>
<body>
<h1>{safe_title}</h1>
<p><a href="{safe_url}">{safe_url}</a></p>
{body}
</body>
</html>"""


def export_epub(bookmarks: List[Bookmark], output_path: Optional[Path] = None,
                title: str = "Bookmark Collection",
                include_text: bool = True) -> Path:
    """Export a list of bookmarks as an EPUB file."""
    if output_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:60]
        output_path = EXPORTS_DIR / f"{safe.strip() or 'collection'}.epub"

    book_id = uuid.uuid4().hex
    now = datetime.now().isoformat()

    chapters = []
    for i, bm in enumerate(bookmarks):
        text = ""
        if include_text and bm.extracted_text_path:
            try:
                text_path = Path(bm.extracted_text_path).resolve()
                if str(text_path).startswith(str(EXPORTS_DIR.parent.resolve())):
                    text = text_path.read_text(encoding="utf-8")[:20000]
            except OSError:
                pass
        chapter_file = f"chapter_{i:04d}.xhtml"
        chapters.append((chapter_file, bm.title or bm.url, _chapter_xhtml(bm, text)))

    toc_items = "\n".join(
        f'    <li><a href="{fn}">{_safe_xhtml(title)}</a></li>'
        for fn, title, _ in chapters
    )
    spine_items = "\n".join(
        f'    <itemref idref="ch{i}"/>'
        for i in range(len(chapters))
    )
    manifest_items = "\n".join(
        f'    <item id="ch{i}" href="{fn}" media-type="application/xhtml+xml"/>'
        for i, (fn, _, _) in enumerate(chapters)
    )

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{_safe_xhtml(title)}</dc:title>
    <dc:language>en</dc:language>
    <dc:date>{now}</dc:date>
    <dc:creator>Bookmark Organizer Pro</dc:creator>
    <meta property="dcterms:modified">{now}</meta>
  </metadata>
  <manifest>
    <item id="toc" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{manifest_items}
  </manifest>
  <spine>
{spine_items}
  </spine>
</package>"""

    toc_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en">
<head><title>Table of Contents</title></head>
<body>
<nav epub:type="toc">
  <h1>{_safe_xhtml(title)}</h1>
  <ol>
{toc_items}
  </ol>
</nav>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.xhtml", toc_xhtml)
        for fn, _, content in chapters:
            zf.writestr(f"OEBPS/{fn}", content)

    log.info(f"EPUB exported: {output_path} ({len(chapters)} chapters)")
    return output_path
