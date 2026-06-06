"""Application constants and path configuration."""

import os
import platform
from pathlib import Path

# Application metadata
APP_NAME = "Bookmark Organizer Pro"
APP_VERSION = "6.6.12"
APP_SUBTITLE = "Ultimate Bookmark Management"

# Paths
#
# README documents BOOKMARK_DATA_DIR as the supported override. Resolve it here
# once so every manager writes to the same location, including logs and caches.
_data_dir_override = os.environ.get("BOOKMARK_DATA_DIR", "").strip()
APP_DIR = Path(_data_dir_override).expanduser() if _data_dir_override else Path.home() / ".bookmark_organizer"
APP_DIR = APP_DIR.resolve()

FAVICON_DIR = APP_DIR / "favicons"
CACHE_DIR = APP_DIR / "cache"
BACKUP_DIR = APP_DIR / "backups"
THEMES_DIR = APP_DIR / "themes"
SCREENSHOTS_DIR = APP_DIR / "screenshots"
LOGS_DIR = APP_DIR / "logs"

DATA_DIR = APP_DIR
MASTER_BOOKMARKS_FILE = DATA_DIR / "master_bookmarks.json"
FAILED_FAVICONS_FILE = DATA_DIR / "failed_favicons.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"
AI_CONFIG_FILE = DATA_DIR / "ai_config.json"
PATTERNS_FILE = DATA_DIR / "patterns.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
TAGS_FILE = DATA_DIR / "tags.json"
LOG_FILE = LOGS_DIR / "bookmark_organizer.log"

# v6.0.0 directories
SNAPSHOTS_DIR = APP_DIR / "snapshots"
EXTRACTED_DIR = APP_DIR / "extracted"
EMBEDDINGS_DIR = APP_DIR / "embeddings"
EXPORTS_DIR = APP_DIR / "exports"
FLOWS_FILE = DATA_DIR / "flows.json"
FEEDS_FILE = DATA_DIR / "feeds.json"
DEAD_LINKS_FILE = DATA_DIR / "dead_links.json"

_ALL_DIRS = [APP_DIR, FAVICON_DIR, CACHE_DIR, BACKUP_DIR, THEMES_DIR,
             SCREENSHOTS_DIR, LOGS_DIR, SNAPSHOTS_DIR, EXTRACTED_DIR,
             EMBEDDINGS_DIR, EXPORTS_DIR]


def ensure_directories():
    """Create all application directories. Call from entry points only."""
    for d in _ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
