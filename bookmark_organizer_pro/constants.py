"""Application constants and path configuration."""

import os
import platform
from pathlib import Path

# Application metadata
APP_NAME = "Bookmark Organizer Pro"
APP_VERSION = "6.0.0"
APP_SUBTITLE = "Ultimate Bookmark Management"

# Paths
#
# README documents BOOKMARK_DATA_DIR as the supported override. Resolve it here
# once so every manager writes to the same location, including logs and caches.
_data_dir_override = os.environ.get("BOOKMARK_DATA_DIR", "").strip()
APP_DIR = Path(_data_dir_override).expanduser() if _data_dir_override else Path.home() / ".bookmark_organizer"
APP_DIR = APP_DIR.resolve()
APP_DIR.mkdir(parents=True, exist_ok=True)

FAVICON_DIR = APP_DIR / "favicons"
FAVICON_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = APP_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
THEMES_DIR = APP_DIR / "themes"
THEMES_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR = APP_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR = APP_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

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
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR = APP_DIR / "extracted"
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
EMBEDDINGS_DIR = APP_DIR / "embeddings"
EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR = APP_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
FLOWS_FILE = DATA_DIR / "flows.json"
FEEDS_FILE = DATA_DIR / "feeds.json"
DEAD_LINKS_FILE = DATA_DIR / "dead_links.json"

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
