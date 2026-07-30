"""Per-bookmark ZIP archive exporter (Readeck-style).

Each bookmark exports as a single immutable ZIP containing:
    - metadata.json   the full bookmark record
    - snapshot.<ext>  the validated offline artifact (if captured)
    - snapshot-manifest.json  portable MIME, digest, and provenance metadata
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
from bookmark_organizer_pro.services.snapshot import ensure_snapshot_manifest


def _safe_name(s: str, fallback: str = "bookmark") -> str:
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in (s or ""))
    return out[:80] or fallback


def _snapshot_export_payload(
    bookmark: Bookmark,
) -> tuple[Path, str, str] | None:
    if not bookmark.snapshot_path:
        return None
    artifact = Path(bookmark.snapshot_path)
    if not artifact.is_file():
        return None
    manifest = ensure_snapshot_manifest(bookmark)
    archive_name = f"snapshot{artifact.suffix.lower()}"
    portable_manifest = manifest.to_dict()
    portable_manifest["artifact_name"] = archive_name
    return (
        artifact,
        archive_name,
        json.dumps(portable_manifest, indent=2, sort_keys=True) + "\n",
    )


def _write_bookmark_payload(z: zipfile.ZipFile, bookmark: Bookmark) -> None:
    snapshot = _snapshot_export_payload(bookmark)
    z.writestr(
        "metadata.json",
        json.dumps(bookmark.to_dict(), indent=2, ensure_ascii=False),
    )
    z.writestr("notes.md", bookmark.notes or "")
    if snapshot is not None:
        artifact, archive_name, manifest_text = snapshot
        z.write(artifact, archive_name)
        z.writestr("snapshot-manifest.json", manifest_text)
    if (
        bookmark.extracted_text_path
        and Path(bookmark.extracted_text_path).exists()
    ):
        z.write(bookmark.extracted_text_path, "extracted.txt")


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
                _write_bookmark_payload(z, bookmark)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
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
            _write_bookmark_payload(z, bookmark)
        return buf.getvalue()
