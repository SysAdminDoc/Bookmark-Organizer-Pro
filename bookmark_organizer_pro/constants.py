"""Application constants and path configuration."""

import platform
from pathlib import Path

# Application metadata
APP_NAME = "Bookmark Organizer Pro"
APP_VERSION = "4.6.0"
APP_SUBTITLE = "Ultimate Bookmark Management"

# Paths
APP_DIR = Path.home() / ".bookmark_organizer"
APP_DIR.mkdir(exist_ok=True)

FAVICON_DIR = APP_DIR / "favicons"
FAVICON_DIR.mkdir(exist_ok=True)
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
BACKUP_DIR = APP_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
THEMES_DIR = APP_DIR / "themes"
THEMES_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR = APP_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)
LOGS_DIR = APP_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

DATA_DIR = APP_DIR
MASTER_BOOKMARKS_FILE = DATA_DIR / "master_bookmarks.json"
FAILED_FAVICONS_FILE = DATA_DIR / "failed_favicons.json"
CATEGORIES_FILE = DATA_DIR / "categories.json"
AI_CONFIG_FILE = DATA_DIR / "ai_config.json"
PATTERNS_FILE = DATA_DIR / "patterns.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
TAGS_FILE = DATA_DIR / "tags.json"
LOG_FILE = LOGS_DIR / "bookmark_organizer.log"

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
