"""Per-bookmark ZIP archive exporter (Readeck-style).

Each bookmark exports as a single immutable ZIP containing:
    - metadata.json   the full bookmark record
    - snapshot.html   the captured page (if SnapshotArchiver has run)
    - extracted.txt   the trafilatura-extracted text (if available)
    - notes.md        user notes (always included, even if empty)

A whole-collection export bundles every per-bookmark ZIP into one
"collection.zip" so users can move the entire library file-by-file.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Iterable, Tuple

from bookmark_organizer_pro.constants import EXPORTS_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


def _safe_name(s: str, fallback: str = "bookmark") -> str:
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in (s or ""))
    return out[:80] or fallback


class ZipExporter:
    """Bundle bookmarks as portable ZIP archives."""

    def __init__(self, exports_dir: Path = EXPORTS_DIR):
        self.exports_dir = Path(exports_dir)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def export_one(self, bookmark: Bookmark,
                   out_path: Path | None = None) -> Tuple[bool, str]:
        if out_path is None:
            name = f"{bookmark.id}_{_safe_name(bookmark.title or bookmark.url)}.zip"
            out_path = self.exports_dir / name
        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("metadata.json",
                           json.dumps(bookmark.to_dict(), indent=2, ensure_ascii=False))
                z.writestr("notes.md", bookmark.notes or "")
                if bookmark.snapshot_path and Path(bookmark.snapshot_path).exists():
                    z.write(bookmark.snapshot_path, "snapshot.html")
                if bookmark.extracted_text_path and Path(bookmark.extracted_text_path).exists():
                    z.write(bookmark.extracted_text_path, "extracted.txt")
        except OSError as exc:
            log.warning(f"ZIP export failed: {exc}")
            return False, str(exc)
        return True, str(out_path)

    def export_collection(self, bookmarks: Iterable[Bookmark],
                          out_path: Path | None = None) -> Tuple[bool, str]:
        if out_path is None:
            from datetime import datetime as _dt
            out_path = self.exports_dir / f"collection_{_dt.now().strftime('%Y%m%d_%H%M%S')}.zip"
        try:
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as outer:
                for bm in bookmarks:
                    name = f"{bm.id}_{_safe_name(bm.title or bm.url)}.zip"
                    inner_data = self._build_inner(bm)
                    outer.writestr(name, inner_data)
        except OSError as exc:
            log.warning(f"Collection ZIP failed: {exc}")
            return False, str(exc)
        return True, str(out_path)

    def _build_inner(self, bookmark: Bookmark) -> bytes:
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("metadata.json",
                       json.dumps(bookmark.to_dict(), indent=2, ensure_ascii=False))
            z.writestr("notes.md", bookmark.notes or "")
            if bookmark.snapshot_path and Path(bookmark.snapshot_path).exists():
                z.write(bookmark.snapshot_path, "snapshot.html")
            if bookmark.extracted_text_path and Path(bookmark.extracted_text_path).exists():
                z.write(bookmark.extracted_text_path, "extracted.txt")
        return buf.getvalue()
