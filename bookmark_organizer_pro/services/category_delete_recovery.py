"""Durable, restart-visible recovery for category deletion."""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from bookmark_organizer_pro.models import Category
from bookmark_organizer_pro.services.atomic_document_store import AtomicDocumentStore


def _validate_record(document: Any) -> None:
    if not isinstance(document, dict):
        raise ValueError("category delete recovery record must be an object")
    if not document:
        return
    required = {"state", "name", "category", "bookmark_ids", "safepoint", "created_at"}
    if not required.issubset(document):
        raise ValueError("category delete recovery record is incomplete")
    if document["state"] not in {"prepared", "ready", "failed"}:
        raise ValueError("category delete recovery state is invalid")
    if not isinstance(document["name"], str) or not document["name"].strip():
        raise ValueError("category delete recovery name is invalid")
    if not isinstance(document["category"], dict):
        raise ValueError("category delete recovery category is invalid")
    if not isinstance(document["bookmark_ids"], list):
        raise ValueError("category delete recovery bookmark IDs are invalid")


class CategoryDeleteRecovery:
    """Coordinate category deletion across category and bookmark stores."""

    def __init__(self, category_manager, bookmark_manager, path: str | Path | None = None):
        self.category_manager = category_manager
        self.bookmark_manager = bookmark_manager
        category_path = Path(category_manager.filepath)
        self.path = Path(path) if path else category_path.with_name("category_delete_recovery.json")
        self._store = AtomicDocumentStore(
            self.path,
            schema="bookmark-organizer-category-delete-recovery",
            default_factory=dict,
            validator=_validate_record,
        )

    def pending(self) -> dict[str, Any] | None:
        record = self._store.load()
        return record if record.get("state") == "ready" else None

    def delete(self, name: str) -> dict[str, Any]:
        category = self.category_manager.categories.get(name)
        if category is None:
            raise ValueError(f"Category {name!r} does not exist")
        bookmarks = list(self.bookmark_manager.get_bookmarks_by_category(name))
        safepoint = self.bookmark_manager.create_safepoint("pre-delete-category") or ""
        if not safepoint:
            raise RuntimeError("category deletion stopped because a bookmark safepoint was unavailable")
        record = {
            "state": "prepared",
            "name": name,
            "category": category.to_dict(),
            "bookmark_ids": [bookmark.id for bookmark in bookmarks],
            "safepoint": safepoint,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._store.save(record)

        try:
            with self._bookmark_batch():
                for bookmark in bookmarks:
                    bookmark.category = "Uncategorized / Needs Review"
                    self.bookmark_manager.update_bookmark(bookmark)
            self.category_manager.categories.pop(name)
            self.category_manager.save_categories()
            self._rebuild_patterns()
            self._verify_deleted(record)
            record["state"] = "ready"
            self._store.save(record)
            return record
        except Exception as exc:
            rollback_ok = self._rollback_delete(record)
            record["state"] = "failed"
            self._store.save(record)
            suffix = "rollback completed" if rollback_ok else "rollback could not be verified"
            raise RuntimeError(
                f"category deletion failed ({suffix}); bookmark safepoint: {safepoint}: {exc}"
            ) from exc

    def restore(self) -> tuple[str, int]:
        record = self.pending()
        if not record:
            raise RuntimeError("No deleted category is available to restore")
        rollback = self.bookmark_manager.create_safepoint("pre-restore-category") or ""
        if not rollback:
            raise RuntimeError("category restore stopped because a bookmark safepoint was unavailable")
        name = record["name"]
        category_before = self.category_manager.categories.get(name)
        try:
            category = Category.from_dict(record["category"])
            category.name = name
            self.category_manager.categories[name] = category
            self.category_manager.save_categories()
            self._rebuild_patterns()
            restored = 0
            with self._bookmark_batch():
                for bookmark_id in record["bookmark_ids"]:
                    bookmark = self.bookmark_manager.get_bookmark(bookmark_id)
                    if bookmark is None:
                        continue
                    bookmark.category = name
                    self.bookmark_manager.update_bookmark(bookmark)
                    restored += 1
            self._verify_restored(record)
            self._store.save({})
            return name, restored
        except Exception:
            self.bookmark_manager.restore_backup(rollback)
            if category_before is None:
                self.category_manager.categories.pop(name, None)
            else:
                self.category_manager.categories[name] = category_before
            self.category_manager.save_categories()
            self._rebuild_patterns()
            raise

    def _bookmark_batch(self):
        batch = getattr(self.bookmark_manager, "batch", None)
        return batch() if callable(batch) else contextlib.nullcontext()

    def _rebuild_patterns(self) -> None:
        rebuild = getattr(self.category_manager, "_rebuild_patterns", None)
        if callable(rebuild):
            rebuild()

    def _persisted_categories(self) -> dict[str, Any]:
        path = Path(self.category_manager.filepath)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("persisted categories are not an object")
        return raw

    def _verify_deleted(self, record: dict[str, Any]) -> None:
        name = record["name"]
        if name in self.category_manager.categories or name in self._persisted_categories():
            raise RuntimeError("deleted category remains in persisted category storage")
        for bookmark_id in record["bookmark_ids"]:
            bookmark = self.bookmark_manager.get_bookmark(bookmark_id)
            if bookmark is not None and bookmark.category == name:
                raise RuntimeError("bookmark reassignment was not persisted")

    def _verify_restored(self, record: dict[str, Any]) -> None:
        name = record["name"]
        if name not in self.category_manager.categories or name not in self._persisted_categories():
            raise RuntimeError("restored category was not persisted")
        for bookmark_id in record["bookmark_ids"]:
            bookmark = self.bookmark_manager.get_bookmark(bookmark_id)
            if bookmark is not None and bookmark.category != name:
                raise RuntimeError("bookmark category restore was not persisted")

    def _rollback_delete(self, record: dict[str, Any]) -> bool:
        restored = bool(self.bookmark_manager.restore_backup(record["safepoint"]))
        category = Category.from_dict(record["category"])
        category.name = record["name"]
        self.category_manager.categories[record["name"]] = category
        self.category_manager.save_categories()
        self._rebuild_patterns()
        try:
            self._verify_restored(record)
        except Exception:
            return False
        return restored
