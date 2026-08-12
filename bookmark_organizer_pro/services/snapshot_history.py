"""Versioned snapshot provenance, retention, and change reports."""

from __future__ import annotations

import difflib
import hashlib
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentStore,
    require_mapping_document,
)


@dataclass(frozen=True)
class SnapshotVersion:
    version_id: str
    bookmark_id: int | None
    source_url: str
    resolved_url: str
    status_code: int | None
    captured_at: str
    sha256: str
    size: int
    backend: str
    path: str
    mime_type: str
    representation: str

    @classmethod
    def from_dict(cls, value: dict) -> "SnapshotVersion":
        status = value.get("status_code")
        return cls(
            version_id=str(value.get("version_id") or ""),
            bookmark_id=int(value["bookmark_id"]) if value.get("bookmark_id") is not None else None,
            source_url=str(value.get("source_url") or ""),
            resolved_url=str(value.get("resolved_url") or ""),
            status_code=int(status) if status is not None else None,
            captured_at=str(value.get("captured_at") or ""),
            sha256=str(value.get("sha256") or ""),
            size=int(value.get("size") or 0),
            backend=str(value.get("backend") or "unknown"),
            path=str(value.get("path") or ""),
            mime_type=str(
                value.get("mime_type")
                or (
                    "text/html"
                    if Path(str(value.get("path") or "")).suffix.lower() == ".html"
                    else "application/octet-stream"
                )
            ),
            representation=str(
                value.get("representation")
                or (
                    "bundled-html"
                    if Path(str(value.get("path") or "")).suffix.lower() == ".html"
                    else "binary"
                )
            ),
        )


class SnapshotHistoryStore:
    """Keep immutable versions while retaining the current compatibility path."""

    def __init__(self, snapshots_dir: Path, *, max_versions: int = 10):
        self.snapshots_dir = Path(snapshots_dir)
        self.max_versions = max(1, min(1000, int(max_versions)))
        self._store = AtomicDocumentStore(
            self.snapshots_dir.parent / "snapshot_history.json",
            schema="bookmark-organizer-pro/snapshot-history",
            current_version=2,
            default_factory=lambda: {"versions": []},
            migrations={
                0: lambda value: value if isinstance(value, dict) else {"versions": []},
                1: self._migrate_format_metadata,
            },
            validator=self._validate,
        )

    @staticmethod
    def _migrate_format_metadata(document):
        migrated = document if isinstance(document, dict) else {"versions": []}
        versions = migrated.get("versions", [])
        if not isinstance(versions, list):
            return migrated
        for item in versions:
            if not isinstance(item, dict):
                continue
            is_html = Path(str(item.get("path") or "")).suffix.lower() == ".html"
            item.setdefault(
                "mime_type",
                "text/html" if is_html else "application/octet-stream",
            )
            item.setdefault(
                "representation",
                "bundled-html" if is_html else "binary",
            )
        return migrated

    @staticmethod
    def _validate(document) -> None:
        require_mapping_document(document)
        versions = document.get("versions", [])
        if not isinstance(versions, list) or any(not isinstance(item, dict) for item in versions):
            raise ValueError("snapshot history versions must be an array of objects")
        for item in versions:
            if item.get("representation") not in {"bundled-html", "binary"}:
                raise ValueError("snapshot history representation is invalid")
            if not isinstance(item.get("mime_type"), str) or not item["mime_type"]:
                raise ValueError("snapshot history MIME type is invalid")

    def record(
        self,
        bookmark_id: int | None,
        current_path: Path,
        *,
        source_url: str,
        resolved_url: str = "",
        status_code: int | None = None,
        backend: str = "unknown",
        captured_at: str = "",
        mime_type: str = "text/html",
        representation: str = "bundled-html",
    ) -> SnapshotVersion:
        payload = Path(current_path).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        captured = captured_at or datetime.now(timezone.utc).isoformat()
        identity = str(bookmark_id) if bookmark_id is not None else f"url:{source_url}"
        safe_id = str(bookmark_id) if bookmark_id is not None else f"url-{hashlib.sha256(source_url.encode()).hexdigest()[:16]}"
        version_id = f"{captured.replace(':', '').replace('-', '').replace('+', '_')}-{digest[:12]}"
        version_dir = self.snapshots_dir / safe_id / "history"
        version_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(current_path).suffix.lower()
        if suffix not in {".html", ".pdf", ".png", ".jpg", ".gif", ".webp"}:
            raise ValueError("snapshot history extension is not supported")
        version_path = version_dir / f"{version_id}{suffix}"
        if not version_path.exists():
            shutil.copyfile(current_path, version_path)
        record = SnapshotVersion(
            version_id=version_id,
            bookmark_id=bookmark_id,
            source_url=source_url,
            resolved_url=resolved_url or source_url,
            status_code=status_code,
            captured_at=captured,
            sha256=digest,
            size=len(payload),
            backend=backend,
            path=str(version_path),
            mime_type=str(mime_type or "application/octet-stream"),
            representation=str(representation or "binary"),
        )

        removed_paths: list[Path] = []
        def mutate(document):
            versions = [item for item in document.get("versions", []) if item.get("version_id") != version_id]
            versions.append(asdict(record))
            matching = sorted(
                [
                    item for item in versions
                    if (
                        str(item.get("bookmark_id"))
                        if item.get("bookmark_id") is not None
                        else f"url:{item.get('source_url', '')}"
                    ) == identity
                ],
                key=lambda item: str(item.get("captured_at") or ""),
                reverse=True,
            )
            for expired in matching[self.max_versions:]:
                versions.remove(expired)
                removed_paths.append(Path(str(expired.get("path") or "")))
            document["versions"] = versions
        self._store.update(mutate)
        for path in removed_paths:
            path.unlink(missing_ok=True)
        return record

    def list_versions(self, bookmark_id: int | None) -> list[SnapshotVersion]:
        document = self._store.load()
        try:
            target_id = int(bookmark_id) if bookmark_id is not None else None
        except (TypeError, ValueError):
            target_id = None
        versions = [
            SnapshotVersion.from_dict(item)
            for item in document.get("versions", [])
            if target_id is not None
            and item.get("bookmark_id") is not None
            and str(item.get("bookmark_id")) == str(target_id)
        ]
        return sorted(versions, key=lambda item: item.captured_at, reverse=True)

    def clear_bookmark(self, bookmark_id: int | None) -> int:
        """Remove retained history artifacts for one bookmark only."""
        if bookmark_id is None:
            return 0
        try:
            target_id = int(bookmark_id)
        except (TypeError, ValueError):
            return 0
        removed: list[Path] = []

        def mutate(document):
            versions = []
            for item in document.get("versions", []):
                if str(item.get("bookmark_id")) == str(target_id):
                    path = Path(str(item.get("path") or ""))
                    try:
                        if path.resolve(strict=False).is_relative_to(self.snapshots_dir.resolve()):
                            removed.append(path)
                    except (OSError, RuntimeError, ValueError):
                        pass
                    continue
                versions.append(item)
            document["versions"] = versions

        self._store.update(mutate)
        for path in removed:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
        return len(removed)

    def remove_version(self, version_id: str) -> bool:
        """Remove one retained snapshot version and its local artifact."""
        target = str(version_id or "").strip()
        if not target:
            return False
        removed: list[Path] = []

        def mutate(document):
            kept = []
            for item in document.get("versions", []):
                if str(item.get("version_id") or "") != target:
                    kept.append(item)
                    continue
                path = Path(str(item.get("path") or ""))
                try:
                    if path.resolve(strict=False).is_relative_to(self.snapshots_dir.resolve()):
                        removed.append(path)
                except (OSError, RuntimeError, ValueError):
                    pass
            document["versions"] = kept

        self._store.update(mutate)
        for path in removed:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
        return bool(removed)

    def list_all_versions(self, *, limit: int | None = None) -> list[SnapshotVersion]:
        document = self._store.load()
        versions = [SnapshotVersion.from_dict(item) for item in document.get("versions", [])]
        versions.sort(key=lambda item: item.captured_at, reverse=True)
        return versions if limit is None else versions[:max(0, int(limit))]

    def relocate_paths(self, destination_snapshots_dir: Path) -> int:
        """Rewrite version paths after a portable recovery-bundle restore."""
        destination = Path(destination_snapshots_dir).resolve()
        changed = 0
        def mutate(document):
            nonlocal changed
            for item in document.get("versions", []):
                original = Path(str(item.get("path") or ""))
                parts = list(original.parts)
                try:
                    marker = len(parts) - 1 - parts[::-1].index("snapshots")
                except ValueError:
                    continue
                relative = Path(*parts[marker + 1:])
                if not relative.parts:
                    continue
                item["path"] = str((destination / relative).resolve())
                changed += 1
        self._store.update(mutate)
        return changed

    def change_report(self, older_id: str, newer_id: str, *, max_diff_lines: int = 500) -> dict:
        document = self._store.load()
        lookup = {
            item.get("version_id"): SnapshotVersion.from_dict(item)
            for item in document.get("versions", [])
        }
        older = lookup.get(older_id)
        newer = lookup.get(newer_id)
        if older is None or newer is None:
            raise KeyError("Snapshot version was not found")
        comparable_text = (
            older.representation == "bundled-html"
            and newer.representation == "bundled-html"
        )
        diff: list[str] = []
        if comparable_text:
            old_text = self._visible_text(
                Path(older.path).read_text(encoding="utf-8", errors="replace")
            )
            new_text = self._visible_text(
                Path(newer.path).read_text(encoding="utf-8", errors="replace")
            )
            diff = list(difflib.unified_diff(
                old_text.splitlines(), new_text.splitlines(),
                fromfile=older.version_id, tofile=newer.version_id, lineterm="",
            ))
        return {
            "older": asdict(older),
            "newer": asdict(newer),
            "content_changed": older.sha256 != newer.sha256,
            "redirect_changed": older.resolved_url != newer.resolved_url,
            "status_changed": older.status_code != newer.status_code,
            "text_diff_available": comparable_text,
            "diff": diff[: max(0, int(max_diff_lines))],
            "diff_truncated": len(diff) > max_diff_lines,
        }

    @staticmethod
    def _visible_text(html: str) -> str:
        html = re.sub(r"<(script|style)\b.*?</\1\s*>", "", html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r"<[^>]+>", " ", html)
        return "\n".join(line.strip() for line in re.sub(r"[ \t]+", " ", html).splitlines() if line.strip())
