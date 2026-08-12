"""Durable, conflict-safe reader progress for local bookmark text."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import re
from pathlib import Path
from typing import Iterable

from bookmark_organizer_pro.constants import READER_PROGRESS_FILE
from bookmark_organizer_pro.services.atomic_document_store import (
    AtomicDocumentStore,
    require_mapping_document,
)


PROGRESS_STATES = frozenset({"unread", "in_progress", "finished"})
DEFAULT_PROGRESS_STATE = "unread"
MAX_PROGRESS_RECORDS = 10_000
MAX_PROGRESS_POSITION = 50_000_000
MAX_ANCHOR_CHARS = 128
MAX_CONTEXT_CHARS = 64
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _timestamp_key(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def source_text_sha256(text: str) -> str:
    """Return the representation digest used by progress and highlights."""

    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _clean_digest(value: object) -> str:
    digest = str(value or "").strip().lower()
    return digest if _DIGEST_RE.fullmatch(digest) else ""


def _clean_state(value: object) -> str:
    state = str(value or DEFAULT_PROGRESS_STATE).strip().lower()
    return state if state in PROGRESS_STATES else DEFAULT_PROGRESS_STATE


def _clean_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _clean_anchor(value: object, limit: int) -> str:
    return str(value or "")[:limit]


@dataclass(frozen=True)
class ReaderProgress:
    """One bookmark's position in one derived text representation."""

    bookmark_id: int
    state: str = DEFAULT_PROGRESS_STATE
    position: int = 0
    content_length: int = 0
    source_sha256: str = ""
    anchor_exact: str = ""
    anchor_prefix: str = ""
    anchor_suffix: str = ""
    anchor_offset: int = 0
    updated_at: str = ""

    @classmethod
    def from_dict(cls, raw: object) -> "ReaderProgress | None":
        if not isinstance(raw, dict):
            return None
        bookmark_id = _clean_int(raw.get("bookmark_id"), -1)
        if bookmark_id < 0:
            return None
        content_length = max(
            0,
            min(MAX_PROGRESS_POSITION, _clean_int(raw.get("content_length"))),
        )
        position = max(
            0,
            min(
                content_length or MAX_PROGRESS_POSITION,
                _clean_int(raw.get("position")),
            ),
        )
        return cls(
            bookmark_id=bookmark_id,
            state=_clean_state(raw.get("state")),
            position=position,
            content_length=content_length,
            source_sha256=_clean_digest(raw.get("source_sha256")),
            anchor_exact=_clean_anchor(raw.get("anchor_exact"), MAX_ANCHOR_CHARS),
            anchor_prefix=_clean_anchor(raw.get("anchor_prefix"), MAX_CONTEXT_CHARS),
            anchor_suffix=_clean_anchor(raw.get("anchor_suffix"), MAX_CONTEXT_CHARS),
            anchor_offset=max(0, min(MAX_ANCHOR_CHARS, _clean_int(raw.get("anchor_offset")))),
            updated_at=str(raw.get("updated_at") or "")[:40],
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["state"] = _clean_state(payload.get("state"))
        payload["position"] = max(0, min(MAX_PROGRESS_POSITION, _clean_int(payload.get("position"))))
        payload["content_length"] = max(
            0,
            min(MAX_PROGRESS_POSITION, _clean_int(payload.get("content_length"))),
        )
        if payload["content_length"]:
            payload["position"] = min(payload["position"], payload["content_length"])
        payload["source_sha256"] = _clean_digest(payload.get("source_sha256"))
        payload["anchor_exact"] = _clean_anchor(payload.get("anchor_exact"), MAX_ANCHOR_CHARS)
        payload["anchor_prefix"] = _clean_anchor(payload.get("anchor_prefix"), MAX_CONTEXT_CHARS)
        payload["anchor_suffix"] = _clean_anchor(payload.get("anchor_suffix"), MAX_CONTEXT_CHARS)
        payload["anchor_offset"] = max(0, min(MAX_ANCHOR_CHARS, _clean_int(payload.get("anchor_offset"))))
        payload["updated_at"] = str(payload.get("updated_at") or "")[:40]
        return payload


@dataclass(frozen=True)
class ReaderProgressWrite:
    """Result of an optimistic progress write."""

    progress: ReaderProgress | None
    applied: bool
    conflict: bool = False


def _migrate_reader_progress_v0(document: object) -> dict[str, list]:
    if isinstance(document, list):
        return {"progress": document}
    if isinstance(document, dict):
        records = document.get("progress", document.get("reader_progress", []))
        return {"progress": records if isinstance(records, list) else []}
    return {"progress": []}


def _validate_reader_progress(document: object) -> None:
    require_mapping_document(document)
    records = document.get("progress", [])
    if not isinstance(records, list) or len(records) > MAX_PROGRESS_RECORDS:
        raise ValueError("reader progress must contain a bounded progress list")
    for raw in records:
        if ReaderProgress.from_dict(raw) is None:
            raise ValueError("reader progress entries must be valid objects")


def _record_map(document: dict) -> dict[int, ReaderProgress]:
    records: dict[int, ReaderProgress] = {}
    for raw in document.get("progress", []):
        progress = ReaderProgress.from_dict(raw)
        if progress is None:
            continue
        previous = records.get(progress.bookmark_id)
        if previous is None or _timestamp_key(progress.updated_at) >= _timestamp_key(previous.updated_at):
            records[progress.bookmark_id] = progress
    return records


def _anchor_for(text: str, position: int) -> tuple[str, str, str, int]:
    value = str(text or "")
    if not value:
        return "", "", "", 0
    position = max(0, min(len(value), int(position)))
    start = min(position, max(0, len(value) - MAX_ANCHOR_CHARS))
    return (
        value[start:start + MAX_ANCHOR_CHARS],
        value[max(0, position - MAX_CONTEXT_CHARS):position],
        value[position:position + MAX_CONTEXT_CHARS],
        position - start,
    )


def _find_nearest(haystack: str, needle: str, target: int, offset: int = 0) -> int | None:
    if not needle:
        return None
    matches: list[int] = []
    start = 0
    while len(matches) < 100:
        found = haystack.find(needle, start)
        if found < 0:
            break
        matches.append(found + offset)
        start = found + 1
    return min(matches, key=lambda value: abs(value - target)) if matches else None


def _reanchor(progress: ReaderProgress, text: str) -> int:
    value = str(text or "")
    if not value:
        return 0
    target = int(
        (progress.position / max(1, progress.content_length)) * len(value)
    )
    exact = _find_nearest(
        value,
        progress.anchor_exact,
        target,
        min(progress.anchor_offset, MAX_ANCHOR_CHARS),
    )
    if exact is not None:
        return max(0, min(len(value), exact))
    suffix = _find_nearest(value, progress.anchor_suffix, target)
    if suffix is not None:
        return max(0, min(len(value), suffix))
    prefix = _find_nearest(
        value,
        progress.anchor_prefix,
        target,
        len(progress.anchor_prefix),
    )
    if prefix is not None:
        return max(0, min(len(value), prefix))
    return target


class ReaderProgressStore:
    """Atomic sidecar store with timestamp-guarded writes and re-anchoring."""

    def __init__(self, path: str | Path = READER_PROGRESS_FILE):
        self.path = Path(path)
        self._store = AtomicDocumentStore(
            self.path,
            schema="bookmark-organizer-pro/reader-progress",
            default_factory=lambda: {"progress": []},
            migrations={0: _migrate_reader_progress_v0},
            validator=_validate_reader_progress,
        )

    @property
    def storage_status(self):
        return self._store.status

    def list_all(self) -> list[ReaderProgress]:
        return sorted(
            _record_map(self._store.load()).values(),
            key=lambda item: (item.updated_at, item.bookmark_id),
            reverse=True,
        )

    def get(self, bookmark_id: int) -> ReaderProgress | None:
        return _record_map(self._store.load()).get(int(bookmark_id))

    def save(
        self,
        bookmark_id: int,
        text: str,
        position: int,
        *,
        state: str = DEFAULT_PROGRESS_STATE,
        expected_updated_at: str | None = None,
        updated_at: str | None = None,
    ) -> ReaderProgressWrite:
        value = str(text or "")
        length = min(MAX_PROGRESS_POSITION, len(value))
        position = max(0, min(length, int(position)))
        anchor_exact, anchor_prefix, anchor_suffix, anchor_offset = _anchor_for(value, position)
        candidate = ReaderProgress(
            bookmark_id=int(bookmark_id),
            state=_clean_state(state),
            position=position,
            content_length=length,
            source_sha256=source_text_sha256(value),
            anchor_exact=anchor_exact,
            anchor_prefix=anchor_prefix,
            anchor_suffix=anchor_suffix,
            anchor_offset=anchor_offset,
            updated_at=str(updated_at or _now())[:40],
        )
        result: ReaderProgress | None = None
        applied = False
        conflict = False

        def mutate(document: dict) -> None:
            nonlocal result, applied, conflict
            records = _record_map(document)
            current = records.get(candidate.bookmark_id)
            if expected_updated_at is not None:
                expected = str(expected_updated_at or "")
                if (expected and (current is None or current.updated_at != expected)) or (
                    not expected and current is not None
                ):
                    result = current
                    conflict = True
                    return
            if current is not None and _timestamp_key(current.updated_at) > _timestamp_key(candidate.updated_at):
                result = current
                conflict = True
                return
            records[candidate.bookmark_id] = candidate
            document["progress"] = [
                item.to_dict()
                for item in sorted(
                    records.values(),
                    key=lambda item: (item.updated_at, item.bookmark_id),
                    reverse=True,
                )[:MAX_PROGRESS_RECORDS]
            ]
            result = candidate
            applied = True

        self._store.update(mutate)
        return ReaderProgressWrite(result, applied, conflict)

    def restore(self, bookmark_id: int, text: str) -> ReaderProgress | None:
        current = self.get(bookmark_id)
        if current is None:
            return None
        value = str(text or "")
        digest = source_text_sha256(value)
        if current.source_sha256 == digest:
            return current
        position = _reanchor(current, value)
        write = self.save(
            bookmark_id,
            value,
            position,
            state=current.state,
            updated_at=_now(),
            expected_updated_at=current.updated_at or None,
        )
        return write.progress or current

    def reset(self, bookmark_id: int, *, expected_updated_at: str | None = None) -> bool:
        removed = False
        conflict = False

        def mutate(document: dict) -> None:
            nonlocal removed, conflict
            records = _record_map(document)
            current = records.get(int(bookmark_id))
            if current is None:
                return
            if expected_updated_at is not None and current.updated_at != str(expected_updated_at):
                conflict = True
                return
            records.pop(int(bookmark_id), None)
            document["progress"] = [item.to_dict() for item in records.values()]
            removed = True

        self._store.update(mutate)
        return removed and not conflict

    def apply_to_bookmarks(self, bookmarks: Iterable) -> int:
        records = _record_map(self._store.load())
        applied = 0
        for bookmark in bookmarks:
            progress = records.get(int(getattr(bookmark, "id", -1)))
            if progress is None:
                continue
            bookmark.reader_progress_state = progress.state
            bookmark.reader_progress_position = progress.position
            bookmark.reader_progress_source_sha256 = progress.source_sha256
            bookmark.reader_progress_updated_at = progress.updated_at
            applied += 1
        return applied

    @staticmethod
    def apply_to_bookmark(bookmark, progress: ReaderProgress | None) -> None:
        if progress is None:
            bookmark.reader_progress_state = DEFAULT_PROGRESS_STATE
            bookmark.reader_progress_position = 0
            bookmark.reader_progress_source_sha256 = ""
            bookmark.reader_progress_updated_at = ""
            return
        bookmark.reader_progress_state = progress.state
        bookmark.reader_progress_position = progress.position
        bookmark.reader_progress_source_sha256 = progress.source_sha256
        bookmark.reader_progress_updated_at = progress.updated_at
