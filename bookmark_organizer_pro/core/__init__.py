"""Core managers for Bookmark Organizer Pro."""

from .pattern_engine import PatternEngine
from .storage_manager import (
    StorageConflictError,
    StorageManager,
    StorageRecoveryRequiredError,
    StorageVersionError,
)
from .sqlite_storage import SQLiteStorageManager, migrate_json_to_sqlite
from .category_manager import CategoryManager, CATEGORY_ICONS, get_category_icon

__all__ = [
    "PatternEngine",
    "StorageManager",
    "StorageConflictError",
    "StorageRecoveryRequiredError",
    "StorageVersionError",
    "SQLiteStorageManager",
    "migrate_json_to_sqlite",
    "CategoryManager",
    "CATEGORY_ICONS",
    "get_category_icon",
]
