"""Bookmark Organizer Pro - package-level re-exports.

This package provides the backend infrastructure (models, utils, managers)
for Bookmark Organizer Pro. The main application file wires these together
with the Tkinter UI.

Example usage:
    from bookmark_organizer_pro import Bookmark, CategoryManager, normalize_url

    cm = CategoryManager()
    category = cm.categorize_url("https://github.com/user/repo")
"""

from .constants import (
    APP_NAME, APP_VERSION, APP_SUBTITLE,
    APP_DIR, FAVICON_DIR, CACHE_DIR, BACKUP_DIR, THEMES_DIR,
    SCREENSHOTS_DIR, LOGS_DIR, DATA_DIR,
    MASTER_BOOKMARKS_FILE, FAILED_FAVICONS_FILE, CATEGORIES_FILE,
    AI_CONFIG_FILE, PATTERNS_FILE, SETTINGS_FILE, TAGS_FILE, LOG_FILE,
    IS_WINDOWS, IS_MAC, IS_LINUX,
)
from .logging_config import AppLogger, log
from .models import Bookmark, Category, Tag
from .utils import (
    # safe
    safe_int, safe_float, safe_str, safe_get, safe_list_get,
    safe_divide, safe_json_loads, safe_json_dumps, safe_get_domain,
    safe_invoke_callback, safe_slice, clamp, truncate_string,
    sanitize_filename, validate_config,
    # validators
    validate_url, validate_path,
    # url normalization
    normalize_url, TRACKING_PARAMS,
    # metadata & wayback
    fetch_page_metadata, wayback_check, wayback_save,
    # health & merging
    calculate_health_score, merge_duplicate_bookmarks,
)
from .core import (
    PatternEngine, StorageManager, CategoryManager,
    CATEGORY_ICONS, get_category_icon,
)
from .io_formats import XBELHandler
from .ai import (
    ensure_package, AIProviderInfo, AI_PROVIDERS,
    AIConfigManager, AIClient, OpenAIClient, AnthropicClient,
    GoogleClient, GroqClient, OllamaClient, create_ai_client,
)
from .search import (
    SearchQuery, SearchEngine, FuzzySearchEngine,
    levenshtein_distance, fuzzy_match,
)
from .importers import (
    BrowserProfileImporter, PocketImporter, RaindropImporter,
    OPMLExporter, TextURLImporter, OPMLImporter,
    OneTabImporter, NetscapeBookmarkImporter,
)
from .link_checker import LinkChecker
from .url_utils import URLUtilities

__version__ = APP_VERSION

__all__ = [
    # Version / constants
    "APP_NAME", "APP_VERSION", "APP_SUBTITLE",
    "APP_DIR", "FAVICON_DIR", "CACHE_DIR", "BACKUP_DIR", "THEMES_DIR",
    "SCREENSHOTS_DIR", "LOGS_DIR", "DATA_DIR",
    "MASTER_BOOKMARKS_FILE", "FAILED_FAVICONS_FILE", "CATEGORIES_FILE",
    "AI_CONFIG_FILE", "PATTERNS_FILE", "SETTINGS_FILE", "TAGS_FILE", "LOG_FILE",
    "IS_WINDOWS", "IS_MAC", "IS_LINUX",
    # Logging
    "AppLogger", "log",
    # Models
    "Bookmark", "Category", "Tag",
    # Safe utilities
    "safe_int", "safe_float", "safe_str", "safe_get", "safe_list_get",
    "safe_divide", "safe_json_loads", "safe_json_dumps", "safe_get_domain",
    "safe_invoke_callback", "safe_slice", "clamp", "truncate_string",
    "sanitize_filename", "validate_config",
    # Validators
    "validate_url", "validate_path",
    # URL / metadata / wayback / health
    "normalize_url", "TRACKING_PARAMS",
    "fetch_page_metadata", "wayback_check", "wayback_save",
    "calculate_health_score", "merge_duplicate_bookmarks",
    # Core managers
    "PatternEngine", "StorageManager", "CategoryManager",
    "CATEGORY_ICONS", "get_category_icon",
    # I/O formats
    "XBELHandler",
    # AI
    "ensure_package", "AIProviderInfo", "AI_PROVIDERS",
    "AIConfigManager", "AIClient", "OpenAIClient", "AnthropicClient",
    "GoogleClient", "GroqClient", "OllamaClient", "create_ai_client",
    # Search
    "SearchQuery", "SearchEngine", "FuzzySearchEngine",
    "levenshtein_distance", "fuzzy_match",
    # Importers
    "BrowserProfileImporter", "PocketImporter", "RaindropImporter",
    "OPMLExporter", "TextURLImporter", "OPMLImporter",
    "OneTabImporter", "NetscapeBookmarkImporter",
    # Link checker
    "LinkChecker",
    # URL utilities
    "URLUtilities",
]
